"""User management for login/register."""
import uuid
from datetime import datetime

from pymongo import DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()


def create_user(
    email: str, username: str, password_hash: str,
    full_name: str = "", role: str = "user",
) -> dict:
    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    _db.users.insert_one({
        "_id": user_id,
        "email": email,
        "username": username,
        "password_hash": password_hash,
        "full_name": full_name,
        "role": role,
        "is_active": True,
        "avatar_url": None,
        "email_verified": False,
        "verification_code": None,
        "verification_code_expires_at": None,
        "reset_code": None,
        "reset_code_expires_at": None,
        "settings": {
            "language": "vi",
            "theme": "dark",
            "notification_enabled": True,
        },
        "coreiot_config": {
            "jwt_token": None,
            "device_id": None,
            "group_id": None,
        },
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    })
    return find_user_by_id(user_id)


def find_user_by_email(email: str) -> dict | None:
    doc = _db.users.find_one({"email": email})
    return _to_dict(doc)


def find_user_by_username(username: str) -> dict | None:
    doc = _db.users.find_one({"username": username})
    return _to_dict(doc)


def find_user_by_id(user_id: str) -> dict | None:
    doc = _db.users.find_one({"_id": user_id})
    return _to_dict(doc)


def update_user(user_id: str, **fields) -> dict | None:
    allowed = {
        "email", "username", "password_hash", "full_name",
        "role", "is_active", "avatar_url", "settings", "coreiot_config",
        "email_verified", "verification_code", "verification_code_expires_at",
        "reset_code", "reset_code_expires_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return find_user_by_id(user_id)
    updates["updated_at"] = datetime.now().isoformat()
    _db.users.update_one({"_id": user_id}, {"$set": updates})
    return find_user_by_id(user_id)


def update_last_login(user_id: str):
    _db.users.update_one(
        {"_id": user_id},
        {"$set": {"last_login_at": datetime.now().isoformat()}},
    )


def list_users(limit: int = 50) -> list[dict]:
    docs = _db.users.find(
        {}, {"password_hash": 0}
    ).sort("created_at", DESCENDING).limit(limit)
    return [_to_dict(doc) for doc in docs]


def delete_user(user_id: str) -> bool:
    result = _db.users.delete_one({"_id": user_id})
    return result.deleted_count > 0
