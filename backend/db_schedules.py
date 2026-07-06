"""Schedule CRUD operations."""
import json
import uuid
from datetime import datetime

from pymongo import ASCENDING, DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()


def _doc_to_schedule(doc) -> dict:
    """Convert MongoDB schedule document to API-compatible camelCase dict."""
    if doc is None:
        return None
    return {
        "id": str(doc["_id"]),
        "userId": doc.get("user_id"),
        "name": doc["name"],
        "targetId": doc["target_id"],
        "action": doc["action"],
        "time": doc["time"],
        "days": doc.get("days", []),
        "enabled": bool(doc.get("enabled", True)),
        "runOnce": bool(doc.get("run_once", False)),
        "source": doc.get("source", "manual"),
        "sourceRunId": doc.get("source_run_id"),
        "approvalStatus": doc.get("approval_status", "manual"),
        "executionPriority": doc.get("execution_priority", 100),
        "expiresAt": doc.get("expires_at"),
        "metadata": doc.get("metadata"),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
    }


def create_schedule(
    name: str, target_id: str, action: str, time: str, days: list,
    enabled: bool = True, run_once: bool = False,
    source: str = "manual", source_run_id: str | None = None,
    approval_status: str = "manual", execution_priority: int = 100,
    expires_at: str | None = None, metadata: dict | None = None,
    user_id: str | None = None,
) -> dict:
    schedule_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    _db.schedules.insert_one({
        "_id": schedule_id, "user_id": user_id, "name": name, "target_id": target_id,
        "action": action, "time": time, "days": days,
        "enabled": enabled, "run_once": run_once,
        "source": source, "source_run_id": source_run_id,
        "approval_status": approval_status,
        "execution_priority": execution_priority,
        "expires_at": expires_at, "metadata": metadata,
        "created_at": created_at, "updated_at": None,
    })
    return get_schedule_by_id(schedule_id)


def get_all_schedules() -> list:
    docs = _db.schedules.find().sort("created_at", DESCENDING)
    return [_doc_to_schedule(doc) for doc in docs]


def get_schedule_by_id(schedule_id: str) -> dict | None:
    doc = _db.schedules.find_one({"_id": schedule_id})
    return _doc_to_schedule(doc)


def update_schedule(
    schedule_id: str, name: str = None, target_id: str = None,
    action: str = None, time: str = None, days: list = None,
    enabled: bool = None, run_once: bool = None,
    approval_status: str = None, expires_at: str = None,
    metadata: dict | None = None, user_id: str | None = None,
) -> dict | None:
    doc = _db.schedules.find_one({"_id": schedule_id})
    if not doc:
        return None

    update_fields = {"updated_at": datetime.now().isoformat()}
    if name is not None:
        update_fields["name"] = name
    if target_id is not None:
        update_fields["target_id"] = target_id
    if action is not None:
        update_fields["action"] = action
    if time is not None:
        update_fields["time"] = time
    if days is not None:
        update_fields["days"] = days
    if enabled is not None:
        update_fields["enabled"] = enabled
    if run_once is not None:
        update_fields["run_once"] = run_once
    if approval_status is not None:
        update_fields["approval_status"] = approval_status
    if expires_at is not None:
        update_fields["expires_at"] = expires_at
    if metadata is not None:
        update_fields["metadata"] = metadata
    if user_id is not None:
        update_fields["user_id"] = user_id

    _db.schedules.update_one({"_id": schedule_id}, {"$set": update_fields})
    return get_schedule_by_id(schedule_id)


def delete_schedule(schedule_id: str) -> bool:
    result = _db.schedules.delete_one({"_id": schedule_id})
    return result.deleted_count > 0


def get_enabled_schedules() -> list:
    now = datetime.now()
    allowed_status = {"manual", "approved", "auto_approved"}
    docs = _db.schedules.find({"enabled": True}).sort(
        [("execution_priority", ASCENDING), ("created_at", DESCENDING)]
    )
    schedules = []
    for doc in docs:
        schedule = _doc_to_schedule(doc)
        if schedule["approvalStatus"] not in allowed_status:
            continue
        expires_at = schedule.get("expiresAt")
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) < now:
                    continue
            except ValueError:
                pass
        schedules.append(schedule)
    return schedules
