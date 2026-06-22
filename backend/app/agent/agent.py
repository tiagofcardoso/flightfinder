import os
import logging
from typing import List, Dict, Any, Callable, Coroutine, Optional
from google import genai
from google.genai import types

from .prompts import SYSTEM_PROMPT
from .tools import resolve_airport_code, search_flights, get_price_matrix, create_price_alert, ws_event_callback

logger = logging.getLogger(__name__)

class FlightAgent:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = None
        
        if self.api_key:
            try:
                # Initialize the modern google-genai Client
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize google-genai Client: {e}")
        else:
            logger.warning("FlightAgent: GEMINI_API_KEY is not set in environment variables! Dynamic prompt will guide the user.")

    async def execute_agent_loop(
        self,
        history: List[Dict[str, Any]],
        new_message: str,
        on_event: Callable[[str, Any], Coroutine[Any, Any, None]]
    ) -> str:
        """
        Executes the agent loop using google-genai.
        """
        # Set the WS event callback for the active async context
        ws_event_callback.set(on_event)
        
        # Check if client is initialized, try re-initializing if API key is set later
        if not self.client:
            self.api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
            if self.api_key:
                try:
                    self.client = genai.Client(api_key=self.api_key)
                except Exception as e:
                    logger.error(f"Failed to initialize google-genai Client: {e}")
            
            if not self.client:
                error_msg = (
                    "O Agente AeroMilhas não pôde ser iniciado porque a chave **GEMINI_API_KEY** não está configurada.\n\n"
                    "**Como resolver:**\n"
                    "1. Abra o arquivo [backend/.env](file:///c:/Users/tiago/OneDrive/Documents/Developments/FlightFinder/backend/.env)\n"
                    "2. Adicione sua chave: `GEMINI_API_KEY=sua_chave_aqui`\n"
                    "3. Reinicie o servidor backend."
                )
                await on_event("agent_message", {"content": error_msg})
                return error_msg
        
        # Convert history format to google-genai content structures
        gemini_history = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.get("content", ""))]
            ))
            
        await on_event("agent_thinking", {"status": "Iniciando análise..."})
        
        try:
            # Build search/system config including tools
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[resolve_airport_code, search_flights, get_price_matrix, create_price_alert]
            )
            
            # Create async chat session
            chat = self.client.aio.chats.create(
                model="gemini-2.5-flash",
                history=gemini_history,
                config=config
            )
            
            # Send message (automatic function calling is enabled by default)
            response = await chat.send_message(new_message)
            final_text = response.text
            
            # Send the final response to the client
            await on_event("agent_message", {"content": final_text})
            return final_text
            
        except Exception as e:
            logger.error(f"Error in Gemini agent loop: {e}")
            error_msg = (
                f"Desculpe, ocorreu um erro ao processar sua busca. "
                f"Por favor, verifique se a chave GEMINI_API_KEY está configurada no backend. (Erro: {e})"
            )
            await on_event("agent_message", {"content": error_msg})
            return error_msg

