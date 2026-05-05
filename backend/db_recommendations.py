"""Recommendation runs, actions, and schedule execution log."""
import json
import uuid
from datetime import datetime

from pymongo import DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()


# === RECOMMENDATION RUNS ===

def create_recommendation_run(
    budget_profile_id: str, month_key: str, planning_horizon_days: int,
    strategy: str, baseline_forecast_bill_vnd: float,
    baseline_forecast_kwh: float, required_bill_reduction_vnd: float,
    required_kwh_reduction: float, summary: dict,
    generated_by: str = "system", run_type: str = "manual",
) -> dict:
    run_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    _db.budget_recommendation_runs.insert_one({
        "_id": run_id,
        "budget_profile_id": budget_profile_id,
        "month_key": month_key, "generated_at": now,
        "generated_by": generated_by, "run_type": run_type,
        "planning_horizon_days": planning_horizon_days,
        "strategy": strategy,
        "baseline_forecast_bill_vnd": baseline_forecast_bill_vnd,
        "baseline_forecast_kwh": baseline_forecast_kwh,
        "required_bill_reduction_vnd": required_bill_reduction_vnd,
        "required_kwh_reduction": required_kwh_reduction,
        "achieved_kwh_reduction_estimate": 0,
        "status": "draft",
        "summary_json": summary,
        "created_at": now, "updated_at": now,
    })
    return get_recommendation_run(run_id)


def update_recommendation_run(run_id: str, **fields) -> dict | None:
    allowed = {
        "optimized_forecast_bill_vnd", "optimized_forecast_kwh",
        "achieved_kwh_reduction_estimate", "status", "summary_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_recommendation_run(run_id)
    updates["updated_at"] = datetime.now().isoformat()
    _db.budget_recommendation_runs.update_one(
        {"_id": run_id}, {"$set": updates}
    )
    return get_recommendation_run(run_id)


def get_recommendation_run(run_id: str) -> dict | None:
    doc = _db.budget_recommendation_runs.find_one({"_id": run_id})
    if not doc:
        return None
    item = _to_dict(doc)
    item["summary"] = item.get("summary_json")
    return item


def list_recommendation_runs(limit: int = 20) -> list[dict]:
    docs = _db.budget_recommendation_runs.find().sort(
        "generated_at", DESCENDING
    ).limit(limit)
    items = []
    for doc in docs:
        item = _to_dict(doc)
        item["summary"] = item.get("summary_json")
        items.append(item)
    return items


# === RECOMMENDATION ACTIONS ===

def add_recommendation_action(run_id: str, payload: dict) -> dict:
    action_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    _db.recommendation_actions.insert_one({
        "_id": action_id, "run_id": run_id,
        "device_id": payload["device_id"],
        "action_type": payload["action_type"],
        "proposed_action": payload["proposed_action"],
        "proposed_start": payload["proposed_start"],
        "proposed_end": payload.get("proposed_end"),
        "proposed_duration_minutes": payload.get("proposed_duration_minutes", 0),
        "estimated_energy_saved_kwh": payload.get("estimated_energy_saved_kwh", 0),
        "estimated_cost_saved_vnd": payload.get("estimated_cost_saved_vnd", 0),
        "comfort_impact_score": payload.get("comfort_impact_score", 0),
        "saving_score": payload.get("saving_score", 0),
        "confidence_score": payload.get("confidence_score", 0.5),
        "priority_score": payload.get("priority_score", 0),
        "reason_code": payload.get("reason_code", "budget_control"),
        "reason_text": payload.get("reason_text"),
        "approval_status": payload.get("approval_status", "pending"),
        "created_at": now, "updated_at": now,
    })
    return get_recommendation_action(action_id)


def get_recommendation_action(action_id: str) -> dict | None:
    doc = _db.recommendation_actions.find_one({"_id": action_id})
    return _to_dict(doc)


def list_recommendation_actions(run_id: str) -> list[dict]:
    docs = _db.recommendation_actions.find({"run_id": run_id}).sort(
        [("priority_score", DESCENDING), ("estimated_cost_saved_vnd", DESCENDING)]
    )
    return [_to_dict(doc) for doc in docs]


def update_recommendation_action(action_id: str, **fields) -> dict | None:
    allowed = {"approval_status", "mapped_schedule_id", "updated_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    updates["updated_at"] = datetime.now().isoformat()
    _db.recommendation_actions.update_one(
        {"_id": action_id}, {"$set": updates}
    )
    return get_recommendation_action(action_id)


# === SCHEDULE EXECUTION LOG ===

def log_schedule_execution(
    schedule_id: str | None, source_run_id: str | None,
    device_id: str, planned_action: str, planned_at: str,
    execution_status: str, executed_action: str | None = None,
    executed_at: str | None = None, failure_reason: str | None = None,
    actual_power_before_w: float | None = None,
    actual_power_after_w: float | None = None,
    actual_current_before_a: float | None = None,
    actual_current_after_a: float | None = None,
):
    log_id = str(uuid.uuid4())
    _db.schedule_execution_log.insert_one({
        "_id": log_id, "schedule_id": schedule_id,
        "source_run_id": source_run_id, "device_id": device_id,
        "planned_action": planned_action, "executed_action": executed_action,
        "planned_at": planned_at, "executed_at": executed_at,
        "execution_status": execution_status,
        "failure_reason": failure_reason,
        "actual_power_before_w": actual_power_before_w,
        "actual_power_after_w": actual_power_after_w,
        "actual_current_before_a": actual_current_before_a,
        "actual_current_after_a": actual_current_after_a,
        "created_at": datetime.now().isoformat(),
    })
