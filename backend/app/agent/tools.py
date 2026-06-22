import logging
from typing import List, Dict, Any, Optional, Callable, Coroutine
from contextvars import ContextVar

from ..flight_search.manager import FlightSearchManager

logger = logging.getLogger(__name__)

# Context variable to hold WebSocket event emitter for the current request
# The callback has signature: async def callback(event_type: str, data: Any) -> None
ws_event_callback: ContextVar[Optional[Callable[[str, Any], Coroutine[Any, Any, None]]]] = ContextVar(
    "ws_event_callback", default=None
)

manager = FlightSearchManager()

async def resolve_airport_code(city_name: str) -> List[Dict[str, str]]:
    """
    Find IATA codes and details of airports matching a city name or query.
    
    Args:
        city_name: The name of the city, country, or airport (e.g., "São Paulo", "London", "Heathrow").
        
    Returns:
        A list of airport dictionaries containing code, city, country, and name.
    """
    logger.info(f"Agent Tool resolve_airport_code called with query: '{city_name}'")
    
    # Notify frontend of tool call
    callback = ws_event_callback.get()
    if callback:
        await callback("agent_thinking", {"status": f"Resolving airport codes for '{city_name}'..."})
        
    results = await manager.get_airport_suggestions(city_name)
    return results

async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    max_price: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Search for flights between two airports on a specific departure date (and optional return date).
    
    Args:
        origin: The 3-letter IATA code of the origin airport (e.g., "GRU", "LIS").
        destination: The 3-letter IATA code of the destination airport (e.g., "JFK", "CDG").
        departure_date: Departure date in YYYY-MM-DD format (e.g., "2026-10-15").
        return_date: Optional return date in YYYY-MM-DD format for round trips.
        passengers: Number of adult passengers (default is 1).
        max_price: Optional maximum price filter in USD.
        
    Returns:
        A list of flight offers sorted by price.
    """
    logger.info(f"Agent Tool search_flights called: {origin} -> {destination} on {departure_date} (return: {return_date})")
    
    callback = ws_event_callback.get()
    if callback:
        msg = f"Searching flights from {origin} to {destination} on {departure_date}"
        if return_date:
            msg += f" returning {return_date}"
        await callback("agent_thinking", {"status": msg + "..."})
        
    results = await manager.search_flights(
        origin, destination, departure_date, return_date, passengers, max_price
    )
    
    if callback:
        await callback("flight_results", results)
        
    return results

async def get_price_matrix(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    range_days: int = 3,
    passengers: int = 1
) -> Dict[str, Any]:
    """
    Retrieve a price matrix grid containing flights prices for alternate departure/return dates.
    Use this to see if shifting the travel dates by up to 3 days (before or after) saves money.
    
    Args:
        origin: The 3-letter IATA code of the origin airport (e.g., "GRU").
        destination: The 3-letter IATA code of the destination airport (e.g., "JFK").
        departure_date: Target departure date in YYYY-MM-DD format.
        return_date: Target return date in YYYY-MM-DD format (for round trips).
        range_days: The number of days to look before/after the target dates (default is 3).
        passengers: Number of adult passengers (default is 1).
        
    Returns:
        A dictionary containing lists of departure/return dates and a list of matrix cells with prices.
    """
    logger.info(f"Agent Tool get_price_matrix called: {origin} -> {destination} around {departure_date} (+/- {range_days} days)")
    
    callback = ws_event_callback.get()
    if callback:
        await callback("agent_thinking", {"status": f"Compiling flexible price matrix (+/- {range_days} days) for travel dates..."})
        
    results = await manager.get_price_matrix(
        origin, destination, departure_date, return_date, range_days, passengers
    )
    
    if callback:
        await callback("price_matrix", results)
        
    return results

async def create_price_alert(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    target_price: float = 1000.0
) -> Dict[str, Any]:
    """
    Create a 24/7 background price monitor/alert for a route and date range.
    Whenever the price drops below the previous check, or falls below the target_price,
    an alert is sent to the user via Telegram.
    
    Args:
        origin: The 3-letter IATA code of the origin airport (e.g., "GRU", "LIS").
        destination: The 3-letter IATA code of the destination airport (e.g., "JFK", "ORY").
        departure_date: Departure date in YYYY-MM-DD format (e.g., "2026-10-15").
        return_date: Optional return date in YYYY-MM-DD format for round trips.
        target_price: Maximum budget price in USD. If price falls below this, the user is alerted.
        
    Returns:
        A dictionary with success status and details of the registered alert.
    """
    import os
    from ..db import create_alert
    
    logger.info(f"Agent Tool create_price_alert called: {origin} -> {destination} on {departure_date} (Target: ${target_price})")
    
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    callback = ws_event_callback.get()
    if callback:
        await callback("agent_thinking", {"status": f"Registando alerta de preço no banco de dados para {origin}->{destination}..."})
        
    try:
        alert_id = create_alert(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            target_price=target_price,
            chat_id=chat_id
        )
        
        # Trigger an immediate background check of prices for this new alert
        from ..scheduler import check_alerts
        import asyncio
        asyncio.create_task(check_alerts())
        
        # Trigger reload of alerts in the UI
        if callback:
            await callback("alert_registered", {
                "id": alert_id,
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "target_price": target_price
            })
            
        return {
            "status": "success",
            "alert_id": alert_id,
            "message": f"Alerta #{alert_id} para {origin.upper()} -> {destination.upper()} registado com sucesso! (Preço alvo: ${target_price})"
        }
    except Exception as e:
        logger.error(f"Failed to create alert: {e}")
        return {
            "status": "error",
            "message": f"Não foi possível registar o alerta de preço: {e}"
        }

