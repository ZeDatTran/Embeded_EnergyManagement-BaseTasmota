"""Budget profiles and device usage preferences."""
import uuid
from datetime import datetime

from pymongo import ASCENDING, DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()


# === ENERGY BUDGET PROFILES ===

def get_current_energy_budget_profile(month_key: str | None = None) -> dict | None:
    if month_key is None:
        month_key = datetime.now().strftime("%Y-%m")
    doc = _db.energy_budget_profiles.find_one({"month_key": month_key})
    return _to_dict(doc)


def list_energy_budget_profiles() -> list[dict]:
    docs = _db.energy_budget_profiles.find().sort("month_key", DESCENDING)
    return [_to_dict(doc) for doc in docs]


def upsert_energy_budget_profile(
    month_key: str, target_bill_vnd: float,
    warning_threshold_percent: float = 0.9,
    optimization_mode: str = "manual",
    auto_apply_recommendations: bool = False,
) -> dict:
    now = datetime.now().isoformat()
    existing = get_current_energy_budget_profile(month_key)
    profile_id = existing["id"] if existing else str(uuid.uuid4())
    _db.energy_budget_profiles.update_one(
        {"month_key": month_key},
        {
            "$set": {
                "target_bill_vnd": target_bill_vnd,
                "warning_threshold_percent": warning_threshold_percent,
                "optimization_mode": optimization_mode,
                "auto_apply_recommendations": auto_apply_recommendations,
                "updated_at": now,
            },
            "$setOnInsert": {
                "_id": profile_id, "month_key": month_key,
                "status": "active", "created_at": now,
            },
        },
        upsert=True,
    )
    return get_current_energy_budget_profile(month_key)


def update_energy_budget_analysis(
    month_key: str, current_spent_vnd: float,
    current_consumed_kwh: float, latest_forecast_bill_vnd: float,
    latest_forecast_kwh_month: float, target_kwh_month: float | None = None,
):
    _db.energy_budget_profiles.update_one(
        {"month_key": month_key},
        {"$set": {
            "current_spent_vnd": current_spent_vnd,
            "current_consumed_kwh": current_consumed_kwh,
            "latest_forecast_bill_vnd": latest_forecast_bill_vnd,
            "latest_forecast_kwh_month": latest_forecast_kwh_month,
            "target_kwh_month": target_kwh_month,
            "updated_at": datetime.now().isoformat(),
        }},
    )


# === DEVICE USAGE PREFERENCES ===

def get_device_usage_preferences() -> list[dict]:
    docs = _db.device_usage_preferences.find().sort(
        [("priority", ASCENDING), ("device_name_snapshot", ASCENDING)]
    )
    return [_to_dict(doc) for doc in docs]


def get_device_usage_preference(device_id: str) -> dict | None:
    doc = _db.device_usage_preferences.find_one({"device_id": device_id})
    return _to_dict(doc)


def upsert_device_usage_preference(device_id: str, payload: dict) -> dict:
    existing = get_device_usage_preference(device_id)
    pref_id = existing["id"] if existing else str(uuid.uuid4())
    now = datetime.now().isoformat()

    def _g(db_key, camel_key, default):
        return payload.get(camel_key, existing[db_key] if existing else default)

    doc = {
        "device_id": device_id,
        "device_name_snapshot": payload.get("deviceNameSnapshot"),
        "room_name_snapshot": payload.get("roomNameSnapshot"),
        "priority": _g("priority", "priority", "medium"),
        "auto_controllable": bool(_g("auto_controllable", "autoControllable", False)),
        "required_daily_runtime_minutes": int(_g("required_daily_runtime_minutes", "requiredDailyRuntimeMinutes", 0) or 0),
        "min_runtime_block_minutes": int(_g("min_runtime_block_minutes", "minRuntimeBlockMinutes", 15) or 15),
        "max_runtime_block_minutes": _g("max_runtime_block_minutes", "maxRuntimeBlockMinutes", None),
        "min_off_block_minutes": int(_g("min_off_block_minutes", "minOffBlockMinutes", 0) or 0),
        "allowed_days_json": payload.get("allowedDays", existing["allowed_days_json"] if existing else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
        "allowed_time_windows_json": payload.get("allowedTimeWindows", existing["allowed_time_windows_json"] if existing else None),
        "blocked_time_windows_json": payload.get("blockedTimeWindows", existing["blocked_time_windows_json"] if existing else None),
        "preferred_time_windows_json": payload.get("preferredTimeWindows", existing["preferred_time_windows_json"] if existing else None),
        "avoid_peak_hours": bool(_g("avoid_peak_hours", "avoidPeakHours", False)),
        "comfort_weight": float(_g("comfort_weight", "comfortWeight", 0.5) or 0.5),
        "saving_weight": float(_g("saving_weight", "savingWeight", 0.5) or 0.5),
        "hard_must_run": bool(_g("hard_must_run", "hardMustRun", False)),
        "estimated_power_watts": _g("estimated_power_watts", "estimatedPowerWatts", None),
        "standby_power_watts": _g("standby_power_watts", "standbyPowerWatts", None),
        "updated_at": now,
    }

    _db.device_usage_preferences.update_one(
        {"device_id": device_id},
        {
            "$set": doc,
            "$setOnInsert": {"_id": pref_id, "created_at": existing["created_at"] if existing else now},
        },
        upsert=True,
    )
    return get_device_usage_preference(device_id)


def create_default_preferences_for_devices(devices: list[dict]) -> list[dict]:
    created = []
    for device in devices:
        device_id = device.get("id")
        if not device_id:
            continue
        if get_device_usage_preference(device_id):
            continue
        telemetry = device.get("telemetry", {})
        metadata = device.get("metadata", {})
        created.append(
            upsert_device_usage_preference(device_id, {
                "deviceNameSnapshot": metadata.get("name") or device.get("name") or device_id,
                "roomNameSnapshot": metadata.get("location") or device.get("location"),
                "priority": "medium", "autoControllable": False,
                "requiredDailyRuntimeMinutes": 60, "minRuntimeBlockMinutes": 30,
                "minOffBlockMinutes": 15,
                "allowedDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "allowedTimeWindows": None, "blockedTimeWindows": None,
                "preferredTimeWindows": None, "avoidPeakHours": False,
                "comfortWeight": 0.5, "savingWeight": 0.5, "hardMustRun": False,
                "estimatedPowerWatts": float(telemetry.get("ENERGY-Power") or 0) or None,
            })
        )
    return created
