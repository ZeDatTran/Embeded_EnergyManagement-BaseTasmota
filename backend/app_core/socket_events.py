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
            data_list.append(
                {
                    "id": device_id,
                    "type": meta["type"],
                    "name": meta["name"],
                    "location": meta["location"],
                    "attributes": info.get("attributes", {}),
                    "telemetry": info.get("telemetry", {}),
                }
            )
        emit("dashboard_update", {"data": data_list})

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
            threshold = float(data.get("threshold", 100))
            user_id = session.get("user_id")
            shared.client_thresholds[request.sid] = {"threshold": threshold, "user_id": user_id}
            join_room("alert")
            logging.info("Client %s (User %s) set threshold: %sA", request.sid, user_id, threshold)

            log_entry = {
                "id": f"log-{int(time.time() * 1000)}",
                "action": "Cài đặt ngưỡng cảnh báo",
                "deviceId": None,
                "deviceName": None,
                "user": "Hệ thống",
                "timestamp": datetime.now().isoformat(),
                "details": f"Ngưỡng: {threshold}A",
            }
            user_id = session.get("user_id")
            if user_id:
                emit("activity_log", log_entry, room=f"user_{user_id}_logs")
            else:
                emit("activity_log", log_entry)
        except (ValueError, TypeError):
            logging.error("Invalid threshold data from client %s", request.sid)

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
