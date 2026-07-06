#Schedule API routes
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from flask import jsonify, request

from app_core import shared
from app_core.auth_routes import _get_current_user


def register_schedule_routes(app, socketio):
    """Đăng ký các route quản lý lịch hẹn."""

    @app.route("/api/schedules", methods=["GET"])
    def get_schedules():
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            schedules = shared.get_all_schedules()
            user_schedules = [s for s in schedules if s.get("userId") == user["id"]]
            return jsonify(user_schedules), 200
        except Exception as e:
            logging.error("Error fetching schedules: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules", methods=["POST"])
    def create_new_schedule():
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

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
                user_id=user["id"],
            )

            logging.info("Schedule created: %s - %s", schedule["id"], schedule["name"])
            socketio.emit("schedule_created", schedule, room=f"user_{user['id']}_schedules")
            return jsonify(schedule), 201

        except Exception as e:
            logging.error("Error creating schedule: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules/<string:schedule_id>", methods=["GET"])
    def get_single_schedule(schedule_id):
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            schedule = shared.get_schedule_by_id(schedule_id)
            if schedule and schedule.get("userId") == user["id"]:
                return jsonify(schedule), 200
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        except Exception as e:
            logging.error("Error fetching schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules/<string:schedule_id>", methods=["PUT"])
    def update_existing_schedule(schedule_id):
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            current_schedule = shared.get_schedule_by_id(schedule_id)
            if not current_schedule or current_schedule.get("userId") != user["id"]:
                return jsonify({"status": "error", "message": "Schedule not found or no permission"}), 404

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
                socketio.emit("schedule_updated", schedule, room=f"user_{user['id']}_schedules")
                return jsonify(schedule), 200

            return jsonify({"status": "error", "message": "Schedule not found"}), 404

        except Exception as e:
            logging.error("Error updating schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules/<string:schedule_id>", methods=["DELETE"])
    def delete_existing_schedule(schedule_id):
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            current_schedule = shared.get_schedule_by_id(schedule_id)
            if not current_schedule or current_schedule.get("userId") != user["id"]:
                return jsonify({"status": "error", "message": "Schedule not found or no permission"}), 404

            success = shared.delete_schedule(schedule_id)
            if success:
                logging.info("Schedule deleted: %s", schedule_id)
                socketio.emit("schedule_deleted", {"id": schedule_id}, room=f"user_{user['id']}_schedules")
                return jsonify({"status": "success", "message": "Schedule deleted"}), 200
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        except Exception as e:
            logging.error("Error deleting schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules/<string:schedule_id>/toggle", methods=["POST"])
    def toggle_schedule(schedule_id):
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            schedule = shared.get_schedule_by_id(schedule_id)
            if not schedule or schedule.get("userId") != user["id"]:
                return jsonify({"status": "error", "message": "Schedule not found or no permission"}), 404

            updated = shared.update_schedule(schedule_id=schedule_id, enabled=not schedule["enabled"])
            if updated:
                logging.info(
                    "Schedule %s toggled to %s",
                    schedule_id,
                    "enabled" if updated["enabled"] else "disabled",
                )
                socketio.emit("schedule_updated", updated, room=f"user_{user['id']}_schedules")
                return jsonify(updated), 200

            return jsonify({"status": "error", "message": "Failed to toggle schedule"}), 500

        except Exception as e:
            logging.error("Error toggling schedule %s: %s", schedule_id, e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/schedules/auto-scenarios", methods=["POST"])
    def generate_auto_scenarios():
        """Generate data-driven on/off schedules from historical hourly energy usage."""
        try:
            user, err = _get_current_user()
            if err:
                response, status_code = err
                return response, status_code

            payload = request.get_json(silent=True) or {}
            lookback_days = int(payload.get("lookbackDays", 14) or 14)
            max_devices = int(payload.get("maxDevices", 8) or 8)
            min_samples = int(payload.get("minSamples", 12) or 12)
            auto_apply = bool(payload.get("autoApply", True))
            buffer_hours = int(payload.get("bufferHours", 0) or 0)
            target_device_ids = payload.get("deviceIds")

            if lookback_days < 1 or lookback_days > 90:
                return jsonify({"status": "error", "message": "lookbackDays must be between 1 and 90"}), 400
            if max_devices < 1 or max_devices > 50:
                return jsonify({"status": "error", "message": "maxDevices must be between 1 and 50"}), 400
            if buffer_hours < 0 or buffer_hours > 3:
                return jsonify({"status": "error", "message": "bufferHours must be between 0 and 3"}), 400

            now = datetime.now()
            start_dt = now - timedelta(days=lookback_days)
            start_ts = int(start_dt.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
            end_ts = int(now.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)

            def _fetch_coreiot_hourly_points(device_id: str) -> list[dict]:
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                params = {
                    "keys": "ENERGY-Total",
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "limit": 50000,
                    "orderBy": "ASC",
                }
                resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=25)
                resp.raise_for_status()
                raw = resp.json()

                entries = raw.get("ENERGY-Total", [])
                if not entries:
                    return []

                parsed = []
                for e in entries:
                    try:
                        ts_ms = int(e["ts"])
                        val = float(e.get("value") or 0.0)
                        parsed.append((ts_ms, max(0.0, val)))
                    except (TypeError, ValueError, KeyError):
                        continue
                parsed.sort(key=lambda x: x[0])

                if len(parsed) < 2:
                    return []

                hourly_kwh: dict = {}
                prev_ts_ms, prev_total = parsed[0]
                for ts_ms, total_kwh in parsed[1:]:
                    delta = total_kwh - prev_total
                    if delta > 0:
                        dt = datetime.fromtimestamp(ts_ms / 1000).replace(
                            minute=0, second=0, microsecond=0
                        )
                        hourly_kwh[dt] = hourly_kwh.get(dt, 0.0) + delta
                    prev_ts_ms, prev_total = ts_ms, total_kwh

                return [{"hour": dt, "energy_kwh": kwh} for dt, kwh in hourly_kwh.items()]

            tracked_device_ids = shared.get_user_devices(user["id"])
            if isinstance(target_device_ids, list) and target_device_ids:
                device_ids = [d for d in tracked_device_ids if d in set(target_device_ids)]
            else:
                device_ids = tracked_device_ids

            if not device_ids:
                return jsonify({"status": "empty", "message": "No devices found"}), 200

            suggestions = []
            created_schedules = []
            existing_schedules = shared.get_all_schedules()

            for device_id in device_ids[:max_devices]:
                try:
                    device_points = _fetch_coreiot_hourly_points(device_id)
                except Exception as fetch_err:
                    logging.warning("Auto scenario: failed fetching CoreIoT history for %s: %s", device_id, fetch_err)
                    continue

                if len(device_points) < min_samples:
                    continue

                hourly_energy = defaultdict(float)
                weekday_hits = defaultdict(int)
                for point in device_points:
                    dt = point.get("hour")
                    if not isinstance(dt, datetime):
                        continue
                    try:
                        energy = float(point.get("energy_kwh") or 0.0)
                    except (TypeError, ValueError):
                        energy = 0.0
                    if energy <= 0:
                        continue
                    hourly_energy[dt.hour] += energy
                    day_code = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dt.weekday()]
                    weekday_hits[day_code] += 1

                if not hourly_energy:
                    continue

                max_hour_energy = max(hourly_energy.values())
                threshold = max_hour_energy * 0.4
                active_hours = sorted([h for h, e in hourly_energy.items() if e >= threshold])
                if not active_hours:
                    continue

                segments: list[list[int]] = []
                current_segment = [active_hours[0]]
                for h in active_hours[1:]:
                    if h == current_segment[-1] + 1:
                        current_segment.append(h)
                    else:
                        segments.append(current_segment)
                        current_segment = [h]
                segments.append(current_segment)

                segments_ranked = sorted(
                    segments,
                    key=lambda seg: sum(hourly_energy.get(hh, 0.0) for hh in seg),
                    reverse=True,
                )
                best_energy = sum(hourly_energy.get(hh, 0.0) for hh in segments_ranked[0])

                top_segments = [segments_ranked[0]]
                if len(segments_ranked) > 1:
                    second_energy = sum(hourly_energy.get(hh, 0.0) for hh in segments_ranked[1])
                    if second_energy >= best_energy * 0.30:
                        top_segments.append(segments_ranked[1])

                top_segments.sort(key=lambda seg: seg[0])

                max_occ_per_day = max(1, (lookback_days + 6) // 7)
                days = [
                    d for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                    if weekday_hits[d] / max_occ_per_day >= 0.30
                ]
                if not days:
                    days = [d for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] if weekday_hits[d] > 0]
                if not days:
                    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

                metadata = (
                    shared.CUSTOM_CB_DEVICES.get(device_id)
                    or shared.DEVICE_METADATA_CACHE.get(device_id)
                    or shared.latest_data.get(device_id, {}).get("metadata")
                    or {}
                )
                device_name = metadata.get("name") or f"Device {device_id[-6:]}"

                peaks_list = []
                for i, seg in enumerate(top_segments):
                    on_hour = (seg[0] - buffer_hours) % 24
                    off_hour = (seg[-1] + 1 + buffer_hours) % 24
                    on_time = f"{on_hour:02d}:00"
                    off_time = f"{off_hour:02d}:00"
                    suffix = f" P{i + 1}" if len(top_segments) > 1 else ""
                    seg_kwh = round(sum(hourly_energy.get(hh, 0.0) for hh in seg), 4)
                    peaks_list.append({
                        "onSchedule": {
                            "name": f"Auto ON {device_name}{suffix}",
                            "targetId": device_id,
                            "action": "on",
                            "time": on_time,
                            "days": days,
                            "enabled": True,
                        },
                        "offSchedule": {
                            "name": f"Auto OFF {device_name}{suffix}",
                            "targetId": device_id,
                            "action": "off",
                            "time": off_time,
                            "days": days,
                            "enabled": True,
                        },
                        "analysis": {
                            "peakWindow": [seg[0], seg[-1]],
                            "bufferHours": buffer_hours,
                            "extendedWindow": [on_hour, (off_hour - 1) % 24],
                            "totalKwhInWindow": seg_kwh,
                        },
                    })

                suggestion = {
                    "deviceId": device_id,
                    "deviceName": device_name,
                    "days": days,
                    "peaks": peaks_list,
                    "analysis": {
                        "samples": len(device_points),
                        "activeHours": active_hours,
                        "dataSource": "energy_total_delta",
                        "lookbackDays": lookback_days,
                    },
                }
                suggestions.append(suggestion)

                if auto_apply:
                    existing_keys = {
                        (
                            sch.get("targetId"),
                            sch.get("action"),
                            sch.get("time"),
                            ",".join(sorted(sch.get("days", []))),
                            bool(sch.get("source") == "data_driven"),
                        )
                        for sch in existing_schedules
                    }

                    for peak in peaks_list:
                        for schedule_payload in (peak["onSchedule"], peak["offSchedule"]):
                            dedupe_key = (
                                schedule_payload["targetId"],
                                schedule_payload["action"],
                                schedule_payload["time"],
                                ",".join(sorted(schedule_payload["days"])),
                                True,
                            )
                            if dedupe_key in existing_keys:
                                continue

                        created = shared.create_schedule(
                            name=schedule_payload["name"],
                            target_id=schedule_payload["targetId"],
                            action=schedule_payload["action"],
                            time=schedule_payload["time"],
                            days=schedule_payload["days"],
                            enabled=True,
                            run_once=False,
                            source="data_driven",
                            source_run_id=None,
                            approval_status="approved",
                            execution_priority=80,
                            metadata={
                                "generator": "auto_scenarios",
                                "lookbackDays": lookback_days,
                                "deviceId": device_id,
                            },
                            user_id=user["id"],
                        )
                        created_schedules.append(created)
                        existing_keys.add(dedupe_key)

            if auto_apply and created_schedules:
                for schedule in created_schedules:
                    socketio.emit("schedule_created", schedule, room=f"user_{user['id']}_schedules")

            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "lookbackDays": lookback_days,
                        "bufferHours": buffer_hours,
                        "autoApply": auto_apply,
                        "suggestionCount": len(suggestions),
                        "createdSchedulesCount": len(created_schedules),
                        "suggestions": suggestions,
                        "createdSchedules": created_schedules,
                    },
                }
            )
        except Exception as e:
            logging.error("Error generating auto scenarios: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    logging.info("Schedule routes registered.")
