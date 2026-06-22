import asyncio
import os
import json
import logging
import httpx
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from .db import create_alert
from .telegram_service import send_interactive_menu, edit_interactive_menu, answer_callback, send_telegram_message
from .flight_search.manager import FlightSearchManager

logger = logging.getLogger(__name__)

# Global state mapping: chat_id -> active flight parameters dict
USER_STATES: Dict[int, Dict[str, Any]] = {}

flight_manager = FlightSearchManager()

async def parse_flight_query_with_gemini(text: str) -> Optional[Dict[str, Any]]:
    """
    NLP parser utilizing Gemini structured outputs to extract flight criteria.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Telegram Listener: GEMINI_API_KEY not configured. Cannot parse queries.")
        return None
        
    client = genai.Client(api_key=api_key)
    
    prompt = (
        "Você é o interpretador de linguagem natural do AeroMilhas. "
        "Analise a solicitação do usuário e extraia os seguintes dados em formato JSON:\n"
        "- origin: Código IATA de 3 letras do aeroporto de origem (ex: Curitiba -> CWB, São Paulo -> GRU).\n"
        "- destination: Código IATA de 3 letras do aeroporto de destino.\n"
        "- departure_date: Data de partida formatada como YYYY-MM-DD. Se o usuário fornecer formatos como DD/MM/AAAA, converta.\n"
        "- return_date: Data de retorno formatada como YYYY-MM-DD (nulo se não especificado).\n"
        "- target_price: Preço alvo máximo em USD (número). Se não especificado, use o padrão 1000.0.\n\n"
        f"Ano atual de referência: 2026.\n\n"
        f"Input do usuário: \"{text}\"\n\n"
        "Retorne EXCLUSIVAMENTE o JSON estruturado correspondente."
    )
    
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        parsed = json.loads(response.text)
        return parsed
    except Exception as e:
        logger.error(f"Telegram Listener: Failed to parse query with Gemini: {e}")
        return None

async def handle_telegram_message(chat_id: int, text: str):
    """Processes text message from Telegram client."""
    if text.startswith("/start"):
        welcome = (
            "👋 *Bem-vindo ao AeroMilhas AI Bot!* ✈️\n\n"
            "Eu sou o seu assistente de voos e preços 24h. "
            "Pode enviar as suas consultas de viagem diretamente aqui em linguagem natural!\n\n"
            "📝 *Exemplo*:\n"
            "`Curitiba - Lisboa 05/12/2027`\n"
            "`Quero voar de São Paulo para Nova Iorque ida a 15 de Outubro e volta a 22`\n\n"
            "Eu irei analisar a sua mensagem e dar-lhe-ei botões interativos para pesquisar ou monitorizar o preço 24/7!"
        )
        await send_telegram_message(welcome, str(chat_id))
        return
        
    await send_telegram_message("🤖 *Analisando a sua solicitação com IA...*", str(chat_id))
    
    extracted = await parse_flight_query_with_gemini(text)
    if not extracted or not extracted.get("origin") or not extracted.get("destination") or not extracted.get("departure_date"):
        err_msg = (
            "❌ *Não consegui compreender a sua pesquisa de voo.*\n\n"
            "Por favor, certifique-se de indicar a **origem**, o **destino** e a **data** do voo.\n"
            "Exemplo: `Lisboa para Paris a 10 de Setembro`"
        )
        await send_telegram_message(err_msg, str(chat_id))
        return
        
    # Store parameters in state
    state = {
        "origin": extracted["origin"].upper(),
        "destination": extracted["destination"].upper(),
        "departure_date": extracted["departure_date"],
        "return_date": extracted.get("return_date"),
        "target_price": extracted.get("target_price", 1000.0),
        "direct": False,
        "flexible": False
    }
    USER_STATES[chat_id] = state
    
    # Send configuration menu
    await send_interactive_menu(str(chat_id), state)

async def handle_callback_query(chat_id: int, message_id: int, data: str, callback_query_id: str):
    """Processes button clicks from Telegram inline keyboard."""
    state = USER_STATES.get(chat_id)
    if not state:
        await answer_callback(callback_query_id, "Sessão expirada. Envie uma nova mensagem.")
        return
        
    if data == "toggle_direct":
        state["direct"] = not state["direct"]
        await edit_interactive_menu(str(chat_id), message_id, state)
        await answer_callback(callback_query_id, f"Apenas Voo Direto: {'Ativo' if state['direct'] else 'Inativo'}")
        
    elif data == "toggle_flexible":
        state["flexible"] = not state["flexible"]
        await edit_interactive_menu(str(chat_id), message_id, state)
        await answer_callback(callback_query_id, f"Datas Flexíveis: {'Ativo' if state['flexible'] else 'Inativo'}")
        
    elif data == "save_alert":
        await answer_callback(callback_query_id, "Configurando Alerta 24/7...")
        
        # Save alert to SQLite
        try:
            alert_id = create_alert(
                origin=state["origin"],
                destination=state["destination"],
                departure_date=state["departure_date"],
                return_date=state["return_date"],
                target_price=state["target_price"],
                chat_id=str(chat_id)
            )
            
            # Update menu message status
            state["status_msg"] = f"Alerta 24/7 Ativado com Sucesso! (ID: #{alert_id}) 🔔"
            await edit_interactive_menu(str(chat_id), message_id, state)
            
            # Send separate success message
            success_text = (
                f"🔔 *Alerta 24/7 Ativado!* \n"
                f"Iremos monitorizar o voo *{state['origin']} ➡️ {state['destination']}* "
                f"e enviar-lhe-emos mensagens aqui se o preço baixar de *${state['target_price']}*."
            )
            await send_telegram_message(success_text, str(chat_id))
        except Exception as e:
            logger.error(f"Failed to register alert: {e}")
            await send_telegram_message(f"❌ Erro ao registar alerta: {e}", str(chat_id))
            
    elif data == "run_search":
        await answer_callback(callback_query_id, "Procurando voos...")
        
        # Update menu to show progress
        state["status_msg"] = "Pesquisando voos em tempo real... 🚀"
        await edit_interactive_menu(str(chat_id), message_id, state)
        
        try:
            # Query flight manager
            flights = await flight_manager.search_flights(
                origin=state["origin"],
                destination=state["destination"],
                departure_date=state["departure_date"],
                return_date=state["return_date"],
                passengers=1
            )
            
            if not flights:
                await send_telegram_message("❌ *Nenhum voo encontrado para esta rota e data.*", str(chat_id))
                state["status_msg"] = "Pesquisa concluída (Nenhum voo)."
                await edit_interactive_menu(str(chat_id), message_id, state)
                return
                
            # Filter direct if requested
            filtered = flights
            if state["direct"]:
                filtered = [f for f in flights if f["stops"] == 0]
                
            if not filtered:
                await send_telegram_message("❌ *Nenhum voo DIRETO encontrado para este dia.*", str(chat_id))
                state["status_msg"] = "Pesquisa concluída (Sem voos diretos)."
                await edit_interactive_menu(str(chat_id), message_id, state)
                return
                
            # Send top 3 flight results
            lines = [
                f"🔍 *AeroMilhas - Melhores Voos Encontrados ({len(filtered)} opções)*:",
                f"✈️ *{state['origin']} ➡️ {state['destination']}* (" + ("Ida e Volta" if state["return_date"] else "Só Ida") + ")",
                ""
            ]
            
            for i, flight in enumerate(filtered[:3]):
                out = flight["outbound"]
                ret_info = flight.get("inbound")
                
                stops_text = "Direto ✅" if flight["stops"] == 0 else f"{flight['stops']} conexão(ões) ⚠️"
                
                flight_lines = [
                    f"*{i+1}. Preço: ${flight['price']}* ({stops_text})",
                    f"   • *Ida*: {out['airline']} | {out['departure_time']} ➡️ {out['arrival_time']} ({out['cabin']})"
                ]
                
                if ret_info:
                    flight_lines.append(
                        f"   • *Volta*: {ret_info['airline']} | {ret_info['departure_time']} ➡️ {ret_info['arrival_time']} ({ret_info['cabin']})"
                    )
                flight_lines.append("")
                lines.extend(flight_lines)
                
            await send_telegram_message("\n".join(lines), str(chat_id))
            
            # Check price matrix if flexible was requested
            if state["flexible"]:
                await send_telegram_message("📅 *Pesquisando matriz de datas flexíveis...*", str(chat_id))
                matrix = await flight_manager.get_price_matrix(
                    origin=state["origin"],
                    destination=state["destination"],
                    departure_date=state["departure_date"],
                    return_date=state["return_date"],
                    range_days=2, # +/- 2 days for cleaner Telegram display
                    passengers=1
                )
                
                if matrix and matrix.get("matrix"):
                    matrix_lines = ["📅 *Melhores Preços Alternativos (Ida/Volta)*:"]
                    # Sort matrix by cheapest
                    sorted_cells = sorted(matrix["matrix"], key=lambda x: x["price"])
                    
                    for cell in sorted_cells[:4]:
                        dep_f = cell["departure_date"]
                        ret_f = cell.get("return_date")
                        row = f"   • {dep_f}" + (f" regresso {ret_f}" if ret_f else "") + f": *${cell['price']}*"
                        if cell.get("is_cheapest"):
                            row += " 🏆 *Mais Barato!*"
                        matrix_lines.append(row)
                        
                    await send_telegram_message("\n".join(matrix_lines), str(chat_id))
                    
            # Reset status message
            state["status_msg"] = "Pesquisa concluída! 🎉"
            await edit_interactive_menu(str(chat_id), message_id, state)
            
        except Exception as search_err:
            logger.error(f"Telegram Listener: Flight search error: {search_err}")
            await send_telegram_message("❌ Ocorreu um erro ao realizar a busca de voos.", str(chat_id))
            state["status_msg"] = f"Erro na pesquisa: {search_err}"
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
    
    # Wait a few seconds for FastAPI startup to complete
    await asyncio.sleep(5)
    
    while True:
        try:
            params = {
                "offset": offset,
                "timeout": 15
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=25.0)
                if response.status_code == 200:
                    data = response.json()
                    updates = data.get("result", [])
                    
                    for update in updates:
                        # Bump offset
                        offset = update["update_id"] + 1
                        
                        # Handle text messages
                        if "message" in update and "text" in update["message"]:
                            chat_id = update["message"]["chat"]["id"]
                            text = update["message"]["text"]
                            
                            # Fire and forget update processing to keep polling responsive
                            asyncio.create_task(handle_telegram_message(chat_id, text))
                            
                        # Handle button clicks
                        elif "callback_query" in update:
                            cq = update["callback_query"]
                            chat_id = cq["message"]["chat"]["id"]
                            message_id = cq["message"]["message_id"]
                            data_val = cq.get("data", "")
                            cq_id = cq.get("id", "")
                            
                            asyncio.create_task(handle_callback_query(chat_id, message_id, data_val, cq_id))
                elif response.status_code == 409:
                    logger.error("Telegram Listener: Webhook is active. Disabling listener.")
                    # A web hook is active on the bot. Stop listener to prevent CPU loop.
                    break
                else:
                    logger.error(f"Telegram Listener: Failed to fetch updates. Status {response.status_code}: {response.text}")
                    
        except httpx.RequestError as req_err:
            # Network timeouts or connection issues are normal in polling loops, log and sleep
            logger.debug(f"Telegram Listener: Network warning: {req_err}")
        except Exception as e:
            logger.error(f"Telegram Listener: Polling exception: {e}", exc_info=True)
            
        await asyncio.sleep(2)
