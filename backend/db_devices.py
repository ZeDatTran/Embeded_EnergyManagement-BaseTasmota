"""CRUD operations for IoT devices (devices collection)."""
from datetime import datetime
from pymongo import ASCENDING, DESCENDING
from db_connection import get_db, _to_dict

_db = get_db()

def _doc_to_device(doc) -> dict:
    if not doc:
        return None
    return {
        "id": doc.get("device_id"),
        "userId": doc.get("user_id"),
        "name": doc.get("name"),
        "type": doc.get("type", "cb"),
        "location": doc.get("location"),
        "roomType": doc.get("room_type"),
        "roomName": doc.get("room_name"),
        "floor": doc.get("floor"),
        "maxLoad": doc.get("max_load"),
        "overcurrentThreshold": doc.get("overcurrent_threshold", 20.0),
        "overcurrentEnabled": doc.get("overcurrent_enabled", False),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
    }

def create_device(device_id: str, user_id: str, name: str, device_type: str = "cb",
                  location: str = None, room_type: str = "custom", room_name: str = "",
                  floor: int = None, max_load: int = 32,
                  overcurrent_threshold: float = 20.0, overcurrent_enabled: bool = False) -> dict:
    created_at = datetime.now().isoformat()
    _db.devices.update_one(
        {"device_id": device_id},
        {"$set": {
            "device_id": device_id,
            "user_id": user_id,
            "name": name,
            "type": device_type,
            "location": location,
            "room_type": room_type,
            "room_name": room_name,
            "floor": floor,
            "max_load": max_load,
            "overcurrent_threshold": overcurrent_threshold,
            "overcurrent_enabled": overcurrent_enabled,
            "created_at": created_at,
            "updated_at": created_at,
        }},
        upsert=True
    )
    return get_device_by_id(device_id)

def get_device_by_id(device_id: str) -> dict | None:
    doc = _db.devices.find_one({"device_id": device_id})
    return _doc_to_device(doc)

def get_devices_by_user(user_id: str) -> list[dict]:
    docs = _db.devices.find({"user_id": user_id}).sort("created_at", DESCENDING)
    return [_doc_to_device(doc) for doc in docs]

def get_all_devices() -> list[dict]:
    docs = _db.devices.find().sort("created_at", DESCENDING)
    return [_doc_to_device(doc) for doc in docs]

def update_device(device_id: str, name: str = None, location: str = None,
                  room_type: str = None, room_name: str = None,
                  floor: int = None, max_load: int = None, user_id: str = None,
                  overcurrent_threshold: float = None, overcurrent_enabled: bool = None) -> dict | None:
    update_fields = {"updated_at": datetime.now().isoformat()}
    if name is not None: update_fields["name"] = name
    if location is not None: update_fields["location"] = location
    if room_type is not None: update_fields["room_type"] = room_type
    if room_name is not None: update_fields["room_name"] = room_name
    if floor is not None: update_fields["floor"] = floor
    if max_load is not None: update_fields["max_load"] = max_load
    if user_id is not None: update_fields["user_id"] = user_id
    if overcurrent_threshold is not None: update_fields["overcurrent_threshold"] = overcurrent_threshold
    if overcurrent_enabled is not None: update_fields["overcurrent_enabled"] = overcurrent_enabled
    
    _db.devices.update_one({"device_id": device_id}, {"$set": update_fields})
    return get_device_by_id(device_id)

def delete_device(device_id: str) -> bool:
    result = _db.devices.delete_one({"device_id": device_id})
    return result.deleted_count > 0
