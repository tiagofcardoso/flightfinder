import os
import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

async def send_telegram_message(text: str, chat_id: Optional[str] = None) -> bool:
    """
    Sends a Markdown-formatted message to a Telegram chat using the configured Telegram Bot.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token:
        logger.warning("Telegram Service: TELEGRAM_BOT_TOKEN is not set. Cannot send message.")
        return False
        
    if not target_chat_id:
        logger.warning("Telegram Service: Target Chat ID (chat_id) is not set. Cannot send message.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Telegram Service: Message successfully sent to chat {target_chat_id}")
                return True
            else:
                logger.error(f"Telegram Service: Failed to send message. Status {response.status_code}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Telegram Service: Request exception: {e}")
        return False

async def notify_price_drop(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str],
    old_price: Optional[float],
    new_price: float,
    target_price: float,
    chat_id: Optional[str] = None,
    booking_url: Optional[str] = None
) -> bool:
    """
    Sends a structured price drop notification over Telegram.
    """
    route = f"✈️ *{origin} ➡️ {destination}*"
    dates = f"📅 *Ida*: {departure_date}"
    if return_date:
        dates += f" | *Volta*: {return_date}"
        
    # Format message
    lines = [
        "🚨 *[AERO-MILHAS] ALERTA DE PREÇO* 🚨",
        "",
        route,
        dates,
        ""
    ]
    
    if old_price:
        savings = old_price - new_price
        lines.append(f"📉 O preço baixou de: ~~${old_price}~~ para *${new_price}*!")
        if savings > 0:
            lines.append(f"💰 *Poupança de: ${round(savings, 2)}*! 🎉")
    else:
        lines.append(f"💵 Preço encontrado: *${new_price}*")
        
    lines.append(f"🎯 Orçamento Alvo: *${target_price}*")
    
    if new_price <= target_price:
        lines.append("\n🔥 *O preço está ABAIXO do seu orçamento alvo! Garanta já!* 🔥")

    if booking_url:
        lines.append(f"\n🔗 [👆 Abrir no Google Flights]({booking_url})")
    else:
        lines.append("\n🔗 Abra o dashboard para ver os voos disponíveis.")
    
    msg_text = "\n".join(lines)
    return await send_telegram_message(msg_text, chat_id)

async def send_interactive_menu(chat_id: str, params: Dict[str, Any]) -> Optional[int]:
    """
    Sends an interactive flight search menu to the user with inline keyboard buttons acting as checkboxes.
    Returns the message ID of the sent menu.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return None
        
    origin = params.get("origin", "").upper()
    dest = params.get("destination", "").upper()
    dep = params.get("departure_date", "")
    ret = params.get("return_date")
    direct = params.get("direct", False)
    flexible = params.get("flexible", False)
    target = params.get("target_price", 1000.0)
    
    text = (
        "✈️ *AeroMilhas - Configuração de Busca* ✈️\n\n"
        f"📍 *Rota*: {origin} ➡️ {dest}\n"
        f"📅 *Ida*: {dep}" + (f" | *Volta*: {ret}" if ret else " (Só ida)") + "\n"
        f"💰 *Orçamento*: ${target}\n\n"
        "Configure as suas preferências abaixo nos botões e clique em *Pesquisar Voos* para ver os resultados no Telegram:"
    )
    
    # Pack inline keyboard buttons
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"{'✅' if direct else '⬜'} Apenas Voo Direto", "callback_data": "toggle_direct"},
                {"text": f"{'✅' if flexible else '⬜'} Datas Flexíveis", "callback_data": "toggle_flexible"}
            ],
            [
                {"text": "🔔 Ativar Alerta 24/7", "callback_data": "save_alert"},
                {"text": "🚀 Pesquisar Voos", "callback_data": "run_search"}
            ]
        ]
    }
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                message_id = data.get("result", {}).get("message_id")
                return message_id
            else:
                logger.error(f"Failed to send interactive menu: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error in send_interactive_menu: {e}")
        return None

async def edit_interactive_menu(chat_id: str, message_id: int, params: Dict[str, Any]) -> bool:
    """
    Edits an existing interactive flight menu to update checkboxes or statuses.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
        
    origin = params.get("origin", "").upper()
    dest = params.get("destination", "").upper()
    dep = params.get("departure_date", "")
    ret = params.get("return_date")
    direct = params.get("direct", False)
    flexible = params.get("flexible", False)
    target = params.get("target_price", 1000.0)
    status_msg = params.get("status_msg", "")
    
    text = (
        "✈️ *AeroMilhas - Configuração de Busca* ✈️\n\n"
        f"📍 *Rota*: {origin} ➡️ {dest}\n"
        f"📅 *Ida*: {dep}" + (f" | *Volta*: {ret}" if ret else " (Só ida)") + "\n"
        f"💰 *Orçamento*: ${target}\n\n"
    )
    if status_msg:
        text += f"ℹ️ *Status*: {status_msg}\n\n"
        
    text += "Configure as suas preferências abaixo nos botões e clique em *Pesquisar Voos* para ver os resultados no Telegram:"
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"{'✅' if direct else '⬜'} Apenas Voo Direto", "callback_data": "toggle_direct"},
                {"text": f"{'✅' if flexible else '⬜'} Datas Flexíveis", "callback_data": "toggle_flexible"}
            ],
            [
                {"text": "🔔 Ativar Alerta 24/7", "callback_data": "save_alert"},
                {"text": "🚀 Pesquisar Voos", "callback_data": "run_search"}
            ]
        ]
    }
    
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Error in edit_interactive_menu: {e}")
        return False

async def answer_callback(callback_query_id: str, text: Optional[str] = None) -> bool:
    """
    Sends callback answer back to Telegram to complete button click loading animation.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id
    }
    if text:
        payload["text"] = text
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=5.0)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")
        return False

