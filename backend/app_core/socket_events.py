import logging
import time
from datetime import datetime

from flask import request
from flask_socketio import emit, join_room, leave_room

from app_core import shared


def register_socket_handlers(socketio):
    @socketio.on("connect")
    def handle_connect():
        logging.info("Client connected: %s", request.sid)
        emit("response", {"data": "Connected to Socket.IO server"})

    @socketio.on("disconnect")
    def handle_disconnect():
        logging.info("Client disconnected: %s", request.sid)
        if request.sid in shared.client_thresholds:
            del shared.client_thresholds[request.sid]

    @socketio.on("join_dashboard")
    def handle_join_dashboard():
        join_room("dashboard")
        logging.info("Client %s joined room 'dashboard'", request.sid)

        data_list = []
        for device_id, info in shared.latest_data.items():
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
        join_room("logs")
        logging.info("Client %s joined room 'logs'", request.sid)

    @socketio.on("set_alert_threshold")
    def handle_set_threshold(data):
        try:
            threshold = float(data.get("threshold", 100))
            shared.client_thresholds[request.sid] = threshold
            join_room("alert")
            logging.info("Client %s set threshold: %sA", request.sid, threshold)

            log_entry = {
                "id": f"log-{int(time.time() * 1000)}",
                "action": "Cài đặt ngưỡng cảnh báo",
                "deviceId": None,
                "deviceName": None,
                "user": "Hệ thống",
                "timestamp": datetime.now().isoformat(),
                "details": f"Ngưỡng: {threshold}A",
            }
            emit("activity_log", log_entry)
        except ValueError:
            logging.error("Invalid threshold value from client %s", request.sid)

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
        join_room("schedules")
        logging.info("Client %s joined room 'schedules'", request.sid)

    @socketio.on("leave_schedules")
    def handle_leave_schedules():
        leave_room("schedules")
        logging.info("Client %s left room 'schedules'", request.sid)
