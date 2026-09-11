"""Costco Gas Price API and Database Storage Module.

Fetches gas prices from Costco's AjaxGetGasPricesService, maintains warehouse
directories from warehouserunner.com/stores, provides offline geospatial zip
code lookups via pgeocode, and manages local historical logging in SQLite.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import pgeocode
import requests

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCATIONS_FILE = BASE_DIR / "default_locations.json"
LOCATIONS_FILE = BASE_DIR / "locations.json"
ALL_STORES_FILE = BASE_DIR / "costco_all_stores.json"
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

# ---------------------------------------------------------
# Warehouse Directory & Geocoding
# ---------------------------------------------------------

_geo_nominatim: Optional[pgeocode.Nominatim] = None


def get_nominatim() -> pgeocode.Nominatim:
    """Lazy initialize pgeocode US nominatim instance."""
    global _geo_nominatim
    if _geo_nominatim is None:
        _geo_nominatim = pgeocode.Nominatim("us")
    return _geo_nominatim


def haversine_np(
    lat1: float, lon1: float, lat2_array: np.ndarray, lon2_array: np.ndarray
) -> np.ndarray:
    """Vectorized Haversine distance in miles."""
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2_array), np.radians(lon2_array)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    )
    c = 2 * np.arcsin(np.sqrt(a))
    miles = 3958.8 * c
    return miles


def sync_all_stores_from_warehouserunner() -> List[Dict[str, Any]]:
    """Fetch all 640+ Costco warehouses from warehouserunner.com/stores and geocode."""
    url = "https://app.warehouserunner.com/stores"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    text = resp.text

    chunks = re.findall(r"self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)", text, re.DOTALL)
    full_str = ""
    for c in chunks:
        try:
            full_str += bytes(c, "utf-8").decode("unicode_escape")
        except Exception:
            full_str += c

    start = full_str.find('[{"id":')
    end = full_str.find("}]", start)
    stores: List[Dict[str, Any]] = []
    while end != -1:
        try:
            stores = json.loads(full_str[start : end + 2])
            break
        except Exception:
            end = full_str.find("}]", end + 1)

    if not stores:
        raise ValueError("Could not extract store list from warehouserunner response.")

    df = pd.DataFrame(stores)
    df["zip_5"] = df["zip_code"].astype(str).str[:5]

    nomi = get_nominatim()
    geo_info = nomi.query_postal_code(df["zip_5"].tolist())
    df["latitude"] = geo_info["latitude"].values
    df["longitude"] = geo_info["longitude"].values

    records = df.to_dict(orient="records")
    with open(ALL_STORES_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    return records


def get_all_stores() -> List[Dict[str, Any]]:
    """Load cached all-stores directory, fetching from source if missing."""
    if ALL_STORES_FILE.exists():
        try:
            with open(ALL_STORES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass

    return sync_all_stores_from_warehouserunner()


def lookup_zipcode(zipcode: str) -> Optional[Dict[str, Any]]:
    """Look up latitude, longitude, city, and state for a US 5-digit ZIP code."""
    cleaned_zip = re.sub(r"[^\d]", "", str(zipcode))[:5]
    if len(cleaned_zip) < 5:
        return None

    # Try local pgeocode first
    nomi = get_nominatim()
    res = nomi.query_postal_code(cleaned_zip)

    if pd.notnull(res.get("latitude")) and pd.notnull(res.get("longitude")):
        return {
            "postal_code": cleaned_zip,
            "city": str(res.get("place_name", "")),
            "state": str(res.get("state_code", "")),
            "latitude": float(res["latitude"]),
            "longitude": float(res["longitude"]),
        }

    # Fallback to public zippopotam.us API if needed
    try:
        fb_url = f"https://api.zippopotam.us/us/{cleaned_zip}"
        fb_resp = requests.get(fb_url, timeout=5)
        if fb_resp.status_code == 200:
            fb_data = fb_resp.json()
            places = fb_data.get("places", [])
            if places:
                p0 = places[0]
                return {
                    "postal_code": cleaned_zip,
                    "city": p0.get("place name", ""),
                    "state": p0.get("state abbreviation", ""),
                    "latitude": float(p0.get("latitude", 0.0)),
                    "longitude": float(p0.get("longitude", 0.0)),
                }
    except Exception:
        pass

    return None


def find_nearby_costco_gas(
    zipcode: str,
    radius_miles: float = 35.0,
    max_stores: int = 6,
) -> Dict[str, Any]:
    """Find nearby Costco warehouses for a given zip code and fetch their live gas prices."""
    zip_info = lookup_zipcode(zipcode)
    if not zip_info:
        return {
            "success": False,
            "error": f"Could not find coordinates for ZIP code '{zipcode}'. Please enter a valid 5-digit US ZIP code.",
            "zip_info": None,
            "stores": [],
        }

    all_stores = get_all_stores()
    if not all_stores:
        return {
            "success": False,
            "error": "Store directory unavailable.",
            "zip_info": zip_info,
            "stores": [],
        }

    df = pd.DataFrame(all_stores)
    valid_coords = df.dropna(subset=["latitude", "longitude"]).copy()

    # Calculate distance to each warehouse
    distances = haversine_np(
        zip_info["latitude"],
        zip_info["longitude"],
        valid_coords["latitude"].to_numpy(dtype=float),
        valid_coords["longitude"].to_numpy(dtype=float),
    )
    valid_coords["distance_miles"] = np.round(distances, 1)

    # Filter within radius
    within_radius = valid_coords[
        valid_coords["distance_miles"] <= radius_miles
    ].sort_values("distance_miles")

    # If none found within radius, fallback to closest 3 so the user always sees results
    if within_radius.empty:
        selected = valid_coords.sort_values("distance_miles").head(3)
        radius_exceeded = True
    else:
        selected = within_radius.head(max_stores)
        radius_exceeded = False

    # Concurrently fetch gas prices for selected stores
    candidates = selected.to_dict(orient="records")
    wid_map = {str(s["id"]): s for s in candidates}

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(candidates) or 1
    ) as executor:
        future_to_wid = {
            executor.submit(fetch_single_gas_price, str(s["id"]), s["name"]): str(
                s["id"]
            )
            for s in candidates
        }
        prices_by_wid: Dict[str, Dict[str, Any]] = {}
        for fut in concurrent.futures.as_completed(future_to_wid):
            wid = future_to_wid[fut]
            try:
                prices_by_wid[wid] = fut.result()
            except Exception as e:
                prices_by_wid[wid] = {
                    "warehouse_id": wid,
                    "store_name": wid_map[wid]["name"],
                    "regular": None,
                    "premium": None,
                    "status": f"Error: {e}",
                }

    # Merge store metadata with fetched prices
    results = []
    for s in candidates:
        wid_str = str(s["id"])
        price_info = prices_by_wid.get(wid_str, {})
        has_gas = (
            price_info.get("regular") is not None
            or price_info.get("premium") is not None
        )

        item = {
            "warehouse_id": wid_str,
            "store_name": f"{s['name']} Costco",
            "short_name": s["name"],
            "street": s.get("street", ""),
            "city": s.get("city", "").title(),
            "state": s.get("state", ""),
            "zip_code": s.get("zip_code", ""),
            "distance_miles": float(s["distance_miles"]),
            "latitude": float(s["latitude"]),
            "longitude": float(s["longitude"]),
            "regular": price_info.get("regular"),
            "premium": price_info.get("premium"),
            "status": (
                "Available" if has_gas else price_info.get("status", "No Gas Station")
            ),
            "has_gas": has_gas,
            "updated_at": price_info.get("updated_at", ""),
        }
        results.append(item)

    # Calculate best prices among stations with active pumps
    gas_stations = [s for s in results if s["has_gas"]]
    cheapest_reg = min(
        [s["regular"] for s in gas_stations if s["regular"] is not None], default=None
    )
    cheapest_prem = min(
        [s["premium"] for s in gas_stations if s["premium"] is not None], default=None
    )

    for s in results:
        s["is_best_regular"] = s["regular"] is not None and s["regular"] == cheapest_reg
        s["is_best_premium"] = (
            s["premium"] is not None and s["premium"] == cheapest_prem
        )

    return {
        "success": True,
        "error": None,
        "zip_info": zip_info,
        "radius_exceeded": radius_exceeded,
        "cheapest_regular": cheapest_reg,
        "cheapest_premium": cheapest_prem,
        "stores": results,
    }


# ---------------------------------------------------------
# User Locations Configuration
# ---------------------------------------------------------


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


def fetch_single_gas_price(
    warehouse_id: str, store_name: str = "", timeout: int = 10
) -> Dict[str, Any]:
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

        if (
            warehouse_data is not None
            and isinstance(warehouse_data, dict)
            and warehouse_data
        ):
            regular_val = warehouse_data.get("regular")
            premium_val = warehouse_data.get("premium")

            reg_float = (
                float(regular_val) if regular_val and regular_val != "N/A" else None
            )
            prem_float = (
                float(premium_val) if premium_val and premium_val != "N/A" else None
            )

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
                results.append(
                    {
                        "warehouse_id": wid,
                        "store_name": locations.get(wid, wid),
                        "regular": None,
                        "premium": None,
                        "status": f"Failed: {e}",
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "raw": {},
                    }
                )

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
            rows_to_insert.append(
                (
                    item.get(
                        "updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ),
                    item.get("store_name", ""),
                    item.get("warehouse_id", ""),
                    item.get("regular"),
                    item.get("premium"),
                )
            )

    if not rows_to_insert:
        return 0

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO gas_price_history (timestamp, store_name, warehouse_id, regular_price, premium_price)
            VALUES (?, ?, ?, ?, ?)
        """,
            rows_to_insert,
        )
        conn.commit()

    return len(rows_to_insert)


def get_price_history(
    days: Optional[int] = None, warehouse_ids: Optional[List[str]] = None
) -> pd.DataFrame:
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
