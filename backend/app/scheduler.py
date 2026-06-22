import asyncio
import os
import logging
from typing import Optional

from .db import get_active_alerts, update_alert_price
from .flight_search.manager import FlightSearchManager
from .telegram_service import notify_price_drop

logger = logging.getLogger(__name__)

# Search manager is instantiated globally
manager = FlightSearchManager()

async def check_alerts():
    """
    Query all active price alerts, fetch current prices,
    compare them with history and targets, and notify via Telegram.
    """
    logger.info("Scheduler: Starting price alerts check...")
    try:
        active_alerts = get_active_alerts()
    except Exception as db_err:
        logger.error(f"Scheduler: Failed to read from DB: {db_err}")
        return
        
    if not active_alerts:
        logger.info("Scheduler: No active alerts to check.")
        return
        
    for alert in active_alerts:
        alert_id = alert["id"]
        origin = alert["origin"]
        destination = alert["destination"]
        dep_date = alert["departure_date"]
        ret_date = alert.get("return_date")
        target_price = alert["target_price"]
        last_price = alert.get("last_price")
        chat_id = alert.get("chat_id")
        
        logger.info(f"Scheduler: Checking Alert #{alert_id}: {origin}->{destination} on {dep_date} (Target: ${target_price}, Prev: ${last_price})")
        
        try:
            # Query the search manager
            flights = await manager.search_flights(
                origin=origin,
                destination=destination,
                departure_date=dep_date,
                return_date=ret_date,
                passengers=1
            )
            
            if not flights:
                logger.warning(f"Scheduler: No flights found for Alert #{alert_id} ({origin}->{destination})")
                continue
                
            cheapest_offer = flights[0]
            current_price = float(cheapest_offer["price"])
            logger.info(f"Scheduler: Alert #{alert_id} current cheapest price: ${current_price}")
            
            # Check conditions to send alert:
            # 1. Price is lower than previous price checked (price drop)
            # 2. Or, first check (last_price is None) AND price is below target budget
            should_alert = False
            
            if last_price is None:
                if current_price <= target_price:
                    should_alert = True
                    logger.info(f"Scheduler: Alert #{alert_id} matches budget on first run.")
            else:
                if current_price < last_price:
                    should_alert = True
                    logger.info(f"Scheduler: Alert #{alert_id} price drop detected: ${last_price} -> ${current_price}")
                elif current_price <= target_price and last_price > target_price:
                    # Price crossed target budget line downwards
                    should_alert = True
                    logger.info(f"Scheduler: Alert #{alert_id} crossed target budget: ${current_price} <= ${target_price}")
            
            # Trigger notification
            if should_alert:
                await notify_price_drop(
                    origin=origin,
                    destination=destination,
                    departure_date=dep_date,
                    return_date=ret_date,
                    old_price=last_price,
                    new_price=current_price,
                    target_price=target_price,
                    chat_id=chat_id
                )
                
            # Always update DB state with latest price
            update_alert_price(alert_id, current_price)
            
        except Exception as e:
            logger.error(f"Scheduler: Error checking Alert #{alert_id}: {e}", exc_info=True)

async def start_scheduler_loop():
    """Infinite background loop runner."""
    # Read interval from env, default to 1800 seconds (30 minutes)
    interval = int(os.environ.get("MONITOR_INTERVAL_SECONDS", 1800))
    logger.info(f"Scheduler: Starting daemon loop. Check interval: {interval} seconds.")
    
    # Wait a few seconds for FastAPI startup to complete
    await asyncio.sleep(5)
    
    while True:
        try:
            await check_alerts()
        except Exception as loop_err:
            logger.error(f"Scheduler: Loop iteration encountered error: {loop_err}")
            
        logger.info(f"Scheduler: Sleeping for {interval} seconds.")
        await asyncio.sleep(interval)
