"""Costco Gas Price API and Database Storage Module.

Fetches gas prices from Costco's AjaxGetGasPricesService and manages
location configurations and local historical logging in SQLite.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCATIONS_FILE = BASE_DIR / "default_locations.json"
LOCATIONS_FILE = BASE_DIR / "locations.json"
DB_FILE = BASE_DIR / "gas_prices.db"

# Default DFW locations matching the user's initial Apps Script
DEFAULT_LOCATIONS = {
    "664": "East Plano Costco",
    "683": "Lewisville Costco",
    "684": "West Plano Costco",
    "1097": "Frisco Costco",
    "1284": "McKinney Costco",
    "1694": "Prosper Costco",
    "1739": "Allen Costco",
    "1645": "Celina Costco",
}

# Optional presets that users can quickly add
POPULAR_DFW_PRESETS = {
    "636": "Dallas (Coit Rd) Costco",
    "668": "Arlington Costco",
    "1173": "Fort Worth Costco",
    "1184": "Dallas Business Center",
}

REQUEST_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}


def load_locations() -> Dict[str, str]:
    """Load the current list of locations (warehouse ID -> store name)."""
    if LOCATIONS_FILE.exists():
        try:
            with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass

    if DEFAULT_LOCATIONS_FILE.exists():
        try:
            with open(DEFAULT_LOCATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass

    return DEFAULT_LOCATIONS.copy()


def save_locations(locations: Dict[str, str]) -> None:
    """Save custom locations dictionary to locations.json."""
    with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(locations, f, indent=2)


def reset_locations() -> Dict[str, str]:
    """Reset locations to default configuration."""
    locations = DEFAULT_LOCATIONS.copy()
    save_locations(locations)
    return locations


def fetch_single_gas_price(warehouse_id: str, store_name: str = "", timeout: int = 10) -> Dict[str, Any]:
    """Fetch live gas prices for a single Costco warehouse ID."""
    wid_str = str(warehouse_id).strip()
    url = f"https://www.costco.com/AjaxGetGasPricesService?warehouseid={wid_str}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        response.raise_for_status()
        text_content = response.text.strip()
        data = json.loads(text_content)

        warehouse_data = data.get(wid_str)

        if warehouse_data is not None and isinstance(warehouse_data, dict) and warehouse_data:
            regular_val = warehouse_data.get("regular")
            premium_val = warehouse_data.get("premium")

            reg_float = float(regular_val) if regular_val and regular_val != "N/A" else None
            prem_float = float(premium_val) if premium_val and premium_val != "N/A" else None

            return {
                "warehouse_id": wid_str,
                "store_name": store_name or f"Costco #{wid_str}",
                "regular": reg_float,
                "premium": prem_float,
                "status": "Success",
                "updated_at": now_str,
                "raw": warehouse_data,
            }
        else:
            return {
                "warehouse_id": wid_str,
                "store_name": store_name or f"Costco #{wid_str}",
                "regular": None,
                "premium": None,
                "status": "No gas station / No data found",
                "updated_at": now_str,
                "raw": {},
            }
    except Exception as err:
        return {
            "warehouse_id": wid_str,
            "store_name": store_name or f"Costco #{wid_str}",
            "regular": None,
            "premium": None,
            "status": f"Error: {err}",
            "updated_at": now_str,
            "raw": {},
        }


def fetch_all_gas_prices(
    locations: Optional[Dict[str, str]] = None,
    max_workers: int = 6,
) -> List[Dict[str, Any]]:
    """Fetch gas prices for all specified locations concurrently."""
    if locations is None:
        locations = load_locations()

    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_wid = {
            executor.submit(fetch_single_gas_price, wid, name): wid
            for wid, name in locations.items()
        }
        for future in concurrent.futures.as_completed(future_to_wid):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                wid = future_to_wid[future]
                results.append({
                    "warehouse_id": wid,
                    "store_name": locations.get(wid, wid),
                    "regular": None,
                    "premium": None,
                    "status": f"Failed: {e}",
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "raw": {},
                })

    # Sort results by store name for consistency
    results.sort(key=lambda x: x["store_name"])
    return results


# ---------------------------------------------------------
# Database Storage (SQLite)
# ---------------------------------------------------------

def init_db() -> None:
    """Initialize SQLite database for historical gas prices."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gas_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                store_name TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,
                regular_price REAL,
                premium_price REAL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_timestamp
            ON gas_price_history (timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_wid
            ON gas_price_history (warehouse_id)
        """)
        conn.commit()


def log_prices_to_db(prices_list: List[Dict[str, Any]]) -> int:
    """Append a batch of fetched prices to SQLite database history."""
    init_db()
    rows_to_insert = []
    for item in prices_list:
        if item.get("regular") is not None or item.get("premium") is not None:
            rows_to_insert.append((
                item.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                item.get("store_name", ""),
                item.get("warehouse_id", ""),
                item.get("regular"),
                item.get("premium"),
            ))

    if not rows_to_insert:
        return 0

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO gas_price_history (timestamp, store_name, warehouse_id, regular_price, premium_price)
            VALUES (?, ?, ?, ?, ?)
        """, rows_to_insert)
        conn.commit()

    return len(rows_to_insert)


def get_price_history(days: Optional[int] = None, warehouse_ids: Optional[List[str]] = None) -> pd.DataFrame:
    """Retrieve historical gas prices as a Pandas DataFrame."""
    init_db()
    query = """
        SELECT timestamp, store_name, warehouse_id, regular_price, premium_price
        FROM gas_price_history
        WHERE 1=1
    """
    params: List[Any] = []

    if days is not None and days > 0:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        query += " AND timestamp >= ?"
        params.append(cutoff)

    if warehouse_ids:
        placeholders = ",".join("?" for _ in warehouse_ids)
        query += f" AND warehouse_id IN ({placeholders})"
        params.extend(warehouse_ids)

    query += " ORDER BY timestamp ASC"

    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df


def clear_price_history() -> None:
    """Clear all historical price records."""
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gas_price_history")
        conn.commit()
