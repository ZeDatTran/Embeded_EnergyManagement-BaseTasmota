import os
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/smart_home")
_client = MongoClient(MONGO_URI)
_db = _client.get_default_database()


def get_db():
    return _db


def _to_dict(doc):
    """Convert MongoDB document to dict with 'id' instead of '_id'."""
    if doc is None:
        return None
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return result


def init_indexes():
    _db.hourly_kwh.create_index("timestamp", unique=True)
    _db.training_log.create_index("date", unique=True)
    _db.schedules.create_index([("enabled", ASCENDING), ("time", ASCENDING)])
    _db.schedules.create_index([("source", ASCENDING), ("source_run_id", ASCENDING)])
    _db.schedules.create_index("approval_status")
    _db.energy_budget_profiles.create_index("month_key", unique=True)
    _db.energy_budget_profiles.create_index("status")
    _db.device_usage_preferences.create_index("device_id", unique=True)
    _db.device_usage_preferences.create_index([("priority", ASCENDING), ("auto_controllable", ASCENDING)])
    _db.plug_hourly_energy.create_index([("device_id", ASCENDING), ("hour_bucket", DESCENDING)])
    _db.plug_hourly_energy.create_index([("device_id", ASCENDING), ("hour_bucket", ASCENDING)], unique=True)
    _db.plug_hourly_energy.create_index([("hour_bucket", DESCENDING)])
    _db.plug_consumption_profiles.create_index("device_id", unique=True)
    _db.plug_consumption_profiles.create_index([("confidence_score", DESCENDING)])
    _db.budget_recommendation_runs.create_index([("month_key", ASCENDING), ("generated_at", DESCENDING)])
    _db.budget_recommendation_runs.create_index([("status", ASCENDING), ("generated_at", DESCENDING)])
    _db.recommendation_actions.create_index([("run_id", ASCENDING), ("approval_status", ASCENDING)])
    _db.recommendation_actions.create_index([("device_id", ASCENDING), ("proposed_start", ASCENDING)])
    _db.schedule_execution_log.create_index([("schedule_id", ASCENDING), ("planned_at", DESCENDING)])
    _db.schedule_execution_log.create_index([("source_run_id", ASCENDING), ("planned_at", DESCENDING)])
    _db.users.create_index("email", unique=True, sparse=True)
    _db.users.create_index("username", unique=True, sparse=True)
    _db.devices.create_index("device_id", unique=True)
    _db.devices.create_index("user_id")
