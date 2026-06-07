import logging
import time
from datetime import datetime

import jwt
from flask import request, session
from flask_socketio import emit, join_room, leave_room, disconnect
from app_core.auth_routes import JWT_SECRET, JWT_ALGORITHM

from app_core import shared


def register_socket_handlers(socketio):
    @socketio.on("connect")
    def handle_connect(auth=None):
        token = None
        if auth and "token" in auth:
            token = auth["token"]
        elif request.args.get("token"):
            token = request.args.get("token")
        
        if not token:
            logging.warning("Connection rejected: Missing token")
            return False
            
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("user_id")
            if not user_id:
                raise ValueError("No user_id in token")
            session["user_id"] = user_id
            logging.info("Client connected: %s (User: %s)", request.sid, user_id)
            emit("response", {"data": f"Authenticated as {user_id}"})
        except Exception as e:
            logging.warning("Connection rejected: Invalid token - %s", str(e))
            return False

    @socketio.on("disconnect")
    def handle_disconnect():
        logging.info("Client disconnected: %s", request.sid)
        if request.sid in shared.client_thresholds:
            del shared.client_thresholds[request.sid]

    @socketio.on("join_dashboard")
    def handle_join_dashboard():
        user_id = session.get("user_id")
        if not user_id: return
        
        room = f"user_{user_id}_dashboard"
        join_room(room)
        logging.info("Client %s (User %s) joined room '%s'", request.sid, user_id, room)

        data_list = []
        for device_id, info in shared.latest_data.items():
            cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
            if not cb_config or cb_config.get("user_id") != user_id:
                continue
                
            meta = info.get("metadata", {"type": "unknown", "name": "Unknown", "location": "N/A"})
            attrs = info.get("attributes", {})
            data_list.append(
                {
                    "id": device_id,
                    "type": meta.get("type", "unknown"),
                    "name": meta.get("name", "Unknown"),
                    "location": meta.get("location", "N/A"),
                    "attributes": attrs,
                    "telemetry": info.get("telemetry", {}),
                    "metadata": meta,
                    "status": "online" if attrs.get("POWER") == "ON" else "offline",
                }
            )
        emit("dashboard_update", {"data": data_list})
        logging.info("Sent dashboard snapshot (%d devices) to %s", len(data_list), request.sid)

    @socketio.on("join_logs")
    def handle_join_logs():
        user_id = session.get("user_id")
        if not user_id: return
        room = f"user_{user_id}_logs"
        join_room(room)
        logging.info("Client %s (User %s) joined room '%s'", request.sid, user_id, room)

    @socketio.on("set_alert_threshold")
    def handle_set_threshold(data):
        try:
            user_id = session.get("user_id")
            if not user_id:
                logging.warning("set_alert_threshold rejected: User not logged in")
                return

            device_id = data.get("deviceId")
            if not device_id:
                logging.warning("set_alert_threshold rejected: Missing deviceId")
                return

            # Check permission
            cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
            if not cb_config or cb_config.get("user_id") != user_id:
                logging.warning("set_alert_threshold rejected: Device not found or no permission for user %s", user_id)
                return

            threshold_val = data.get("threshold")
            enabled_val = data.get("enabled")

            # Resolve final values — keep existing from cache if not sent in payload
            enabled = bool(enabled_val) if enabled_val is not None else cb_config.get("overcurrent_enabled", False)
            threshold = float(threshold_val) if threshold_val is not None else cb_config.get("overcurrent_threshold", 20.0)

            # Only write threshold to DB if it was explicitly sent (toggle-only should NOT overwrite threshold)
            update_kwargs: dict = {"overcurrent_enabled": enabled}
            if threshold_val is not None:
                update_kwargs["overcurrent_threshold"] = threshold

            # Update DB - only write fields that changed
            from database import update_device
            update_device(device_id, **update_kwargs)

            # Update in-memory caches
            cb_config["overcurrent_threshold"] = threshold
            cb_config["overcurrent_enabled"] = enabled

            if device_id in shared.DEVICE_METADATA_CACHE:
                shared.DEVICE_METADATA_CACHE[device_id]["overcurrent_threshold"] = threshold
                shared.DEVICE_METADATA_CACHE[device_id]["overcurrent_enabled"] = enabled
            if device_id in shared.latest_data:
                if "metadata" not in shared.latest_data[device_id]:
                    shared.latest_data[device_id]["metadata"] = {}
                shared.latest_data[device_id]["metadata"]["overcurrent_threshold"] = threshold
                shared.latest_data[device_id]["metadata"]["overcurrent_enabled"] = enabled

            logging.info("User %s updated overcurrent settings for %s: threshold=%sA, enabled=%s", user_id, device_id, threshold, enabled)

            # Broadcast update to dashboard room so UI reloads correctly
            socketio.emit(
                "device_updated",
                {
                    "device_id": device_id,
                    "metadata": cb_config,
                    "timestamp": datetime.now().isoformat()
                },
                room=f"user_{user_id}_dashboard"
            )

            # Log activity
            action_desc = "Bật bảo vệ quá dòng" if enabled else "Tắt bảo vệ quá dòng"
            if threshold_val is not None and enabled_val is None:
                action_desc = "Cài đặt ngưỡng bảo vệ quá dòng"

            log_entry = {
                "id": f"log-{int(time.time() * 1000)}",
                "action": action_desc,
                "deviceId": device_id,
                "deviceName": cb_config.get("name", "Unknown CB"),
                "user": "Hệ thống",
                "timestamp": datetime.now().isoformat(),
                "details": f"Ngưỡng: {threshold}A | Trạng thái: {'Bật' if enabled else 'Tắt'}",
            }
            socketio.emit("activity_log", log_entry, room=f"user_{user_id}_logs")

        except (ValueError, TypeError) as e:
            logging.error("Invalid threshold data: %s", str(e))

    @socketio.on("subscribe_devices")
    def handle_subscribe_devices():
        logging.info("Client %s subscribed to device updates", request.sid)
        emit("response", {"data": "Subscribed to device updates"})
        join_room("device_updates")

    @socketio.on("unsubscribe_devices")
    def handle_unsubscribe_devices():
        logging.info("Client %s unsubscribed from device updates", request.sid)
        leave_room("device_updates")

    @socketio.on("join_schedules")
    def handle_join_schedules():
        user_id = session.get("user_id")
        if not user_id: return
        room = f"user_{user_id}_schedules"
        join_room(room)
        logging.info("Client %s (User %s) joined room '%s'", request.sid, user_id, room)

    @socketio.on("leave_schedules")
    def handle_leave_schedules():
        user_id = session.get("user_id")
        if not user_id: return
        room = f"user_{user_id}_schedules"
        leave_room(room)
        logging.info("Client %s (User %s) left room '%s'", request.sid, user_id, room)
