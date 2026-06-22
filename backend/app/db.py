import os
import logging
import libsql_client
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flights.db")

def get_db_client():
    url = os.environ.get("TURSO_DATABASE_URL")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN")
    if url and auth_token:
        # Use remote Turso database
        return libsql_client.create_client_sync(url=url, auth_token=auth_token)
    else:
        # Fallback to local SQLite if Turso not configured
        return libsql_client.create_client_sync(url=f"file:{DB_PATH}")

def init_db():
    logger.info("Initializing database...")
    client = get_db_client()
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                return_date TEXT,
                target_price REAL NOT NULL,
                last_price REAL,
                chat_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
    finally:
        client.close()

def create_alert(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str],
    target_price: float,
    chat_id: Optional[str] = None,
    last_price: Optional[float] = None
) -> int:
    client = get_db_client()
    try:
        result = client.execute("""
            INSERT INTO alerts (origin, destination, departure_date, return_date, target_price, chat_id, last_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, [origin.upper(), destination.upper(), departure_date, return_date, target_price, chat_id, last_price])
        
        alert_id = result.rows[0][0]
        logger.info(f"Created alert {alert_id} for {origin}->{destination} (Target: ${target_price})")
        return alert_id
    finally:
        client.close()

def get_active_alerts() -> List[Dict[str, Any]]:
    client = get_db_client()
    try:
        result = client.execute("SELECT * FROM alerts WHERE is_active = 1")
        return [dict(zip(result.columns, row)) for row in result.rows]
    finally:
        client.close()

def get_all_alerts() -> List[Dict[str, Any]]:
    client = get_db_client()
    try:
        result = client.execute("SELECT * FROM alerts ORDER BY created_at DESC")
        return [dict(zip(result.columns, row)) for row in result.rows]
    finally:
        client.close()

def update_alert_price(alert_id: int, last_price: float):
    client = get_db_client()
    try:
        client.execute("""
            UPDATE alerts
            SET last_price = ?, last_checked = CURRENT_TIMESTAMP
            WHERE id = ?
        """, [last_price, alert_id])
    finally:
        client.close()

def delete_alert(alert_id: int):
    client = get_db_client()
    try:
        client.execute("DELETE FROM alerts WHERE id = ?", [alert_id])
        logger.info(f"Deleted alert {alert_id}")
    finally:
        client.close()
