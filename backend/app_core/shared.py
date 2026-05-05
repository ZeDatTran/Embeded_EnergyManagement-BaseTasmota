import hashlib
import json
import logging
import os
import random
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from database import (
    create_schedule,
    delete_schedule,
    get_all_schedules,
    get_all_history,
    get_enabled_schedules,
    get_schedule_by_id,
    list_plug_hourly_energy,
    log_schedule_execution,
    save_plug_hourly_energy,
    update_schedule,
    get_all_devices,
)

try:
    from ml.websocket_forecast import forecast_client
    from database import save_hourly_kwh

    FORECAST_ENABLED = True
except ImportError:
    print("WARNING: ml/websocket_forecast.py not found. Running without forecast.")
    FORECAST_ENABLED = False

load_dotenv()

CORE_IOT_URL = "https://app.coreiot.io"
JWT_TOKEN = os.getenv("JWT_TOKEN")
DEVICE_ID = os.getenv("DEVICE_ID")
GROUP_ID = os.getenv("GROUP_ID")
ML_ANALYSIS_DEVICE_ID = os.getenv("ML_ANALYSIS_DEVICE_ID") or DEVICE_ID
HEADERS = {"Authorization": f"Bearer {JWT_TOKEN}"}

if not all([JWT_TOKEN, DEVICE_ID, GROUP_ID]):
    raise ValueError("JWT_TOKEN, DEVICE_ID and GROUP_ID must be set in .env file")

log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, "telemetry.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

TELEMETRY_KEYS = [
    "ENERGY-Voltage",
    "ENERGY-Current",
    "ENERGY-Power",
    "ENERGY-Today",
    "ENERGY-Total",
    "ENERGY-Factor",
]

DEVICE_TYPES = ["light", "fan", "ac", "sensor", "camera", "cb", "circuit_breaker"]
DEVICE_LOCATIONS = ["Phòng khách", "Phòng ngủ", "Phòng làm việc", "Phòng ăn", "Ban công"]
DEVICE_NAME_MAP = {
    "light": "Đèn thông minh",
    "fan": "Quạt máy",
    "ac": "Điều hòa",
    "sensor": "Cảm biến",
    "camera": "Camera",
    "cb": "CB Tổng",
    "circuit_breaker": "CB Tổng",
}
ROOM_TYPE_MAP = {
    "living_room": "Phòng khách",
    "bedroom": "Phòng ngủ",
    "office": "Phòng làm việc",
    "kitchen": "Nhà bếp",
    "bathroom": "Phòng tắm",
    "balcony": "Ban công",
    "custom": "Tùy chỉnh",
}
DAY_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

latest_data = {}
subscription_to_device_map = {}
DEVICE_METADATA_CACHE = {}
CUSTOM_CB_DEVICES = {}
client_thresholds = {}


def load_devices_from_db():
    global CUSTOM_CB_DEVICES, DEVICE_METADATA_CACHE
    devices = get_all_devices()
    CUSTOM_CB_DEVICES.clear()
    DEVICE_METADATA_CACHE.clear()
    for dev in devices:
        meta = {
            "type": dev.get("type", "cb"),
            "name": dev.get("name"),
            "location": dev.get("location"),
            "room_type": dev.get("roomType"),
            "room_name": dev.get("roomName"),
            "floor": dev.get("floor"),
            "max_load": dev.get("maxLoad"),
            "user_id": dev.get("userId"),
        }
        CUSTOM_CB_DEVICES[dev["id"]] = meta
        DEVICE_METADATA_CACHE[dev["id"]] = meta
    logging.info(f"Loaded {len(CUSTOM_CB_DEVICES)} devices from DB into cache")


def get_tracked_device_ids(user_id: int = None) -> list[str]:
    """Return device IDs explicitly configured by users. If user_id is provided, return only devices for that user."""
    if user_id is not None:
        return [dev_id for dev_id, meta in CUSTOM_CB_DEVICES.items() if meta.get("user_id") == user_id]
    return list(CUSTOM_CB_DEVICES.keys())

if FORECAST_ENABLED:
    previous_energy = {}
    hourly_kwh_global = {}
    predicted_details_cache = {}
    monthly_boundaries = {}  # 'YYYY-MM': {'consumed_kwh': float, 'bill_vnd': float, 'closed': bool}
    lock = threading.Lock()

def process_new_energy(device_id, total_energy_str, ts_iso):
    """Calculate hourly kWh from ENERGY-Total. Handle monthly boundaries."""
    global hourly_kwh_global, previous_energy, monthly_boundaries
    try:
        total_energy = float(total_energy_str)
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return

    current_month_key = ts.strftime("%Y-%m")
    with lock:
        # Check monthly boundary crossing
        if current_month_key not in monthly_boundaries:
            monthly_boundaries[current_month_key] = {
                'start_ts': int(ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000),
                'consumed_kwh': 0.0,
                'bill_vnd': 0.0,
                'closed': False
            }
            logging.info(f"New month initialized: {current_month_key}")

        # Previous month closeout logic
        prev_month_key = (ts.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        if prev_month_key in monthly_boundaries and not monthly_boundaries[prev_month_key]['closed']:
            prev_month_consumed = sum(
                v for k, v in hourly_kwh_global.items() 
                if k.startswith(prev_month_key)
            )
            monthly_boundaries[prev_month_key] = {
                    'consumed_kwh': round(prev_month_consumed, 2),
                    'bill_vnd': 0.0,  # Calculate in api.py when needed
                    'closed': True
            }
            logging.info(f"Closed previous month {prev_month_key}: {prev_month_consumed:.2f} kWh, Bill: {monthly_boundaries[prev_month_key]['bill_vnd']:,} VND")

        key = ts.strftime("%Y-%m-%dT%H:00:00")
        prev = previous_energy.get(device_id)

        if prev:
            prev_ts, prev_val = prev
            gap_seconds = (ts - prev_ts).total_seconds()
            gap_minutes = gap_seconds / 60
            is_new_day = ts.date() > prev_ts.date()
            is_long_gap = gap_seconds > 30 * 60  # > 30 minutes
            
            delta = total_energy - prev_val
            
            # Decision logic for delta calculation
            if delta < 0:
                # Device counter reset detected
                logging.info(
                    "Device %s counter reset detected (%.6f → %.6f). Setting delta=0.",
                    device_id, prev_val, total_energy
                )
                delta = 0.0
            elif is_new_day:
                # Cross day boundary: treat as new period, don't carry delta from yesterday
                logging.info(
                    "Device %s new day boundary (%s → %s). Resetting delta to 0.",
                    device_id, prev_ts.date(), ts.date()
                )
                delta = 0.0
            elif is_long_gap and 0 < delta < 0.05:
                # Long gap (>30min) but tiny delta (<0.05 kWh): likely register didn't change, duplicate value
                logging.warning(
                    "Device %s duplicate register value (gap=%.0fmin, delta=%.6f). Skipping.",
                    device_id, gap_minutes, delta
                )
                delta = 0.0
            elif is_long_gap:
                # Long gap but reasonable delta: acknowledge the gap
                logging.info(
                    "Device %s long data gap (%.0f min). Delta=%.6f kWh recorded but marked as gap.",
                    device_id, gap_minutes, delta
                )
            else:
                # Normal case: use calculated delta
                if delta >= 0:
                    logging.debug(
                        "Device %s normal delta (gap=%.0fs): %.6f kWh",
                        device_id, gap_seconds, delta
                    )

            if delta > 0:
                hourly_kwh_global[key] = hourly_kwh_global.get(key, 0.0) + round(delta, 4)
                # Update current month consumed
                monthly_boundaries[current_month_key]['consumed_kwh'] = sum(
                    v for k, v in hourly_kwh_global.items() 
                    if k.startswith(current_month_key)
                )

                save_hourly_kwh(key, hourly_kwh_global[key])
                dev_meta = CUSTOM_CB_DEVICES.get(device_id, {})
                dev_name = dev_meta.get("name")
                dev_user_id = dev_meta.get("user_id")
                save_plug_hourly_energy(
                    device_id, key, round(delta, 4), source="coreiot",
                    name=dev_name, user_id=dev_user_id
                )

                if key in predicted_details_cache:
                    forecast_client.send_feedback(
                        {key: predicted_details_cache[key]},
                        {key: hourly_kwh_global[key]},
                    )
                    del predicted_details_cache[key]

        previous_energy[device_id] = (ts, total_energy)

def load_hourly_kwh_from_db():
        """Load persisted hourly consumption to in-memory cache (real data only)."""
        logging.info("Loading hourly_kwh history from database...")
        loaded = 0
        backfilled = 0
        with lock:
            hourly_kwh_global.clear()
            history = get_all_history()
            for ts, kwh in history.items():
                try:
                    hourly_kwh_global[ts] = float(kwh)
                    loaded += 1
                except (TypeError, ValueError):
                    continue

            # Backfill from per-plug hourly table when hourly_kwh is sparse.
            plug_rows = list_plug_hourly_energy()
            by_hour = defaultdict(float)
            for row in plug_rows:
                hour_bucket = row.get("hour_bucket")
                energy_kwh = row.get("energy_kwh")
                if not hour_bucket:
                    continue
                try:
                    by_hour[hour_bucket] += float(energy_kwh or 0.0)
                except (TypeError, ValueError):
                    continue

            for hour_bucket, total_kwh in by_hour.items():
                # Prefer aggregated real plug data when present.
                hourly_kwh_global[hour_bucket] = round(max(0.0, total_kwh), 6)
                backfilled += 1

        logging.info("Loaded %s hourly_kwh records from database.", loaded)
        logging.info("Backfilled %s hourly records from plug_hourly_energy.", backfilled)


def get_or_assign_metadata(device_id):
    """Assign deterministic metadata for one device ID and cache it."""
    global DEVICE_METADATA_CACHE

    if device_id in DEVICE_METADATA_CACHE:
        return DEVICE_METADATA_CACHE[device_id]

    hash_object = hashlib.md5(device_id.encode())
    hash_int = int(hash_object.hexdigest(), 16)
    loc_idx = hash_int % len(DEVICE_LOCATIONS)

    device_type = "cb"
    device_location = DEVICE_LOCATIONS[loc_idx]
    device_name = f"CB {device_location}"

    room_type = "custom"
    for key, value in ROOM_TYPE_MAP.items():
        if value == device_location:
            room_type = key
            break

    metadata = {
        "type": device_type,
        "name": device_name,
        "location": device_location,
        "room_type": room_type,
        "room_name": device_location,
        "max_load": 32,
    }
    DEVICE_METADATA_CACHE[device_id] = metadata
    logging.info(f"CB Metadata Assigned: {device_id} -> {device_name} ({device_location})")

    return metadata


def verify_token():
    """Verify JWT token validity."""
    try:
        response = requests.get(f"{CORE_IOT_URL}/api/auth/user", headers=HEADERS, timeout=10)
        response.raise_for_status()
        logging.info("JWT_TOKEN is valid")
        return True
    except requests.RequestException as e:
        logging.error(
            "Invalid JWT_TOKEN: %s, Status Code: %s",
            e,
            getattr(e.response, "status_code", "N/A"),
        )
        return False


def get_devices_from_group():
    """Get all DEVICE ids from configured entity group only (no tenant fallback)."""
    if not GROUP_ID:
        logging.error("GROUP_ID is missing. Refusing tenant-wide device fetch.")
        return []

    try:
        # CoreIoT/ThingsBoard entity-group endpoint gives strict group membership.
        url = f"{CORE_IOT_URL}/api/entityGroup/{GROUP_ID}/entities?pageSize=100&page=0&entityType=DEVICE"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            entities = payload.get("data", [])
        elif isinstance(payload, list):
            entities = payload
        else:
            entities = []

        device_ids = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            # Common shapes: {id:{id,entityType}}, or {entityId:{id,...}}, or direct id
            if isinstance(entity.get("id"), dict):
                dev_id = entity["id"].get("id")
            elif isinstance(entity.get("entityId"), dict):
                dev_id = entity["entityId"].get("id")
            else:
                dev_id = entity.get("id")

            if dev_id:
                device_ids.append(dev_id)

        if not device_ids:
            logging.warning("No devices found in group %s.", GROUP_ID)
            return []

        logging.info("Found %s devices in group %s", len(device_ids), GROUP_ID)
        return device_ids

    except requests.RequestException as e:
        logging.error("Error fetching devices from group %s: %s", GROUP_ID, e)
        return []


def get_device_telemetry(device_id):
    """Fetch one snapshot telemetry and update local cache."""
    try:
        response = requests.get(
            (
                f"{CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/"
                f"values/timeseries?keys={','.join(TELEMETRY_KEYS)}&limit=1"
            ),
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        telemetry = response.json()

        if device_id not in latest_data:
            metadata = get_or_assign_metadata(device_id)
            latest_data[device_id] = {
                "telemetry": {},
                "attributes": {"POWER": "N/A"},
                "metadata": metadata,
            }

        parsed_telemetry = {}
        for key, value_list in telemetry.items():
            if value_list and isinstance(value_list, list) and value_list[0] and "value" in value_list[0]:
                parsed_telemetry[key] = value_list[0]["value"]
            else:
                parsed_telemetry[key] = "N/A"

        latest_data[device_id]["telemetry"].update(parsed_telemetry)

        hour_bucket = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
        try:
            power_w = float(parsed_telemetry.get("ENERGY-Power") or 0)
            current_a = float(parsed_telemetry.get("ENERGY-Current") or 0)
            voltage_v = float(parsed_telemetry.get("ENERGY-Voltage") or 0)
            # Polling interval is ~10 seconds in periodic_data_logger.
            # Energy per sample (kWh) = W * seconds / (1000 * 3600).
            estimated_kwh = max(0.0, power_w) * 10.0 / (1000.0 * 3600.0)
            dev_meta = CUSTOM_CB_DEVICES.get(device_id, {})
            dev_name = dev_meta.get("name")
            dev_user_id = dev_meta.get("user_id")
            save_plug_hourly_energy(
                device_id=device_id,
                hour_bucket=hour_bucket,
                energy_kwh=estimated_kwh,
                power_avg_w=power_w,
                current_avg_a=current_a,
                voltage_avg_v=voltage_v,
                on_minutes=0,
                samples_count=1,
                source="derived",
                name=dev_name,
                user_id=dev_user_id,
            )
        except (TypeError, ValueError):
            pass

        logging.info("Telemetry received for device %s: %s", device_id, parsed_telemetry)
        return telemetry

    except requests.RequestException as e:
        logging.error("Error fetching telemetry for device %s: %s", device_id, e)
        return {}
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON telemetry for device %s", device_id)
        return {}


def get_device_attributes(device_id):
    """Fetch device attributes (POWER state)."""
    try:
        response = requests.get(
            f"{CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/CLIENT_SCOPE",
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        attributes = response.json()
        power_attr = next((attr for attr in attributes if attr["key"] == "POWER"), {"value": "N/A"})

        if device_id not in latest_data:
            metadata = get_or_assign_metadata(device_id)
            latest_data[device_id] = {
                "telemetry": {},
                "attributes": {"POWER": "N/A"},
                "metadata": metadata,
            }

        latest_data[device_id]["attributes"]["POWER"] = power_attr["value"]
        logging.info("POWER attribute received for device %s: %s", device_id, power_attr["value"])
        return attributes
    except requests.RequestException as e:
        logging.error("Error fetching attributes for device %s: %s", device_id, e)
        return []
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON attributes for device %s", device_id)
        return []


def send_rpc_to_device(device_id, command, retries=3):
    """Send RPC POWER command to one device."""
    api_url = f"{CORE_IOT_URL}/api/rpc/oneway/{device_id}"
    payload = {"method": "POWER", "params": command.upper()}

    for attempt in range(retries):
        try:
            response = requests.post(api_url, headers=HEADERS, json=payload, timeout=15)
            if response.status_code == 200:
                logging.info("RPC '%s' sent to %s successfully.", command, device_id)
                return True, {"status": "success", "device_id": device_id, "command_sent": command}
            if response.status_code == 401:
                logging.warning("401 error sending RPC to %s: Invalid token.", device_id)
                return False, {"status": "error", "message": "Token (JWT) expired or invalid."}
            logging.error("Error sending RPC to %s: %s - %s", device_id, response.status_code, response.text)
            return False, {"status": "error", "message": response.text, "device_id": device_id}
        except requests.exceptions.Timeout as e:
            logging.warning("Timeout attempt %s/%s sending RPC to %s: %s", attempt + 1, retries, device_id, e)
            if attempt < retries - 1:
                time.sleep(2**attempt)
            else:
                logging.error("All %s attempts failed sending RPC to %s", retries, device_id)
                return (
                    False,
                    {
                        "status": "error",
                        "message": "Device not responding. Please check connection.",
                        "device_id": device_id,
                    },
                )
        except requests.exceptions.RequestException as e:
            logging.error("Connection error sending RPC to %s: %s", device_id, e)
            return False, {"status": "error", "message": str(e), "device_id": device_id}


def generate_mock_device_history(period):
    """Generate mock history data as fallback when upstream fails."""
    now = datetime.now()
    history = []

    if period == "week":
        count = 168
        interval_minutes = 60
    elif period == "month":
        count = 720
        interval_minutes = 60
    else:
        count = 24
        interval_minutes = 60

    for i in range(count - 1, -1, -1):
        timestamp = now - timedelta(minutes=i * interval_minutes)
        hour = timestamp.hour

        if 0 <= hour < 6:
            base_power = 30
        elif 6 <= hour < 9:
            base_power = 150
        elif 9 <= hour < 17:
            base_power = 80
        elif 17 <= hour < 22:
            base_power = 200
        else:
            base_power = 50

        power = base_power + random.uniform(-20, 20)
        voltage = 220 + random.uniform(-5, 5)
        current = power / voltage

        history.append(
            {
                "timestamp": timestamp.isoformat(),
                "power": round(max(0, power), 2),
                "voltage": round(voltage, 1),
                "current": round(max(0, current), 4),
                "energy": round(max(0, power * (interval_minutes / 60) / 1000), 4),
            }
        )

    return history


def get_plug_hourly_history_for_forecast(device_id: str, start_of_month: datetime, now: datetime) -> dict:
    """Get hourly history for one plug from plug_hourly_energy table for forecasting."""
    start_iso = start_of_month.strftime("%Y-%m-%dT%H:00:00")
    end_iso = now.strftime("%Y-%m-%dT%H:00:00")
    
    rows = list_plug_hourly_energy(start_iso=start_iso, end_iso=end_iso, device_id=device_id)
    history_dict = {}
    for row in rows:
        hour_bucket = row.get("hour_bucket")
        energy_kwh = row.get("energy_kwh", 0.0)
        try:
            history_dict[hour_bucket] = float(energy_kwh)
        except (TypeError, ValueError):
            pass
    
    return history_dict


def get_all_plugs_for_forecast() -> list[dict]:
    """Return list of custom CB devices with their metadata for batch forecasting."""
    plugs = []
    for device_id, metadata in CUSTOM_CB_DEVICES.items():
        plugs.append({
            "device_id": device_id,
            "name": metadata.get("name", f"CB {device_id}"),
            "location": metadata.get("location", "N/A"),
        })
    return plugs
