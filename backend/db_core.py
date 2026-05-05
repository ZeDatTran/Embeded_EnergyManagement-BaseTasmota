"""Core data functions: hourly_kwh, training_log, plug_hourly_energy."""
import uuid
from datetime import datetime, timedelta

from pymongo import ASCENDING, DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()


def save_hourly_kwh(timestamp_iso: str, kwh: float):
    _db.hourly_kwh.update_one(
        {"timestamp": timestamp_iso},
        {"$set": {"timestamp": timestamp_iso, "kwh": round(kwh, 6)}},
        upsert=True,
    )


def get_all_history():
    rows = _db.hourly_kwh.find({}, {"_id": 0}).sort("timestamp", ASCENDING)
    return {row["timestamp"]: row["kwh"] for row in rows}


def log_training_result(date_str, scores: dict, note=""):
    _db.training_log.update_one(
        {"date": date_str},
        {"$set": {
            "date": date_str,
            "r2_rf": scores.get("rf"),
            "r2_xgb": scores.get("xgb"),
            "r2_mlp": scores.get("mlp"),
            "r2_lr": scores.get("lr"),
            "note": note,
        }},
        upsert=True,
    )


def save_plug_hourly_energy(
    device_id: str, hour_bucket: str, energy_kwh: float,
    power_avg_w: float | None = None, current_avg_a: float | None = None,
    voltage_avg_v: float | None = None, on_minutes: int = 0,
    samples_count: int = 1, source: str = "coreiot",
    name: str | None = None, user_id: str | None = None,
):
    energy_val = round(max(0.0, energy_kwh), 6)
    on_min_val = max(0, min(60, on_minutes))
    samples_val = max(1, samples_count)
    filt = {"device_id": device_id, "hour_bucket": hour_bucket}
    existing = _db.plug_hourly_energy.find_one(filt)

    if existing:
        new_on_min = min(60, existing.get("on_minutes", 0) + on_min_val)
        update_set = {"on_minutes": new_on_min, "source": source}
        if power_avg_w is not None:
            update_set["power_avg_w"] = power_avg_w
        if current_avg_a is not None:
            update_set["current_avg_a"] = current_avg_a
        if voltage_avg_v is not None:
            update_set["voltage_avg_v"] = voltage_avg_v
        if name is not None:
            update_set["name"] = name
        if user_id is not None:
            update_set["user_id"] = user_id
        _db.plug_hourly_energy.update_one(filt, {
            "$inc": {"energy_kwh": energy_val, "samples_count": samples_val},
            "$set": update_set,
        })
    else:
        record_id = f"{device_id}:{hour_bucket}"
        _db.plug_hourly_energy.insert_one({
            "_id": record_id, "device_id": device_id, "hour_bucket": hour_bucket,
            "power_avg_w": power_avg_w, "current_avg_a": current_avg_a,
            "voltage_avg_v": voltage_avg_v, "energy_kwh": energy_val,
            "on_minutes": on_min_val, "samples_count": samples_val,
            "source": source, "name": name, "user_id": user_id, 
            "created_at": datetime.now().isoformat(),
        })


def list_plug_hourly_energy(start_iso: str | None = None, end_iso: str | None = None,
                            device_id: str | None = None) -> list[dict]:
    query = {}
    bucket_filter = {}
    if start_iso:
        bucket_filter["$gte"] = start_iso
    if end_iso:
        bucket_filter["$lte"] = end_iso
    if bucket_filter:
        query["hour_bucket"] = bucket_filter
    if device_id:
        query["device_id"] = device_id
    docs = _db.plug_hourly_energy.find(query).sort("hour_bucket", ASCENDING)
    return [_to_dict(doc) for doc in docs]


def get_plug_consumption_totals(start_iso: str, end_iso: str) -> list[dict]:
    pipeline = [
        {"$match": {"hour_bucket": {"$gte": start_iso, "$lte": end_iso}}},
        {"$group": {
            "_id": "$device_id",
            "total_kwh": {"$sum": "$energy_kwh"},
            "avg_power_w": {"$avg": "$power_avg_w"},
            "total_on_minutes": {"$sum": "$on_minutes"},
            "hour_count": {"$sum": 1},
        }},
        {"$sort": {"total_kwh": -1}},
        {"$project": {
            "_id": 0, "device_id": "$_id", "total_kwh": 1,
            "avg_power_w": 1, "total_on_minutes": 1, "hour_count": 1,
        }},
    ]
    return list(_db.plug_hourly_energy.aggregate(pipeline))


def get_device_hourly_average(device_id: str, lookback_days: int = 14) -> dict[int, float]:
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%S")
    pipeline = [
        {"$match": {"device_id": device_id, "hour_bucket": {"$gte": cutoff}}},
        {"$addFields": {"hour_of_day": {"$toInt": {"$substr": ["$hour_bucket", 11, 2]}}}},
        {"$group": {"_id": "$hour_of_day", "avg_kwh": {"$avg": "$energy_kwh"}}},
    ]
    return {int(r["_id"]): float(r["avg_kwh"] or 0) for r in _db.plug_hourly_energy.aggregate(pipeline)}


def get_device_daily_runtime_average(device_id: str, lookback_days: int = 14) -> dict:
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%S")
    pipeline = [
        {"$match": {"device_id": device_id, "hour_bucket": {"$gte": cutoff}}},
        {"$addFields": {"day_key": {"$substr": ["$hour_bucket", 0, 10]}}},
        {"$group": {
            "_id": "$day_key",
            "daily_kwh": {"$sum": "$energy_kwh"},
            "active_hours": {"$sum": {"$cond": [{"$gt": ["$energy_kwh", 0.001]}, 1, 0]}},
        }},
        {"$group": {
            "_id": None,
            "avg_daily_kwh": {"$avg": "$daily_kwh"},
            "avg_active_hours": {"$avg": "$active_hours"},
        }},
    ]
    results = list(_db.plug_hourly_energy.aggregate(pipeline))
    if results:
        return {
            "avg_daily_kwh": float(results[0].get("avg_daily_kwh") or 0),
            "avg_active_hours": float(results[0].get("avg_active_hours") or 0),
        }
    return {"avg_daily_kwh": 0.0, "avg_active_hours": 0.0}
