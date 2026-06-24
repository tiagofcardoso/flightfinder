import asyncio
import os
import io
import json
import logging
import tempfile
import httpx
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types

from .db import create_alert
from .telegram_service import (
    send_interactive_menu, edit_interactive_menu,
    answer_callback, send_telegram_message, send_voice_message
)
from .flight_search.manager import FlightSearchManager

logger = logging.getLogger(__name__)

# In-memory conversation history per user: chat_id -> list of {role, text}
USER_CONVERSATIONS: Dict[int, List[Dict[str, str]]] = {}

# In-memory flight state per user: chat_id -> extracted params dict
USER_STATES: Dict[int, Dict[str, Any]] = {}

flight_manager = FlightSearchManager()

# System prompt for the conversational super-agent
SYSTEM_PROMPT = """Você é o AeroMilhas, um SUPER AGENTE DE VIAGENS com 20 anos de experiência, especialista em encontrar as melhores tarifas aéreas entre Brasil, Portugal e o mundo.

Você pensa ALÉM do pedido do utilizador — antecipa necessidades, sugere rotas alternativas mais baratas e sempre age como um consultor de viagens premium.

═══════════════════════════════════
COMPORTAMENTO E CONVERSAÇÃO
═══════════════════════════════════
1. Converse naturalmente em Português (PT/BR), adapte ao tom do utilizador (formal/informal).
2. Seja caloroso, entusiasta e proativo — como um agente de viagens experiente que adora o seu trabalho.
3. Se o utilizador disser "oi", "olá", etc., responda com energia e pergunte para onde quer ir.
4. Lembre-se do contexto anterior — "e se for em outubro?" refere-se sempre à última rota mencionada.
5. Se faltar origem, destino ou data, PERGUNTE de forma natural — nunca dê erro genérico.

═══════════════════════════════════
INTELIGÊNCIA DE ROTAS (PENSE SEMPRE NISTO)
═══════════════════════════════════
6. Sempre pense em alternativas de custo-benefício ANTES de pesquisar:
   - Aeroportos alternativos próximos (ex: GRU/CGH/VCP para São Paulo, LIS/OPO para Portugal)
   - Rotas via hubs mais baratos (ex: GRU→MIA→JFK pode ser mais barato que direto)
   - Datas adjacentes (terça/quarta são geralmente mais baratas que sexta/domingo)
   - Ida e volta vs só ida (às vezes comprar 2 passagens de ida é mais barato)
7. Quando sugerir pesquisa, mencione que vai comparar preços do mercado brasileiro E português.

═══════════════════════════════════
AÇÃO DE PESQUISA (FORMATO OBRIGATÓRIO)
═══════════════════════════════════
8. Quando tiver origem + destino + data de partida, retorne EXCLUSIVAMENTE este JSON (sem mais nada):
   {"action": "search", "origin": "GRU", "destination": "LIS", "departure_date": "2026-10-15", "return_date": "2026-10-22", "target_price": 800.0}
9. Para respostas de conversa normal: texto livre, máximo 4 linhas, use emojis com moderação.
10. Conversões IATA obrigatórias: Lisboa→LIS, Porto→OPO, São Paulo→GRU, Rio→GIG, Paris→CDG, Nova Iorque→JFK, Miami→MIA, Londres→LHR, Madrid→MAD, Roma→FCO, Frankfurt→FRA, Amsterdam→AMS, Dubai→DXB, Tóquio→NRT.
11. Ano de referência: 2026. "setembro" sem ano = setembro 2026.
12. Se o utilizador disser "só ida": return_date = null.
13. Após mostrar resultados, SEMPRE sugira ativar um alerta 24/7 para monitorizar o preço."""


async def chat_with_gemini_agent(chat_id: int, user_text: str) -> str:
    """
    Conversational agent using Gemini with per-user conversation history.
    Returns either a natural language reply or a JSON action string.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "❌ Serviço de IA não configurado."

    client = genai.Client(api_key=api_key)

    # Build conversation history
    history = USER_CONVERSATIONS.get(chat_id, [])

    # Build contents for Gemini
    contents = []
    for msg in history[-10:]:  # Keep last 10 messages for context
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["text"])]))

    # Add current user message
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=500
            )
        )
        reply = response.text.strip()

        # Update conversation history
        if chat_id not in USER_CONVERSATIONS:
            USER_CONVERSATIONS[chat_id] = []
        USER_CONVERSATIONS[chat_id].append({"role": "user", "text": user_text})
        USER_CONVERSATIONS[chat_id].append({"role": "model", "text": reply})

        # Trim history to last 20 messages
        if len(USER_CONVERSATIONS[chat_id]) > 20:
            USER_CONVERSATIONS[chat_id] = USER_CONVERSATIONS[chat_id][-20:]

        return reply

    except Exception as e:
        logger.error(f"Gemini agent error: {e}")
        return "❌ Ocorreu um erro ao processar a sua mensagem. Tente novamente."


async def transcribe_voice_with_gemini(audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
    """
    Transcribes a voice message using Gemini's native audio understanding.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
                    types.Part(text="Transcreve este áudio em texto, em Português. Retorna APENAS a transcrição, sem explicações.")
                ])
            ]
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        return None


async def handle_voice_message(chat_id: int, file_id: str):
    """Downloads and transcribes a Telegram voice message, then processes as text."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return

    try:
        # Step 1: Get file path from Telegram
        async with httpx.AsyncClient() as client:
            file_resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id},
                timeout=10.0
            )
            file_data = file_resp.json()
            file_path = file_data.get("result", {}).get("file_path")
            if not file_path:
                await send_telegram_message("❌ Não consegui processar o áudio.", str(chat_id))
                return

        # Step 2: Download audio file
        async with httpx.AsyncClient() as client:
            audio_resp = await client.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}",
                timeout=30.0
            )
            audio_bytes = audio_resp.content

        # Step 3: Transcribe with Gemini
        await send_telegram_message("🎤 *A transcrever o seu áudio...*", str(chat_id))
        transcription = await transcribe_voice_with_gemini(audio_bytes, "audio/ogg")

        if not transcription:
            await send_telegram_message("❌ Não consegui entender o áudio. Tente enviar uma mensagem de texto.", str(chat_id))
            return

        logger.info(f"Voice transcription for chat {chat_id}: '{transcription}'")

        # Step 4: Show what was understood and process as text
        await send_telegram_message(f"🎤 *Entendi:* _{transcription}_", str(chat_id))
        await handle_telegram_message(chat_id, transcription, reply_with_voice=True)

    except Exception as e:
        logger.error(f"Voice message handling error: {e}")
        await send_telegram_message("❌ Erro ao processar o áudio.", str(chat_id))


async def handle_telegram_message(chat_id: int, text: str, reply_with_voice: bool = False):
    """Processes a text message from Telegram using the conversational Gemini agent."""
    text_clean = text.strip().lower()

    # Handle /start command
    if text_clean.startswith("/start"):
        welcome = (
            "👋 *Bem-vindo ao AeroMilhas!* ✈️\n\n"
            "Sou o seu assistente de viagens com IA. Pode falar comigo de forma natural!\n\n"
            "💬 *Exemplos do que pode dizer:*\n"
            "• _\"Quero ir a Paris em setembro\"_\n"
            "• _\"Voo de Lisboa para Nova Iorque em outubro, volta em novembro\"_\n"
            "• _\"GRU para LIS dia 15/10, orçamento $800\"_\n\n"
            "🎤 Também pode enviar *mensagens de voz*!\n\n"
            "Com o que posso ajudar?"
        )
        await send_telegram_message(welcome, str(chat_id))
        return

    # Handle /reset command to clear conversation history
    if text_clean.startswith("/reset") or text_clean.startswith("/novo"):
        USER_CONVERSATIONS.pop(chat_id, None)
        USER_STATES.pop(chat_id, None)
        await send_telegram_message("🔄 *Conversa reiniciada!* Para onde quer viajar?", str(chat_id))
        return

    # Send to conversational Gemini agent
    typing_msg = "🤖 _A pensar..._"
    await send_telegram_message(typing_msg, str(chat_id))

    agent_reply = await chat_with_gemini_agent(chat_id, text)

    # Check if Gemini returned a search action JSON
    action_data = None
    try:
        # Try to parse as JSON action
        clean = agent_reply.strip()
        if clean.startswith("{") and '"action"' in clean:
            action_data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        pass

    if action_data and action_data.get("action") == "search":
        # Extract flight parameters and show interactive menu
        state = {
            "origin": action_data.get("origin", "").upper(),
            "destination": action_data.get("destination", "").upper(),
            "departure_date": action_data.get("departure_date", ""),
            "return_date": action_data.get("return_date"),
            "target_price": float(action_data.get("target_price") or 1000.0),
            "direct": False,
            "flexible": False
        }
        USER_STATES[chat_id] = state

        confirm_text = (
            f"✅ *Encontrei os seus critérios de voo:*\n"
            f"✈️ *{state['origin']} → {state['destination']}*\n"
            f"📅 Ida: {state['departure_date']}"
            + (f" | Volta: {state['return_date']}" if state.get('return_date') else " (Só ida)")
            + f"\n💰 Orçamento: ${state['target_price']}\n\n"
            "Configure as opções abaixo:"
        )
        await send_telegram_message(confirm_text, str(chat_id))
        await send_interactive_menu(str(chat_id), state)

    else:
        # Natural language reply
        if reply_with_voice:
            await send_voice_message(agent_reply, str(chat_id))
        else:
            await send_telegram_message(agent_reply, str(chat_id))


async def handle_callback_query(chat_id: int, message_id: int, data: str, callback_query_id: str):
    """Processes button clicks from Telegram inline keyboard."""
    state = USER_STATES.get(chat_id)
    if not state:
        await answer_callback(callback_query_id, "Sessão expirada. Envie uma nova mensagem.")
        return

    if data == "toggle_direct":
        state["direct"] = not state["direct"]
        await edit_interactive_menu(str(chat_id), message_id, state)
        await answer_callback(callback_query_id, f"Apenas Voo Direto: {'Ativo ✅' if state['direct'] else 'Inativo ⬜'}")

    elif data == "toggle_flexible":
        state["flexible"] = not state["flexible"]
        await edit_interactive_menu(str(chat_id), message_id, state)
        await answer_callback(callback_query_id, f"Datas Flexíveis: {'Ativo ✅' if state['flexible'] else 'Inativo ⬜'}")

    elif data == "save_alert":
        await answer_callback(callback_query_id, "Configurando Alerta 24/7...")
        try:
            alert_id = create_alert(
                origin=state["origin"],
                destination=state["destination"],
                departure_date=state["departure_date"],
                return_date=state["return_date"],
                target_price=state["target_price"],
                chat_id=str(chat_id)
            )
            state["status_msg"] = f"Alerta 24/7 Ativado! (ID: #{alert_id}) 🔔"
            await edit_interactive_menu(str(chat_id), message_id, state)
            success_text = (
                f"🔔 *Alerta 24/7 Ativado!*\n"
                f"Vou monitorizar *{state['origin']} → {state['destination']}* "
                f"e aviso-o aqui se o preço baixar de *${state['target_price']}*."
            )
            await send_telegram_message(success_text, str(chat_id))
        except Exception as e:
            logger.error(f"Failed to register alert: {e}")
            await send_telegram_message(f"❌ Erro ao registar alerta: {e}", str(chat_id))

    elif data == "run_search":
        await answer_callback(callback_query_id, "Procurando voos nos mercados BR e PT...")
        state["status_msg"] = "🌎 Comparando preços Brasil vs Portugal... 🚀"
        await edit_interactive_menu(str(chat_id), message_id, state)

        try:
            origin = state["origin"]
            destination = state["destination"]
            dep_date = state["departure_date"]
            ret_date = state["return_date"]

            # Run multi-market search AND alternative routes in parallel
            multi_task = flight_manager.search_flights_multi_market(
                origin=origin, destination=destination,
                departure_date=dep_date, return_date=ret_date, passengers=1
            )
            alt_task = flight_manager.search_alternative_routes(
                origin=origin, destination=destination,
                departure_date=dep_date, return_date=ret_date, passengers=1
            )
            multi_result, alt_results = await asyncio.gather(multi_task, alt_task)

            br_flights = multi_result.get("br", [])
            pt_flights = multi_result.get("pt", [])
            recommendation = multi_result.get("recommendation", "br")
            savings = multi_result.get("savings", 0)

            # Apply direct filter if requested
            if state.get("direct"):
                br_flights = [f for f in br_flights if f["stops"] == 0]
                pt_flights = [f for f in pt_flights if f["stops"] == 0]

            all_flights = br_flights or pt_flights
            if not all_flights:
                await send_telegram_message("❌ *Nenhum voo encontrado para esta rota e data.*\nTente datas diferentes ou active as Datas Flexíveis.", str(chat_id))
                state["status_msg"] = "Pesquisa concluída (Nenhum resultado)."
                await edit_interactive_menu(str(chat_id), message_id, state)
                return

            # ── Header ──────────────────────────────────────────
            header = [
                f"🔍 *AeroMilhas — Análise de Mercado*",
                f"✈️ *{origin} → {destination}* ({'Ida e Volta' if ret_date else 'Só Ida'})",
                f"📅 {dep_date}" + (f" ↩ {ret_date}" if ret_date else ""),
                ""
            ]
            await send_telegram_message("\n".join(header), str(chat_id))

            # ── Brazil market results ────────────────────────────
            if br_flights:
                br_lines = ["🇧🇷 *Mercado Brasil (Google Flights BR):*"]
                for i, flight in enumerate(br_flights[:3]):
                    out = flight["outbound"]
                    ret_info = flight.get("inbound")
                    stops_text = "Direto ✅" if flight["stops"] == 0 else f"{flight['stops']} escala(s) ⚠️"
                    booking_url = flight.get("booking_url", "")
                    line = f"*{i+1}. ${flight['price']}* — {stops_text} | {out['airline']} {out['departure_time']}→{out['arrival_time']}"
                    if ret_info:
                        line += f" / {ret_info['departure_time']}→{ret_info['arrival_time']}"
                    br_lines.append(line)
                    if booking_url:
                        br_lines.append(f"   🔗 [Ver no Google Flights]({booking_url})")
                await send_telegram_message("\n".join(br_lines), str(chat_id))

            # ── Portugal market results ──────────────────────────
            if pt_flights:
                pt_lines = ["🇵🇹 *Mercado Portugal (Google Flights PT):*"]
                for i, flight in enumerate(pt_flights[:3]):
                    out = flight["outbound"]
                    ret_info = flight.get("inbound")
                    stops_text = "Direto ✅" if flight["stops"] == 0 else f"{flight['stops']} escala(s) ⚠️"
                    booking_url = flight.get("booking_url", "")
                    line = f"*{i+1}. ${flight['price']}* — {stops_text} | {out['airline']} {out['departure_time']}→{out['arrival_time']}"
                    if ret_info:
                        line += f" / {ret_info['departure_time']}→{ret_info['arrival_time']}"
                    pt_lines.append(line)
                    if booking_url:
                        pt_lines.append(f"   🔗 [Ver no Google Flights]({booking_url})")
                await send_telegram_message("\n".join(pt_lines), str(chat_id))

            # ── Market comparison verdict ────────────────────────
            if br_flights and pt_flights and savings > 1:
                rec_flag = "🇧🇷" if recommendation == "br" else "🇵🇹"
                rec_name = "Brasil" if recommendation == "br" else "Portugal"
                verdict = (
                    f"💡 *Recomendação do Agente:*\n"
                    f"{rec_flag} Pesquisar pelo mercado *{rec_name}* está *${savings} mais barato* nesta rota!\n"
                    f"Use a VPN ou acesse google.com.{'br' if recommendation == 'br' else 'pt'}/flights para garantir este preço."
                )
                await send_telegram_message(verdict, str(chat_id))

            # ── Alternative airports/routes ──────────────────────
            if alt_results:
                alt_lines = ["🗺️ *Rotas Alternativas (aeroportos próximos):*"]
                for alt in alt_results[:2]:
                    alt_org = alt.get("alt_origin", origin)
                    alt_dst = alt.get("alt_destination", destination)
                    booking_url = alt.get("booking_url", "")
                    alt_lines.append(f"• *{alt_org} → {alt_dst}*: ${alt['price']}")
                    if booking_url:
                        alt_lines.append(f"  🔗 [Ver no Google Flights]({booking_url})")
                await send_telegram_message("\n".join(alt_lines), str(chat_id))

            # ── Flexible dates matrix ────────────────────────────
            if state.get("flexible"):
                await send_telegram_message("📅 *A calcular datas alternativas...*", str(chat_id))
                matrix = await flight_manager.get_price_matrix(
                    origin=origin, destination=destination,
                    departure_date=dep_date, return_date=ret_date, range_days=2, passengers=1
                )
                if matrix and matrix.get("matrix"):
                    matrix_lines = ["📅 *Preços em Datas Alternativas:*"]
                    for cell in sorted(matrix["matrix"], key=lambda x: x["price"])[:5]:
                        dep_f = cell["departure_date"]
                        ret_f = cell.get("return_date")
                        row = f"   • {dep_f}" + (f" ↩ {ret_f}" if ret_f else "") + f": *${cell['price']}*"
                        if cell.get("is_cheapest"):
                            row += " 🏆"
                        matrix_lines.append(row)
                    await send_telegram_message("\n".join(matrix_lines), str(chat_id))

            # ── Agent pro tip ────────────────────────────────────
            pro_tip = (
                "🤖 *Dica do Agente:* Active o alerta 24/7 para monitorizar o preço desta rota!\n"
                "Use o botão *🔔 Ativar Alerta* e eu aviso-o quando o preço baixar."
            )
            await send_telegram_message(pro_tip, str(chat_id))

            state["status_msg"] = "Análise completa! 🎉"
            await edit_interactive_menu(str(chat_id), message_id, state)

        except Exception as search_err:
            logger.error(f"Flight search error: {search_err}", exc_info=True)
            await send_telegram_message("❌ Ocorreu um erro ao realizar a busca de voos.", str(chat_id))
            state["status_msg"] = f"Erro: {search_err}"
            await edit_interactive_menu(str(chat_id), message_id, state)


async def start_telegram_listener():
    """Background loop polling getUpdates from Telegram API."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("Telegram Listener: TELEGRAM_BOT_TOKEN not configured. Polling disabled.")
        return

    logger.info("Telegram Listener: Starting polling listener loop...")
    offset = 0
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    await asyncio.sleep(5)

    while True:
        try:
            params = {"offset": offset, "timeout": 15}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=25.0)

                if response.status_code == 200:
                    data = response.json()
                    updates = data.get("result", [])

                    for update in updates:
                        offset = update["update_id"] + 1

                        # Handle text messages
                        if "message" in update and "text" in update["message"]:
                            chat_id = update["message"]["chat"]["id"]
                            text = update["message"]["text"]
                            asyncio.create_task(handle_telegram_message(chat_id, text))

                        # Handle voice messages
                        elif "message" in update and "voice" in update["message"]:
                            chat_id = update["message"]["chat"]["id"]
                            file_id = update["message"]["voice"]["file_id"]
                            asyncio.create_task(handle_voice_message(chat_id, file_id))

                        # Handle button clicks
                        elif "callback_query" in update:
                            cq = update["callback_query"]
                            chat_id = cq["message"]["chat"]["id"]
                            message_id = cq["message"]["message_id"]
                            data_val = cq.get("data", "")
                            cq_id = cq.get("id", "")
                            asyncio.create_task(handle_callback_query(chat_id, message_id, data_val, cq_id))

                elif response.status_code == 409:
                    logger.warning("Telegram Listener: 409 Conflict — attempting to delete active webhook and retry...")
                    try:
                        del_url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true"
                        async with httpx.AsyncClient() as del_client:
                            del_resp = await del_client.get(del_url, timeout=10.0)
                            logger.info(f"Telegram Listener: deleteWebhook result: {del_resp.text}")
                    except Exception as del_err:
                        logger.error(f"Telegram Listener: Failed to delete webhook: {del_err}")
                    await asyncio.sleep(5)
                else:
                    logger.error(f"Telegram Listener: Status {response.status_code}: {response.text}")

        except httpx.RequestError as req_err:
            logger.debug(f"Telegram Listener: Network warning: {req_err}")
        except Exception as e:
            logger.error(f"Telegram Listener: Polling exception: {e}", exc_info=True)

        await asyncio.sleep(2)
