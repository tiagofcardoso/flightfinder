import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# Load local environment variables
load_dotenv()

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from app.flight_search.manager import FlightSearchManager
from app.agent.agent import FlightAgent
from app.db import init_db, create_alert, get_all_alerts, delete_alert
from app.scheduler import start_scheduler_loop
from app.telegram_listener import start_telegram_listener

class AlertRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    target_price: float
    chat_id: Optional[str] = None

async def start_keep_alive_loop():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("Keep-alive loop disabled: RENDER_EXTERNAL_URL not found.")
        return
    
    if not url.endswith("/"):
        url += "/"
    url += "api/health"
    
    logger.info(f"Keep-alive loop started. Pinging {url} every 14 minutes.")
    import httpx
    while True:
        await asyncio.sleep(14 * 60) # 14 minutes
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, timeout=10.0)
                logger.info(f"Keep-alive ping successful: {res.status_code}")
        except Exception as e:
            logger.error(f"Keep-alive ping failed: {e}")

# Life cycle event manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Setup database and run background monitoring loop
    init_db()
    scheduler_task = asyncio.create_task(start_scheduler_loop())
    logger.info("FastAPI Lifespan: Background scheduler task launched successfully.")
    
    listener_task = asyncio.create_task(start_telegram_listener())
    logger.info("FastAPI Lifespan: Telegram updates listener task launched successfully.")
    
    keep_alive_task = asyncio.create_task(start_keep_alive_loop())
    logger.info("FastAPI Lifespan: Keep-alive task launched successfully.")
    
    yield
    
    # Shutdown: Cancel tasks gracefully
    logger.info("FastAPI Lifespan: Cancelling background tasks...")
    scheduler_task.cancel()
    listener_task.cancel()
    keep_alive_task.cancel()
    
    try:
        await asyncio.gather(scheduler_task, listener_task, keep_alive_task, return_exceptions=True)
    except Exception as e:
        logger.error(f"FastAPI Lifespan: Task cancellation exception: {e}")
    logger.info("FastAPI Lifespan: Tasks cancelled cleanly.")

app = FastAPI(
    title="AeroMilhas AI Flight Finder Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Setup CORS for Next.js frontend communication (typically port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

search_manager = FlightSearchManager()
agent_instance = FlightAgent()

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "provider": "serpapi" if search_manager.active_provider == search_manager.serpapi_provider else ("amadeus" if search_manager.active_provider == search_manager.amadeus_provider else ("kiwi" if search_manager.active_provider == search_manager.kiwi_provider else "mock"))}

@app.get("/api/airports")
async def get_airports(q: str = Query(..., min_length=1)):
    """Fetch airport autocomplete suggestions."""
    suggestions = await search_manager.get_airport_suggestions(q)
    return {"suggestions": suggestions}

@app.get("/api/flights")
async def search_flights_endpoint(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    max_price: Optional[float] = None
):
    """Direct flight search endpoint."""
    try:
        flights = await search_manager.search_flights(
            origin, destination, departure_date, return_date, passengers, max_price
        )
        return {"flights": flights}
    except Exception as e:
        logger.error(f"Flight search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/matrix")
async def get_price_matrix_endpoint(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    range_days: int = 3,
    passengers: int = 1
):
    """Price matrix comparison endpoint."""
    try:
        matrix = await search_manager.get_price_matrix(
            origin, destination, departure_date, return_date, range_days, passengers
        )
        return {"matrix": matrix}
    except Exception as e:
        logger.error(f"Matrix generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Active alerts APIs
@app.get("/api/alerts")
async def get_alerts_endpoint():
    """Retrieve all price monitoring alerts."""
    try:
        alerts = get_all_alerts()
        return {"alerts": alerts}
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/alerts")
async def create_alert_endpoint(alert: AlertRequest):
    """Manually register a price alert."""
    from app.scheduler import check_alerts
    try:
        alert_id = create_alert(
            origin=alert.origin,
            destination=alert.destination,
            departure_date=alert.departure_date,
            return_date=alert.return_date,
            target_price=alert.target_price,
            chat_id=alert.chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        )
        # Trigger an immediate background check of prices for this new alert
        asyncio.create_task(check_alerts())
        return {"status": "success", "alert_id": alert_id}
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/alerts/{alert_id}")
async def delete_alert_endpoint(alert_id: int):
    """Remove/deactivate a price alert."""
    try:
        delete_alert(alert_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")
    
    try:
        while True:
            # Expecting message format:
            # { "message": "user input text", "history": [{"role": "user"|"model", "content": "text"}] }
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            user_msg = payload.get("message", "")
            history = payload.get("history", [])
            
            logger.info(f"Received message from user: '{user_msg}'")
            
            # Local async event sender function
            async def ws_event_sender(event_type: str, data_payload: Any) -> None:
                try:
                    await websocket.send_json({
                        "type": event_type,
                        "data": data_payload
                    })
                except Exception as send_err:
                    logger.error(f"Error sending message over WebSocket: {send_err}")
            
            # Execute Agent execution loop
            await agent_instance.execute_agent_loop(
                history=history,
                new_message=user_msg,
                on_event=ws_event_sender
            )
            
            # Signal frontend that processing is complete
            await ws_event_sender("agent_done", {})
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected gracefully.")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    # Run locally on port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

