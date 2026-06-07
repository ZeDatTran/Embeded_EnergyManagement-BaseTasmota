import json
import logging
import time
from datetime import datetime

import websocket

from app_core import shared
from database import find_user_by_id
from app_core.email_utils import send_email, get_overload_alert_email_html

# Cache for rate limiting warning emails: device_id -> timestamp
last_email_sent_at = {}


def periodic_data_logger():
    """Periodically fetch data every 10s."""
    while True:
        logging.info("Periodic check: Starting data fetch cycle")
        if shared.verify_token():
            devices = shared.get_tracked_device_ids()
            if not devices:
                logging.info("Periodic check: No configured CB devices to fetch")
            for device_id in devices:
                shared.get_device_telemetry(device_id)
                shared.get_device_attributes(device_id)
                time.sleep(0.1)
        else:
            logging.warning("Periodic check: Cannot fetch data due to invalid token")
        time.sleep(10)


def schedule_executor(socketio):
    """Background thread to execute scheduled actions."""
    logging.info("Schedule executor started")
    executed_today = {}

    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_day = list(shared.DAY_MAP.keys())[now.weekday()]
            today_key = now.strftime("%Y-%m-%d")

            keys_to_remove = [k for k in executed_today.keys() if not k.startswith(today_key)]
            for k in keys_to_remove:
                del executed_today[k]

            schedules = shared.get_enabled_schedules()

            for schedule in schedules:
                schedule_key = f"{today_key}_{schedule['id']}_{schedule['time']}"
                if (
                    schedule["time"] == current_time
                    and current_day in schedule["days"]
                    and schedule_key not in executed_today
                ):
                    logging.info(
                        "Executing schedule: %s - %s for %s",
                        schedule["name"],
                        schedule["action"].upper(),
                        schedule["targetId"],
                    )

                    target_id = schedule["targetId"]
                    action = schedule["action"].upper()

                    if target_id in ["all", "group"]:
                        device_ids = shared.get_devices_from_group()
                        for device_id in device_ids:
                            success, result = shared.send_rpc_to_device(device_id, action)
                            if success:
                                logging.info("Schedule executed: %s -> %s %s", schedule["name"], device_id, action)
                                shared.log_schedule_execution(
                                    schedule_id=schedule["id"],
                                    source_run_id=schedule.get("sourceRunId"),
                                    device_id=device_id,
                                    planned_action=action.lower(),
                                    planned_at=now.isoformat(),
                                    execution_status="success",
                                    executed_action=action.lower(),
                                    executed_at=datetime.now().isoformat(),
                                )
                            else:
                                logging.error("Schedule failed for %s: %s", device_id, result)
                                shared.log_schedule_execution(
                                    schedule_id=schedule["id"],
                                    source_run_id=schedule.get("sourceRunId"),
                                    device_id=device_id,
                                    planned_action=action.lower(),
                                    planned_at=now.isoformat(),
                                    execution_status="failed",
                                    failure_reason=result.get("message"),
                                )
                            time.sleep(0.1)
                    else:
                        success, result = shared.send_rpc_to_device(target_id, action)
                        if success:
                            logging.info("Schedule executed: %s -> %s %s", schedule["name"], target_id, action)
                            shared.log_schedule_execution(
                                schedule_id=schedule["id"],
                                source_run_id=schedule.get("sourceRunId"),
                                device_id=target_id,
                                planned_action=action.lower(),
                                planned_at=now.isoformat(),
                                execution_status="success",
                                executed_action=action.lower(),
                                executed_at=datetime.now().isoformat(),
                            )
                        else:
                            logging.error("Schedule failed for %s: %s", target_id, result)
                            shared.log_schedule_execution(
                                schedule_id=schedule["id"],
                                source_run_id=schedule.get("sourceRunId"),
                                device_id=target_id,
                                planned_action=action.lower(),
                                planned_at=now.isoformat(),
                                execution_status="failed",
                                failure_reason=result.get("message"),
                            )

                    executed_today[schedule_key] = True

                    user_id = schedule.get("userId")
                    if user_id:
                        socketio.emit(
                            "schedule_executed",
                            {
                                "scheduleId": schedule["id"],
                                "scheduleName": schedule["name"],
                                "targetId": target_id,
                                "action": action,
                                "executedAt": now.isoformat(),
                            },
                            room=f"user_{user_id}_schedules",
                        )

                    if schedule.get("runOnce"):
                        deleted = shared.delete_schedule(schedule["id"])
                        if deleted:
                            logging.info("One-time schedule deleted after execution: %s", schedule["id"])
                            socketio.emit("schedule_deleted", {"id": schedule["id"]}, room=f"user_{user_id}_schedules")
                        else:
                            logging.warning(
                                "One-time schedule could not be deleted after execution: %s",
                                schedule["id"],
                            )

                    log_entry = {
                        "id": f"log-{int(time.time() * 1000)}",
                        "action": f"Lịch trình tự động: {schedule['name']}",
                        "deviceId": target_id,
                        "deviceName": schedule["name"],
                        "user": "Scheduler",
                        "timestamp": now.isoformat(),
                        "details": f"{action} - {schedule['time']}",
                    }
                    if user_id:
                        socketio.emit("activity_log", log_entry, room=f"user_{user_id}_logs")

        except Exception as e:
            logging.error("Schedule executor error: %s", e)

        time.sleep(30)


def start_websocket(socketio):
    """Start CoreIoT websocket connection for real-time updates."""
    ws_url = f"wss://app.coreiot.io/api/ws/plugins/telemetry?token={shared.JWT_TOKEN}"

    def on_message(ws, message):
        try:
            data = json.loads(message)
            subscription_id = data.get("subscriptionId")
            device_id = shared.subscription_to_device_map.get(subscription_id)

            if not device_id:
                if "errorCode" in data and data["errorCode"] != 0:
                    logging.error("WebSocket server error: %s", data.get("errorMsg", "Unknown"))
                return

            if "data" in data:
                telemetry_data = data.get("data", {})

                if device_id not in shared.latest_data:
                    metadata = shared.get_or_assign_metadata(device_id)
                    shared.latest_data[device_id] = {
                        "telemetry": {},
                        "attributes": {"POWER": "N/A"},
                        "metadata": metadata,
                    }

                telemetry_keys_found = {
                    key: telemetry_data[key][0][1]
                    for key in shared.TELEMETRY_KEYS
                    if key in telemetry_data
                }
                if telemetry_keys_found:
                    shared.latest_data[device_id]["telemetry"].update(telemetry_keys_found)
                    logging.info("Real-time telemetry for %s: %s", device_id, telemetry_keys_found)

                    if "ENERGY-Current" in telemetry_keys_found:
                        current_val = float(telemetry_keys_found["ENERGY-Current"])
                        display_name = shared.latest_data[device_id]["metadata"]["name"]

                        cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
                        if cb_config and cb_config.get("overcurrent_enabled", False):
                            threshold = cb_config.get("overcurrent_threshold", 20.0)
                            device_user_id = cb_config.get("user_id")

                            if current_val > threshold:
                                msg = {
                                    "level": "DANGER",
                                    "device_id": device_id,
                                    "current": current_val,
                                    "threshold": threshold,
                                    "message": (
                                        f"{display_name} (Dòng {current_val}A) "
                                        f"vượt ngưỡng {threshold}A."
                                    ),
                                }
                                if device_user_id:
                                    socketio.emit("alert_trigger", msg, room=f"user_{device_user_id}_dashboard")

                                try:
                                    logging.warning(
                                        "Auto-shutdown: %s (Current: %sA > Threshold: %sA)",
                                        display_name,
                                        current_val,
                                        threshold,
                                    )
                                    success, result = shared.send_rpc_to_device(device_id, "OFF")
                                    if success:
                                        logging.info("Auto-shutdown successful for %s", device_id)
                                    else:
                                        logging.error("Auto-shutdown failed for %s: %s", device_id, result)
                                    
                                    # Send warning email with rate limit check
                                    if device_user_id:
                                        now_ts = time.time()
                                        last_sent = last_email_sent_at.get(device_id, 0.0)
                                        if now_ts - last_sent > 300:  # 5 minutes limit
                                            last_email_sent_at[device_id] = now_ts
                                            
                                            def trigger_warning_email(uid, dname, cur, thres, dev_id):
                                                try:
                                                    user = find_user_by_id(uid)
                                                    if user and user.get("email"):
                                                        user_settings = user.get("settings") or {}
                                                        if user_settings.get("notification_enabled", True):
                                                            html_content = get_overload_alert_email_html(
                                                                user.get("full_name") or user["username"],
                                                                dname, cur, thres
                                                            )
                                                            send_email(
                                                                user["email"],
                                                                f"[CẢNH BÁO] Thiết bị {dname} tự động ngắt do quá tải",
                                                                html_content
                                                            )
                                                except Exception as ex:
                                                    logging.error("Error sending warning email for %s: %s", dev_id, ex)
                                            
                                            import threading
                                            threading.Thread(
                                                target=trigger_warning_email,
                                                args=(device_user_id, display_name, current_val, threshold, device_id),
                                                daemon=True
                                            ).start()
                                except Exception as e:
                                    logging.error("Error during auto-shutdown for %s: %s", device_id, e)

                if "POWER" in telemetry_data:
                    power_val = telemetry_data["POWER"][0][1]
                    old_power = shared.latest_data[device_id]["attributes"].get("POWER", "N/A")
                    shared.latest_data[device_id]["attributes"]["POWER"] = power_val
                    logging.info("Real-time attribute for %s: POWER = %s", device_id, power_val)

                    if old_power != "N/A" and old_power != power_val:
                        display_name = shared.latest_data[device_id]["metadata"]["name"]
                        action = "Bật thiết bị" if power_val == "ON" else "Tắt thiết bị"

                        log_entry = {
                            "id": f"log-{int(time.time() * 1000)}",
                            "action": action,
                            "deviceId": device_id,
                            "deviceName": display_name,
                            "user": "Hệ thống",
                            "timestamp": datetime.now().isoformat(),
                            "details": f"Trạng thái: {power_val}",
                        }

                        cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
                        if cb_config and "user_id" in cb_config:
                            socketio.emit("activity_log", log_entry, room=f"user_{cb_config['user_id']}_logs")
                        logging.info("Activity log sent: %s - %s", action, display_name)

                if shared.FORECAST_ENABLED and "ENERGY-Total" in telemetry_data:
                    ts_ms = telemetry_data["ENERGY-Total"][0][0]
                    iso_ts = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
                    shared.process_new_energy(device_id, telemetry_data["ENERGY-Total"][0][1], iso_ts)

                cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
                if cb_config and "user_id" in cb_config:
                    socketio.emit(
                        "dashboard_update",
                        {
                            "device_id": device_id,
                            "data": shared.latest_data[device_id],
                            "timestamp": datetime.now().isoformat(),
                        },
                        room=f"user_{cb_config['user_id']}_dashboard",
                    )

        except json.JSONDecodeError as e:
            logging.error("Error decoding WebSocket message: %s", e)
        except Exception as e:
            logging.error("Error processing WebSocket message: %s", e)

    def on_error(ws, error):
        logging.error("WebSocket error: %s", error)

    def on_close(ws, close_status_code, close_msg):
        logging.warning("WebSocket closed: Status %s, Message: %s", close_status_code, close_msg)

    def on_open(ws):
        logging.info("WebSocket connection opened, subscribing to devices...")
        shared.subscription_to_device_map.clear()

        try:
            device_ids = shared.get_tracked_device_ids()
            if not device_ids:
                logging.info("WebSocket: No configured CB devices to subscribe.")
                return

            ts_sub_cmds = []
            attr_sub_cmds = []
            cmd_id_counter = 1

            for dev_id in device_ids:
                ts_sub_cmds.append(
                    {
                        "entityType": "DEVICE",
                        "entityId": dev_id,
                        "scope": "LATEST_TELEMETRY",
                        "keys": ",".join(shared.TELEMETRY_KEYS),
                        "cmdId": cmd_id_counter,
                    }
                )
                shared.subscription_to_device_map[cmd_id_counter] = dev_id
                cmd_id_counter += 1

                attr_sub_cmds.append(
                    {
                        "entityType": "DEVICE",
                        "entityId": dev_id,
                        "scope": "CLIENT_SCOPE",
                        "keys": "POWER",
                        "cmdId": cmd_id_counter,
                    }
                )
                shared.subscription_to_device_map[cmd_id_counter] = dev_id
                cmd_id_counter += 1

            subscription_message = {"tsSubCmds": ts_sub_cmds, "attrSubCmds": attr_sub_cmds}
            ws.send(json.dumps(subscription_message))
            logging.info("WebSocket: Subscribed to %s devices.", len(device_ids))

        except Exception as e:
            logging.error("Error during WebSocket subscription: %s", e)

    while True:
        if shared.verify_token():
            try:
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_open=on_open,
                    on_close=on_close,
                )
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logging.error("WebSocket connection failed: %s", e)
        else:
            logging.error("Cannot start WebSocket due to invalid token")

        logging.info("WebSocket connection closed. Retrying in 30 seconds...")
        time.sleep(30)
