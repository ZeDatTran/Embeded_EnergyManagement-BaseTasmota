import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests
from flask import jsonify, request

from app_core import shared


PRICE_PER_KWH = 2500


def register_routes(app, socketio):
    @app.route("/", methods=["GET"])
    def home():
        endpoints = {
            "/check-data": "Get all device data",
            "/check-token": "Verify JWT token",
            "/control/<device_id>/<on|off>": "Control specific device",
            "/control/group/<on|off>": "Control all devices",
        }

        if shared.FORECAST_ENABLED:
            endpoints["/forecast"] = "Trigger AI forecast"
            endpoints["/forecast/summary"] = "Get simplified forecast result (Fast)"
            endpoints["/energy"] = "Get hourly kWh data"

        return jsonify(
            {
                "status": "success",
                "message": "Smart Plug Backend - Full Features (Alert + Forecast)",
                "features": {
                    "forecast": shared.FORECAST_ENABLED,
                    "auto_shutdown": True,
                    "activity_logs": True,
                    "realtime_alerts": True,
                },
                "endpoints": endpoints,
            }
        )

    @app.route("/check-data", methods=["GET"])
    def check_data():
        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

        if not shared.latest_data:
            logging.warning("/check-data called but no data cached yet. Forcing fetch for configured CB devices.")
            devices = shared.get_tracked_device_ids()
            for device_id in devices:
                shared.get_device_telemetry(device_id)
                shared.get_device_attributes(device_id)

        data_array = []
        for device_id, info in shared.latest_data.items():
            meta = info.get("metadata", {"type": "cb", "name": "CB Unknown", "location": "N/A"})
            data_array.append(
                {
                    "type": meta.get("type", "cb"),
                    "name": meta.get("name", "CB Unknown"),
                    "location": meta.get("location", "N/A"),
                    "id": device_id,
                    "attributes": info.get("attributes", {}),
                    "telemetry": info.get("telemetry", {}),
                    "metadata": meta,
                }
            )

        logging.info("API response for /check-data: %s devices (CB)", len(data_array))
        return jsonify({"status": "success", "data": data_array})

    @app.route("/devices/available", methods=["GET"])
    def get_available_devices():
        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

        try:
            url = f"{shared.CORE_IOT_URL}/api/tenant/devices?pageSize=100&page=0&groupId={shared.GROUP_ID}"
            response = requests.get(url, headers=shared.HEADERS, timeout=15)
            response.raise_for_status()
            devices_data = response.json().get("data", [])

            available_devices = []
            for device in devices_data:
                device_id = device["id"]["id"]
                is_configured = device_id in shared.CUSTOM_CB_DEVICES
                available_devices.append(
                    {
                        "id": device_id,
                        "name": device.get("name", "Unknown Device"),
                        "type": device.get("type", "Unknown"),
                        "isConfigured": is_configured,
                        "configuredAs": (
                            shared.CUSTOM_CB_DEVICES.get(device_id, {}).get("name") if is_configured else None
                        ),
                    }
                )

            logging.info("Found %s available devices from CoreIoT", len(available_devices))
            return jsonify({"status": "success", "data": available_devices, "count": len(available_devices)})

        except requests.RequestException as e:
            logging.error("Error fetching available devices: %s", e)
            return jsonify({"status": "error", "message": "Cannot fetch devices from CoreIoT"}), 500

    @app.route("/devices/cb", methods=["POST"])
    def add_circuit_breaker():
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        device_id = data.get("deviceId")
        name = data.get("name")
        room_type = data.get("roomType", "custom")
        room_name = data.get("roomName", "")
        floor = data.get("floor")
        max_load = data.get("maxLoad", 32)

        if not device_id:
            return jsonify({"status": "error", "message": "Device ID is required"}), 400
        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        if room_name:
            location = room_name
        elif room_type in shared.ROOM_TYPE_MAP:
            location = shared.ROOM_TYPE_MAP[room_type]
        else:
            location = name

        metadata = {
            "type": "cb",
            "name": name,
            "location": location,
            "room_type": room_type,
            "room_name": room_name,
            "floor": floor,
            "max_load": max_load,
        }

        shared.DEVICE_METADATA_CACHE[device_id] = metadata
        shared.CUSTOM_CB_DEVICES[device_id] = metadata

        if device_id not in shared.latest_data:
            shared.latest_data[device_id] = {
                "telemetry": {},
                "attributes": {"POWER": "N/A"},
                "metadata": metadata,
            }
        else:
            shared.latest_data[device_id]["metadata"] = metadata

        shared.get_device_telemetry(device_id)
        shared.get_device_attributes(device_id)

        logging.info("Added new CB: %s (ID: %s) for %s", name, device_id, location)

        socketio.emit(
            "device_added",
            {"device_id": device_id, "metadata": metadata, "timestamp": datetime.now().isoformat()},
            room="dashboard",
        )

        return jsonify(
            {
                "status": "success",
                "message": f"CB '{name}' added successfully",
                "device": {
                    "id": device_id,
                    "name": name,
                    "type": "cb",
                    "location": location,
                    "roomType": room_type,
                    "roomName": room_name,
                    "floor": floor,
                    "maxLoad": max_load,
                },
            }
        )

    @app.route("/devices/cb/<string:device_id>", methods=["DELETE"])
    def delete_circuit_breaker(device_id):
        if device_id not in shared.CUSTOM_CB_DEVICES:
            return jsonify(
                {
                    "status": "error",
                    "message": "CB not found or cannot be deleted (not a custom CB)",
                }
            ), 404

        cb_name = shared.CUSTOM_CB_DEVICES[device_id].get("name", device_id)
        if device_id in shared.DEVICE_METADATA_CACHE:
            del shared.DEVICE_METADATA_CACHE[device_id]
        if device_id in shared.CUSTOM_CB_DEVICES:
            del shared.CUSTOM_CB_DEVICES[device_id]
        if device_id in shared.latest_data:
            del shared.latest_data[device_id]

        logging.info("Deleted CB: %s (ID: %s)", cb_name, device_id)

        socketio.emit("device_removed", {"device_id": device_id, "timestamp": datetime.now().isoformat()}, room="dashboard")

        return jsonify({"status": "success", "message": f"CB '{cb_name}' deleted successfully"})

    @app.route("/devices/cb", methods=["GET"])
    def list_circuit_breakers():
        cb_list = []
        for device_id, meta in shared.CUSTOM_CB_DEVICES.items():
            device_info = shared.latest_data.get(device_id, {})
            cb_list.append(
                {
                    "id": device_id,
                    "name": meta.get("name", "Unknown"),
                    "type": "cb",
                    "location": meta.get("location", "N/A"),
                    "roomType": meta.get("room_type", "custom"),
                    "roomName": meta.get("room_name", ""),
                    "floor": meta.get("floor"),
                    "maxLoad": meta.get("max_load", 32),
                    "attributes": device_info.get("attributes", {}),
                    "telemetry": device_info.get("telemetry", {}),
                }
            )

        return jsonify({"status": "success", "data": cb_list, "count": len(cb_list)})

    @app.route("/check-token", methods=["GET"])
    def check_token():
        if shared.verify_token():
            return jsonify({"status": "success", "message": "JWT_TOKEN is valid"})
        return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

    @app.route("/device/<string:device_id>", methods=["GET"])
    def get_device_detail(device_id):
        logging.info("Device detail request for: %s", device_id)

        if device_id in shared.latest_data:
            info = shared.latest_data[device_id]
            meta = info.get("metadata", {"type": "cb", "name": "CB Unknown", "location": "N/A"})
            return jsonify(
                {
                    "status": "success",
                    "device": {
                        "id": device_id,
                        "type": meta.get("type", "cb"),
                        "name": meta.get("name", "CB Unknown"),
                        "location": meta.get("location", "N/A"),
                        "attributes": info.get("attributes", {}),
                        "telemetry": info.get("telemetry", {}),
                        "metadata": meta,
                    },
                }
            )

        shared.get_device_telemetry(device_id)
        shared.get_device_attributes(device_id)

        if device_id in shared.latest_data:
            info = shared.latest_data[device_id]
            meta = info.get("metadata", {"type": "cb", "name": "CB Unknown", "location": "N/A"})
            return jsonify(
                {
                    "status": "success",
                    "device": {
                        "id": device_id,
                        "type": meta.get("type", "cb"),
                        "name": meta.get("name", "CB Unknown"),
                        "location": meta.get("location", "N/A"),
                        "attributes": info.get("attributes", {}),
                        "telemetry": info.get("telemetry", {}),
                        "metadata": meta,
                    },
                }
            )

        return jsonify({"status": "error", "message": "Device not found"}), 404

    @app.route("/device/<string:device_id>/history", methods=["GET"])
    def get_device_history(device_id):
        period = request.args.get("period", "day").lower()
        full_mode = period == "all"
        logging.info("Device history request for: %s, period: %s", device_id, period)

        def _parse_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        def _build_history(raw_data, include_ts_ms=False):
            history = []
            telemetry_map = {
                "ENERGY-Power": "power",
                "ENERGY-Voltage": "voltage",
                "ENERGY-Current": "current",
                "ENERGY-Today": "energy",
            }
            points_by_ts = {}

            for key, values in raw_data.items():
                metric = telemetry_map.get(key)
                if metric is None:
                    continue
                for entry in values or []:
                    ts = entry.get("ts")
                    if ts is None:
                        continue
                    if ts not in points_by_ts:
                        points_by_ts[ts] = {
                            "timestamp": datetime.fromtimestamp(ts / 1000).isoformat(),
                            "power": 0.0,
                            "voltage": 0.0,
                            "current": 0.0,
                            "energy": 0.0,
                        }
                        if include_ts_ms:
                            points_by_ts[ts]["tsMs"] = int(ts)
                    points_by_ts[ts][metric] = _parse_float(entry.get("value"))

            for ts in sorted(points_by_ts.keys()):
                history.append(points_by_ts[ts])
            return history

        def _fetch_timeseries(start_ts, end_ts, limit, agg, interval, timeout=20):
            keys = "ENERGY-Power,ENERGY-Voltage,ENERGY-Current,ENERGY-Today"
            url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
            params = {
                "keys": keys,
                "startTs": start_ts,
                "endTs": end_ts,
                "limit": limit,
                "agg": agg,
                "interval": interval,
            }
            response = requests.get(url, headers=shared.HEADERS, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()

        try:
            now = datetime.now()

            if full_mode:
                end_ts = int(now.timestamp() * 1000)
                try:
                    chunk_days = max(1, int(request.args.get("chunkDays", 3)))
                except ValueError:
                    return jsonify({"status": "error", "message": "chunkDays must be an integer"}), 400
                chunk_ms = chunk_days * 24 * 60 * 60 * 1000
                page_size_default = 5000
                page_size_max = 20000
                try:
                    page_size = int(request.args.get("pageSize", page_size_default))
                except ValueError:
                    return jsonify({"status": "error", "message": "pageSize must be an integer"}), 400
                page_size = max(1, min(page_size, page_size_max))

                cursor_param = request.args.get("cursor")
                start_ts_param = request.args.get("startTs", "0")
                try:
                    start_ts = int(cursor_param) if cursor_param is not None else int(start_ts_param)
                except ValueError:
                    return jsonify({"status": "error", "message": "cursor/startTs must be an integer timestamp in ms"}), 400

                full_history = []
                cursor = start_ts
                seen_ts_ms = set()
                next_cursor = None
                has_more = False
                reached_page_limit = False

                # Start with user-selected chunk size and automatically shrink on upstream failures.
                adaptive_chunk_ms = chunk_ms
                min_chunk_ms = 60 * 60 * 1000  # 1 hour

                while cursor <= end_ts:
                    chunk_end = min(cursor + adaptive_chunk_ms - 1, end_ts)
                    try:
                        raw_chunk = _fetch_timeseries(
                            start_ts=cursor,
                            end_ts=chunk_end,
                            limit=20000,
                            agg="NONE",
                            interval=0,
                            timeout=35,
                        )
                    except requests.RequestException as fetch_err:
                        if adaptive_chunk_ms <= min_chunk_ms:
                            raise fetch_err

                        adaptive_chunk_ms = max(min_chunk_ms, adaptive_chunk_ms // 2)
                        logging.warning(
                            "Full history fetch failed for %s in [%s,%s], reducing chunk to %sms: %s",
                            device_id,
                            cursor,
                            chunk_end,
                            adaptive_chunk_ms,
                            fetch_err,
                        )
                        continue

                    chunk_history = _build_history(raw_chunk, include_ts_ms=True)

                    for point in chunk_history:
                        ts_ms = int(point.get("tsMs") or 0)
                        if ts_ms <= 0 or ts_ms in seen_ts_ms:
                            continue

                        seen_ts_ms.add(ts_ms)
                        response_point = {
                            "timestamp": point["timestamp"],
                            "power": point["power"],
                            "voltage": point["voltage"],
                            "current": point["current"],
                            "energy": point["energy"],
                        }
                        full_history.append(response_point)

                        if len(full_history) >= page_size:
                            next_cursor = ts_ms + 1
                            has_more = next_cursor <= end_ts
                            reached_page_limit = True
                            break

                    if reached_page_limit:
                        break

                    cursor = chunk_end + 1

                    if adaptive_chunk_ms < chunk_ms:
                        adaptive_chunk_ms = min(chunk_ms, adaptive_chunk_ms * 2)

                if not reached_page_limit:
                    full_history.sort(key=lambda item: item["timestamp"])
                    has_more = False
                    next_cursor = None

                logging.info(
                    "Returning paged full history for %s: %s points, chunkDays=%s, hasMore=%s",
                    device_id,
                    len(full_history),
                    chunk_days,
                    has_more,
                )
                return jsonify(
                    {
                        "status": "success",
                        "period": "all",
                        "history": full_history,
                        "count": len(full_history),
                        "pageSize": page_size,
                        "cursor": start_ts,
                        "nextCursor": next_cursor,
                        "hasMore": has_more,
                    }
                )

            if period == "week":
                start_time = now - timedelta(days=7)
                limit = 168
                agg = "AVG"
                interval = 3600000
            elif period == "month":
                start_time = now - timedelta(days=30)
                limit = 720
                agg = "AVG"
                interval = 3600000
            else:
                start_time = now - timedelta(days=1)
                limit = 24
                agg = "NONE"
                interval = 0

            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)
            raw_data = _fetch_timeseries(
                start_ts=start_ts,
                end_ts=end_ts,
                limit=limit * 4,
                agg=agg,
                interval=interval,
            )
            history = _build_history(raw_data)

            if len(history) > limit:
                step = max(1, len(history) // limit)
                history = history[::step][:limit]

            logging.info("Returning %s history points for device %s", len(history), device_id)
            return jsonify(
                {
                    "status": "success",
                    "period": period,
                    "history": history,
                    "count": len(history),
                    "hasMore": False,
                    "nextCursor": None,
                }
            )
        except requests.RequestException as e:
            logging.error("Failed to fetch history from Core IoT for %s: %s", device_id, e)
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Cannot fetch history from CoreIoT",
                        "history": [],
                    }
                ),
                502,
            )
        except Exception as e:
            logging.error("Error fetching device history: %s", e)
            return jsonify({"status": "error", "message": str(e), "history": []}), 500

    @app.route("/device/<string:device_id>/history/full", methods=["GET"])
    def get_device_history_full(device_id):
        # Reuse the same logic through period=all so frontend can call either form.
        args = request.args.to_dict(flat=True)
        args["period"] = "all"
        with app.test_request_context(query_string=args):
            return get_device_history(device_id)

    @app.route("/control/<string:device_id>/<string:command>", methods=["POST"])
    def control_specific_device(device_id, command):
        logging.info("Control request: Device %s, Command: %s", device_id, command)

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401
        if command.lower() not in ["on", "off"]:
            return jsonify({"status": "error", "message": "Invalid command. Only 'on' or 'off' accepted."}), 400

        success, result = shared.send_rpc_to_device(device_id, command.upper())
        if success:
            return jsonify(result), 200

        status_code = 401 if "Token" in result.get("message", "") else 500
        return jsonify(result), status_code

    @app.route("/control/group/<string:command>", methods=["POST"])
    def control_group_devices(command):
        logging.info("Group control request: Command: %s", command)

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401
        if command.lower() not in ["on", "off"]:
            return jsonify({"status": "error", "message": "Invalid command. Only 'on' or 'off' accepted."}), 400

        try:
            device_ids = shared.get_devices_from_group()
            if not device_ids:
                return jsonify({"status": "error", "message": "No devices found in group."}), 404
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error getting device list: {e}"}), 500

        results = []
        all_success = True
        cmd_upper = command.upper()

        for device_id in device_ids:
            success, result = shared.send_rpc_to_device(device_id, cmd_upper)
            results.append(result)
            if not success:
                all_success = False
            time.sleep(0.1)

        summary = {
            "status": "success" if all_success else "partial_failure",
            "command_sent": cmd_upper,
            "total_devices": len(device_ids),
            "results": results,
        }
        return jsonify(summary), 200 if all_success else 207

    @app.route("/schedules", methods=["GET"])
    def get_schedules():
        try:
            schedules = shared.get_all_schedules()
            return jsonify(schedules), 200
        except Exception as e:
            logging.error("Error fetching schedules: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/schedules", methods=["POST"])
    def create_new_schedule():
        try:
            data = request.get_json()
            required_fields = ["name", "targetId", "action", "time", "days"]
            for field in required_fields:
                if field not in data:
                    return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400

            if data["action"] not in ["on", "off"]:
                return jsonify({"status": "error", "message": "Action must be 'on' or 'off'"}), 400

            valid_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if not isinstance(data["days"], list) or not all(d in valid_days for d in data["days"]):
                return (
                    jsonify({"status": "error", "message": "Days must be a list of valid day abbreviations"}),
                    400,
                )

            try:
                datetime.strptime(data["time"], "%H:%M")
            except ValueError:
                return jsonify({"status": "error", "message": "Time must be in HH:MM format"}), 400

            enabled = data.get("enabled", True)
            run_once = bool(data.get("runOnce", False))
            if run_once and len(data["days"]) != 1:
                return jsonify({"status": "error", "message": "One-time schedule must have exactly 1 day"}), 400

            schedule = shared.create_schedule(
                name=data["name"],
                target_id=data["targetId"],
                action=data["action"],
                time=data["time"],
                days=data["days"],
                enabled=enabled,
                run_once=run_once,
            )

            logging.info("Schedule created: %s - %s", schedule["id"], schedule["name"])
            socketio.emit("schedule_created", schedule, room="schedules")
            return jsonify(schedule), 201

        except Exception as e:
            logging.error("Error creating schedule: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/schedules/<string:schedule_id>", methods=["GET"])
    def get_single_schedule(schedule_id):
        try:
            schedule = shared.get_schedule_by_id(schedule_id)
            if schedule:
                return jsonify(schedule), 200
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        except Exception as e:
            logging.error("Error fetching schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/schedules/<string:schedule_id>", methods=["PUT"])
    def update_existing_schedule(schedule_id):
        try:
            data = request.get_json()
            if "action" in data and data["action"] not in ["on", "off"]:
                return jsonify({"status": "error", "message": "Action must be 'on' or 'off'"}), 400

            if "days" in data:
                valid_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                if not isinstance(data["days"], list) or not all(d in valid_days for d in data["days"]):
                    return (
                        jsonify({"status": "error", "message": "Days must be a list of valid day abbreviations"}),
                        400,
                    )

            if "time" in data:
                try:
                    datetime.strptime(data["time"], "%H:%M")
                except ValueError:
                    return jsonify({"status": "error", "message": "Time must be in HH:MM format"}), 400

            if "runOnce" in data and not isinstance(data["runOnce"], bool):
                return jsonify({"status": "error", "message": "runOnce must be a boolean"}), 400

            run_once_value = data.get("runOnce")
            next_days = data.get("days")
            if run_once_value is None:
                current_schedule = shared.get_schedule_by_id(schedule_id)
                if not current_schedule:
                    return jsonify({"status": "error", "message": "Schedule not found"}), 404
                run_once_value = bool(current_schedule.get("runOnce", False))
                if next_days is None:
                    next_days = current_schedule.get("days", [])

            if run_once_value and (not isinstance(next_days, list) or len(next_days) != 1):
                return jsonify({"status": "error", "message": "One-time schedule must have exactly 1 day"}), 400

            schedule = shared.update_schedule(
                schedule_id=schedule_id,
                name=data.get("name"),
                target_id=data.get("targetId"),
                action=data.get("action"),
                time=data.get("time"),
                days=data.get("days"),
                enabled=data.get("enabled"),
                run_once=data.get("runOnce"),
            )

            if schedule:
                logging.info("Schedule updated: %s", schedule_id)
                socketio.emit("schedule_updated", schedule, room="schedules")
                return jsonify(schedule), 200

            return jsonify({"status": "error", "message": "Schedule not found"}), 404

        except Exception as e:
            logging.error("Error updating schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/schedules/<string:schedule_id>", methods=["DELETE"])
    def delete_existing_schedule(schedule_id):
        try:
            success = shared.delete_schedule(schedule_id)
            if success:
                logging.info("Schedule deleted: %s", schedule_id)
                socketio.emit("schedule_deleted", {"id": schedule_id}, room="schedules")
                return jsonify({"status": "success", "message": "Schedule deleted"}), 200
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        except Exception as e:
            logging.error("Error deleting schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/schedules/<string:schedule_id>/toggle", methods=["POST"])
    def toggle_schedule(schedule_id):
        try:
            schedule = shared.get_schedule_by_id(schedule_id)
            if not schedule:
                return jsonify({"status": "error", "message": "Schedule not found"}), 404

            updated = shared.update_schedule(schedule_id=schedule_id, enabled=not schedule["enabled"])
            if updated:
                logging.info(
                    "Schedule %s toggled to %s",
                    schedule_id,
                    "enabled" if updated["enabled"] else "disabled",
                )
                socketio.emit("schedule_updated", updated, room="schedules")
                return jsonify(updated), 200

            return jsonify({"status": "error", "message": "Failed to toggle schedule"}), 500

        except Exception as e:
            logging.error("Error toggling schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    if shared.FORECAST_ENABLED:
        @app.route("/forecast", methods=["GET"])
        def trigger_forecast():
            logging.info("--- MANUAL FORECAST TRIGGERED ---")

            def _coreiot_hourly_kwh(start_dt: datetime, end_dt: datetime) -> dict[str, float]:
                start_ts = int(start_dt.timestamp() * 1000)
                end_ts = int(end_dt.timestamp() * 1000)
                device_ids = shared.get_tracked_device_ids()
                if not device_ids:
                    device_ids = shared.get_devices_from_group()

                totals_by_hour_ts: dict[int, float] = {}
                for device_id in device_ids:
                    try:
                        url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                        params = {
                            "keys": "ENERGY-Power",
                            "startTs": start_ts,
                            "endTs": end_ts,
                            "limit": 10000,
                            "agg": "AVG",
                            "interval": 3600000,
                        }
                        resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                        resp.raise_for_status()
                        raw = resp.json()

                        for entry in raw.get("ENERGY-Power", []):
                            ts = entry.get("ts")
                            if ts is None:
                                continue
                            try:
                                power_w = float(entry.get("value") or 0.0)
                            except (TypeError, ValueError):
                                continue
                            dt_hour = datetime.fromtimestamp(ts / 1000).replace(minute=0, second=0, microsecond=0)
                            hour_ts = int(dt_hour.timestamp() * 1000)
                            totals_by_hour_ts[hour_ts] = totals_by_hour_ts.get(hour_ts, 0.0) + max(0.0, power_w)
                    except Exception as e:
                        logging.warning("Forecast source skipped device %s due to error: %s", device_id, e)

                hourly_kwh = {}
                for hour_ts in sorted(totals_by_hour_ts.keys()):
                    dt_obj = datetime.fromtimestamp(hour_ts / 1000)
                    iso_ts = dt_obj.strftime("%Y-%m-%dT%H:00:00")
                    hourly_kwh[iso_ts] = round(totals_by_hour_ts[hour_ts] / 1000.0, 6)
                return hourly_kwh

            def _coreiot_latest_total_kwh() -> float:
                device_ids = shared.get_tracked_device_ids()
                if not device_ids:
                    device_ids = shared.get_devices_from_group()

                total_kwh = 0.0
                for device_id in device_ids:
                    try:
                        url = (
                            f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/"
                            "values/timeseries?keys=ENERGY-Total&limit=1"
                        )
                        resp = requests.get(url, headers=shared.HEADERS, timeout=20)
                        resp.raise_for_status()
                        raw = resp.json()
                        entries = raw.get("ENERGY-Total", [])
                        if not entries:
                            continue
                        total_kwh += float(entries[0].get("value") or 0.0)
                    except Exception as e:
                        logging.warning("Forecast total source skipped device %s due to error: %s", device_id, e)

                return round(max(0.0, total_kwh), 6)

            with shared.lock:
                if len(shared.hourly_kwh_global) < 1:
                    logging.info("Forecast cache is sparse, attempting CoreIoT monthly history fetch")

                now = datetime.now()
                start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                # Use CoreIoT as the primary source so forecast math matches Energy page totals.
                coreiot_history = _coreiot_hourly_kwh(start_of_month, now)
                if coreiot_history:
                    # Match the value users see on CoreIoT dashboard.
                    consumed = _coreiot_latest_total_kwh()
                    if consumed <= 0:
                        consumed = sum(coreiot_history.values())
                    recent_history = dict(sorted(coreiot_history.items(), key=lambda x: x[0], reverse=True)[:1200])
                else:
                    consumed = sum(
                        v for k, v in shared.hourly_kwh_global.items() if datetime.fromisoformat(k) >= start_of_month
                    )
                    recent_history = dict(
                        sorted(shared.hourly_kwh_global.items(), key=lambda x: x[0], reverse=True)[:1200]
                    )

                if len(recent_history) < 1:
                    return jsonify({"status": "error", "message": "Not enough data"}), 400

            logging.info("Sending request to AI Server... (Consumed: %.2f kWh)", consumed)
            result = shared.forecast_client.predict(recent_history, consumed)

            if result:
                result["ConsumedThisMonthKwh"] = round(consumed, 2)
                shared.predicted_details_cache = result.get("PredictedHourlyDetails", {})
                logging.info("FORECAST SUCCESS -> Bill: %s VND", f"{result['PredictedBillVND']:,}")

                try:
                    with open("forecast_result.json", "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=4, ensure_ascii=False)
                except Exception:
                    pass

                return jsonify(result)

            return jsonify({"status": "error", "message": "AI Server not responding"}), 500

        @app.route("/forecast/summary", methods=["GET"])
        def get_forecast_summary():
            try:
                if os.path.exists("forecast_result.json"):
                    with open("forecast_result.json", "r", encoding="utf-8") as f:
                        full_result = json.load(f)

                    summary_data = {
                        "tien_can_tra_vnd": full_result.get("PredictedBillVND", 0),
                        "tong_kwh_du_doan_duoc": full_result.get("TotalKwhForecasted", 0),
                        "tong_kwh_ca_thang": full_result.get("TotalKwhMonth", 0),
                        "kwh_da_tieu_thu_thang_nay": full_result.get("ConsumedThisMonthKwh", 0),
                    }

                    return jsonify({"status": "success", "data": summary_data})

                return (
                    jsonify(
                        {
                            "status": "empty",
                            "message": "Chưa có dữ liệu dự báo. Vui lòng nhấn nút 'Dự báo' trước.",
                        }
                    ),
                    404,
                )

            except Exception as e:
                logging.error("Error reading forecast summary: %s", e)
                return jsonify({"status": "error", "message": str(e)}), 500

        @app.route("/energy", methods=["GET"])
        def get_energy_data():
            period = request.args.get("period", "day")
            now = datetime.now()

            start_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

            if period == "day":
                start_time = start_of_today
            elif period == "week":
                seven_days_ago = now - timedelta(days=7)
                start_time = max(seven_days_ago, start_of_this_month)
            elif period == "month":
                start_time = start_of_this_month
            else:
                start_time = now - timedelta(hours=24)

            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)

            # Prefer tracked CB devices; fallback to all devices in group.
            device_ids = shared.get_tracked_device_ids()
            if not device_ids:
                device_ids = shared.get_devices_from_group()

            # Aggregate hourly average power across devices from CoreIoT, then convert to kWh.
            totals_by_hour_ts: dict[int, float] = {}
            for device_id in device_ids:
                try:
                    url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                    params = {
                        "keys": "ENERGY-Power",
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "limit": 10000,
                        "agg": "AVG",
                        "interval": 3600000,
                    }
                    resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                    resp.raise_for_status()
                    raw = resp.json()

                    for entry in raw.get("ENERGY-Power", []):
                        ts = entry.get("ts")
                        if ts is None:
                            continue
                        try:
                            power_w = float(entry.get("value") or 0.0)
                        except (TypeError, ValueError):
                            continue
                        dt_hour = datetime.fromtimestamp(ts / 1000).replace(minute=0, second=0, microsecond=0)
                        hour_ts = int(dt_hour.timestamp() * 1000)
                        totals_by_hour_ts[hour_ts] = totals_by_hour_ts.get(hour_ts, 0.0) + max(0.0, power_w)
                except Exception as e:
                    logging.warning("Energy aggregation skipped device %s due to error: %s", device_id, e)

            response_data = []
            for ts in sorted(totals_by_hour_ts.keys()):
                dt_obj = datetime.fromtimestamp(ts / 1000)
                kwh = totals_by_hour_ts[ts] / 1000.0
                response_data.append(
                    {
                        "timestamp": dt_obj.isoformat(),
                        "consumption": round(max(0.0, kwh), 6),
                        "cost": round(max(0.0, kwh) * PRICE_PER_KWH, 2),
                    }
                )

            # If upstream telemetry is unavailable, keep backward-compatible fallback.
            if not response_data:
                with shared.lock:
                    sorted_items = sorted(shared.hourly_kwh_global.items(), key=lambda x: x[0])
                    recent_items = sorted_items[-750:]

                    for iso_ts, kwh in recent_items:
                        try:
                            dt_obj = datetime.fromisoformat(iso_ts)
                            if dt_obj >= start_time:
                                response_data.append(
                                    {
                                        "timestamp": iso_ts,
                                        "consumption": kwh,
                                        "cost": kwh * PRICE_PER_KWH,
                                    }
                                )
                        except ValueError:
                            continue

            return jsonify(response_data)

        @app.route("/energy/summary", methods=["GET"])
        def get_energy_summary():
            """Return CoreIoT latest cumulative total (ENERGY-Total) for Energy page summary cards."""
            period = request.args.get("period", "month")

            if period not in ["day", "month"]:
                return jsonify({"status": "success", "data": {"totalConsumption": 0.0, "totalCost": 0.0}})

            device_ids = shared.get_tracked_device_ids()
            if not device_ids:
                device_ids = shared.get_devices_from_group()

            total_kwh = 0.0
            metric_key = "ENERGY-Today" if period == "day" else "ENERGY-Total"
            for device_id in device_ids:
                try:
                    url = (
                        f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/"
                        f"values/timeseries?keys={metric_key}&limit=1"
                    )
                    resp = requests.get(url, headers=shared.HEADERS, timeout=20)
                    resp.raise_for_status()
                    raw = resp.json()
                    entries = raw.get(metric_key, [])
                    if entries:
                        total_kwh += float(entries[0].get("value") or 0.0)
                except Exception as e:
                    logging.warning("Energy summary skipped device %s due to error: %s", device_id, e)

            total_kwh = round(max(0.0, total_kwh), 4)
            total_cost = round(total_kwh * PRICE_PER_KWH, 2)
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "totalConsumption": total_kwh,
                        "totalCost": total_cost,
                    },
                }
            )
