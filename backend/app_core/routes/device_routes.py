#Device API routes
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from flask import jsonify, request

from app_core import shared
from app_core.auth_routes import _get_current_user
from database import (
    create_device, update_device, delete_device,
)


def register_device_routes(app, socketio):
    #Đăng ký các route quản lý thiết bị.
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
            "ENERGY-Total": "energy_total",
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
                        "energy_total": 0.0,
                    }
                    if include_ts_ms:
                        points_by_ts[ts]["tsMs"] = int(ts)
                points_by_ts[ts][metric] = _parse_float(entry.get("value"))

        for ts in sorted(points_by_ts.keys()):
            history.append(points_by_ts[ts])
        return history

    def _derive_energy_from_total(history_points, bucket_period: str) -> dict[str, float]:
        parsed = []
        for point in history_points:
            try:
                ts = datetime.fromisoformat(point["timestamp"])
                total = float(point.get("energy_total") or 0.0)
                parsed.append((ts, max(0.0, total)))
            except (TypeError, ValueError):
                continue

        if len(parsed) < 2:
            logging.debug(
                "_derive_energy_from_total: Not enough points (%d) for period %s",
                len(parsed), bucket_period,
            )
            return {}

        parsed.sort(key=lambda x: x[0])
        logging.debug(
            "_derive_energy_from_total: Processing %d points for period %s",
            len(parsed), bucket_period,
        )

        by_bucket = defaultdict(float)
        seen_deltas_by_day = defaultdict(dict)

        prev_total = parsed[0][1]
        prev_ts = parsed[0][0]

        for idx, (ts, total) in enumerate(parsed[1:], 1):
            time_gap_sec = (ts - prev_ts).total_seconds()
            time_gap_min = time_gap_sec / 60
            day_key = ts.date().isoformat()
            delta = total - prev_total

            if delta < 0:
                logging.debug("Point %d: Counter reset detected, delta=%.6f → 0", idx, delta)
                delta = 0.0
            elif time_gap_min > 30:
                if delta < 0.05:
                    logging.debug("Point %d: Duplicate value detected (gap=%.0fmin, delta=%.6f), skipping", idx, time_gap_min, delta)
                    delta = 0.0
                else:
                    logging.debug("Point %d: Gap %.0f min detected with delta %.6f", idx, time_gap_min, delta)
            elif ts.date() > prev_ts.date():
                logging.debug("Point %d: Day boundary crossed, delta stays %.6f", idx, delta)
                seen_deltas_by_day[day_key] = {}
            else:
                delta_rounded = round(delta, 4)
                if 0 < delta_rounded <= 0.01 and delta_rounded in seen_deltas_by_day[day_key]:
                    logging.debug("Point %d: Repeated tiny delta (%.6f <= 0.01) in same day, skipping", idx, delta_rounded)
                    delta = 0.0
                elif delta_rounded > 0:
                    seen_deltas_by_day[day_key][delta_rounded] = True

            prev_total = total
            prev_ts = ts

            if delta <= 0:
                continue

            if bucket_period == "day":
                bucket = ts.replace(minute=0, second=0, microsecond=0)
            else:
                bucket = ts.replace(hour=0, minute=0, second=0, microsecond=0)

            logging.debug(
                "Point %d: ts=%s, gap=%.0fm, delta=%.6f → bucket=%s",
                idx, ts.isoformat(), time_gap_min, delta, bucket.isoformat(),
            )
            by_bucket[bucket.isoformat()] += delta

        result = {k: round(v, 6) for k, v in by_bucket.items() if v > 0}
        logging.debug("_derive_energy_from_total result for %s: %s", bucket_period, result)
        return result

    def _derive_energy_profile_from_total(history_points) -> dict[str, float]:
        parsed = []
        for point in history_points:
            try:
                ts = datetime.fromisoformat(point["timestamp"])
                total = float(point.get("energy_total") or 0.0)
                parsed.append((ts, max(0.0, total)))
            except (TypeError, ValueError):
                continue

        if not parsed:
            return {}

        parsed.sort(key=lambda x: x[0])
        profile_by_ts = {}
        current_day = None
        baseline_total = 0.0
        prev_total = None

        for ts, total in parsed:
            day_key = ts.date().isoformat()
            if day_key != current_day:
                current_day = day_key
                baseline_total = total
                prev_total = total

            if prev_total is not None and total < prev_total:
                baseline_total = total

            energy_value = max(0.0, total - baseline_total)
            profile_by_ts[ts.isoformat()] = round(energy_value, 6)
            prev_total = total

        return profile_by_ts

    def _fetch_timeseries(device_id, start_ts, end_ts, limit, agg, interval, timeout=20):
        keys = "ENERGY-Power,ENERGY-Voltage,ENERGY-Current,ENERGY-Today,ENERGY-Total"
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

    def _fetch_energy_deltas_by_bucket(device_id, start_ts: int, end_ts: int, bucket_period: str) -> dict[str, float]:
        url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
        params = {
            "keys": "ENERGY-Total",
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": 50000,
            "agg": "NONE",
            "interval": 0,
        }
        response = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
        response.raise_for_status()
        raw = response.json()
        entries = raw.get("ENERGY-Total", [])
        logging.debug(
            "_fetch_energy_deltas_by_bucket: Fetched %d raw entries for period %s",
            len(entries), bucket_period,
        )
        if len(entries) < 2:
            logging.warning("Not enough entries (%d) for %s", len(entries), bucket_period)
            return {}

        parsed = []
        for entry in entries:
            try:
                ts_ms = int(entry.get("ts"))
                total_kwh = float(entry.get("value") or 0.0)
                parsed.append((ts_ms, max(0.0, total_kwh)))
            except (TypeError, ValueError):
                continue

        if len(parsed) < 2:
            logging.warning("Not enough parsed entries (%d) for %s", len(parsed), bucket_period)
            return {}

        parsed.sort(key=lambda x: x[0])

        by_bucket = defaultdict(float)
        seen_deltas_by_day = defaultdict(dict)

        prev_total = parsed[0][1]
        prev_ts_ms = parsed[0][0]

        for idx, (ts_ms, total_kwh) in enumerate(parsed[1:], 1):
            dt = datetime.fromtimestamp(ts_ms / 1000)
            prev_dt = datetime.fromtimestamp(prev_ts_ms / 1000)
            day_key = dt.date().isoformat()

            time_gap_sec = (ts_ms - prev_ts_ms) / 1000
            time_gap_min = time_gap_sec / 60
            delta = total_kwh - prev_total

            if delta < 0:
                logging.debug("Entry %d: Counter reset (%.6f → %.6f), setting delta=0", idx, prev_total, total_kwh)
                delta = 0.0
            elif time_gap_min > 30:
                if delta < 0.05:
                    logging.debug("Entry %d: Duplicate value detected (gap=%.0fmin, delta=%.6f), skipping", idx, time_gap_min, delta)
                    delta = 0.0
                else:
                    logging.debug("Entry %d: Gap %.0f min detected with delta %.6f", idx, time_gap_min, delta)
            elif dt.date() > prev_dt.date():
                logging.debug("Entry %d: Day boundary crossed, delta stays %.6f", idx, delta)
                seen_deltas_by_day[day_key] = {}
            else:
                delta_rounded = round(delta, 4)
                if 0 < delta_rounded <= 0.01 and delta_rounded in seen_deltas_by_day[day_key]:
                    logging.debug("Entry %d: Repeated tiny delta (%.6f <= 0.01) in same day, skipping", idx, delta_rounded)
                    delta = 0.0
                elif delta_rounded > 0:
                    seen_deltas_by_day[day_key][delta_rounded] = True

            prev_total = total_kwh
            prev_ts_ms = ts_ms

            if delta <= 0:
                continue

            if bucket_period == "day":
                bucket = dt.replace(minute=0, second=0, microsecond=0)
            else:
                bucket = dt.replace(hour=0, minute=0, second=0, microsecond=0)

            logging.debug(
                "Entry %d: ts=%s, gap=%.0fm, delta=%.6f → bucket=%s",
                idx, dt.isoformat(), time_gap_min, delta, bucket.isoformat(),
            )
            by_bucket[bucket.isoformat()] += delta

        result = {k: round(v, 6) for k, v in by_bucket.items() if v > 0}
        logging.debug("_fetch_energy_deltas_by_bucket result for %s: %s", bucket_period, result)
        return result

    # Routes
    @app.route("/api/check-data", methods=["GET"])
    def check_data():
        user, err = _get_current_user()
        if err:
            return err

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

        if not shared.latest_data:
            logging.warning("/check-data called but no data cached yet. Forcing fetch for configured CB devices.")
            user_devices = [k for k, v in shared.CUSTOM_CB_DEVICES.items() if v.get("user_id") == user["id"]]
            for device_id in user_devices:
                shared.get_device_telemetry(device_id)
                shared.get_device_attributes(device_id)

        data_array = []
        for device_id, info in shared.latest_data.items():
            cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
            if not cb_config or cb_config.get("user_id") != user["id"]:
                continue

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

    @app.route("/api/devices/available", methods=["GET"])
    def get_available_devices():
        user, err = _get_current_user()
        if err:
            return err

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

        try:
            user_group_id = shared.get_user_group_id(user["id"])
            device_ids = shared.get_devices_from_group(user_group_id)

            available_devices = []
            from db_users import find_user_by_id
            for device_id in device_ids:
                cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
                if cb_config:
                    owner_id = cb_config.get("user_id")
                    if owner_id:
                        owner = find_user_by_id(owner_id)
                        if not owner:
                            logging.info(
                                "Cleaning up orphaned device %s from deleted user %s",
                                device_id, owner_id,
                            )
                            delete_device(device_id)
                            if device_id in shared.DEVICE_METADATA_CACHE:
                                del shared.DEVICE_METADATA_CACHE[device_id]
                            if device_id in shared.CUSTOM_CB_DEVICES:
                                del shared.CUSTOM_CB_DEVICES[device_id]
                            if device_id in shared.latest_data:
                                del shared.latest_data[device_id]
                            cb_config = None
                        elif owner_id != user["id"]:
                            continue
                    elif cb_config.get("user_id") != user["id"]:
                        continue

                name = "Unknown Device"
                dev_type = "Unknown"

                try:
                    info_url = f"{shared.CORE_IOT_URL}/api/device/{device_id}"
                    info_resp = requests.get(info_url, headers=shared.HEADERS, timeout=10)
                    info_resp.raise_for_status()
                    dev = info_resp.json()
                    name = dev.get("name", name)
                    dev_type = dev.get("type", dev_type)
                except requests.RequestException:
                    pass

                is_configured = cb_config is not None
                available_devices.append(
                    {
                        "id": device_id,
                        "name": name,
                        "type": dev_type,
                        "isConfigured": is_configured,
                        "configuredAs": (cb_config.get("name") if is_configured else None),
                    }
                )

            logging.info("Found %s available devices from CoreIoT", len(available_devices))
            return jsonify({"status": "success", "data": available_devices, "count": len(available_devices)})

        except requests.RequestException as e:
            logging.error("Error fetching available devices: %s", e)
            return jsonify({"status": "error", "message": "Cannot fetch devices from CoreIoT"}), 500

    @app.route("/api/devices/cb", methods=["POST"])
    def add_circuit_breaker():
        user, err = _get_current_user()
        if err:
            return err

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
            "overcurrent_threshold": data.get("overcurrentThreshold", 20.0),
            "overcurrent_enabled": data.get("overcurrentEnabled", False),
            "user_id": user["id"],
        }

        create_device(
            device_id=device_id, user_id=user["id"], name=name, device_type="cb",
            location=location, room_type=room_type, room_name=room_name,
            floor=floor, max_load=max_load,
            overcurrent_threshold=metadata["overcurrent_threshold"],
            overcurrent_enabled=metadata["overcurrent_enabled"],
        )

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
            {"device": {"id": device_id, "metadata": metadata}, "timestamp": datetime.now().isoformat()},
            room=f"user_{user['id']}_dashboard",
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
                    "overcurrentThreshold": metadata["overcurrent_threshold"],
                    "overcurrentEnabled": metadata["overcurrent_enabled"],
                },
            }
        )

    @app.route("/devices/cb/<string:device_id>", methods=["PUT"])
    def update_circuit_breaker(device_id):
        user, err = _get_current_user()
        if err:
            return err

        if device_id not in shared.CUSTOM_CB_DEVICES or shared.CUSTOM_CB_DEVICES[device_id].get("user_id") != user["id"]:
            return jsonify({"status": "error", "message": "CB not found or no permission"}), 404

        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        current_meta = shared.CUSTOM_CB_DEVICES[device_id]

        name = data.get("name", current_meta.get("name"))
        room_type = data.get("roomType", current_meta.get("room_type", "custom"))
        room_name = data.get("roomName", current_meta.get("room_name", ""))
        floor = data.get("floor", current_meta.get("floor"))
        max_load = data.get("maxLoad", current_meta.get("max_load", 32))

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
            "overcurrent_threshold": data.get("overcurrentThreshold", current_meta.get("overcurrent_threshold", 20.0)),
            "overcurrent_enabled": data.get("overcurrentEnabled", current_meta.get("overcurrent_enabled", False)),
            "user_id": user["id"],
        }

        update_device(
            device_id=device_id, name=name, location=location,
            room_type=room_type, room_name=room_name, floor=floor, max_load=max_load,
            overcurrent_threshold=metadata["overcurrent_threshold"],
            overcurrent_enabled=metadata["overcurrent_enabled"],
        )

        shared.DEVICE_METADATA_CACHE[device_id] = metadata
        shared.CUSTOM_CB_DEVICES[device_id] = metadata

        if device_id in shared.latest_data:
            shared.latest_data[device_id]["metadata"] = metadata
        else:
            shared.latest_data[device_id] = {
                "telemetry": {},
                "attributes": {"POWER": "N/A"},
                "metadata": metadata,
            }

        logging.info("Updated CB: %s (ID: %s) to location %s", name, device_id, location)

        socketio.emit(
            "device_updated",
            {"device_id": device_id, "metadata": metadata, "timestamp": datetime.now().isoformat()},
            room=f"user_{user['id']}_dashboard",
        )

        return jsonify(
            {
                "status": "success",
                "message": f"CB '{name}' updated successfully",
                "device": {
                    "id": device_id,
                    "name": name,
                    "type": "cb",
                    "location": location,
                    "roomType": room_type,
                    "roomName": room_name,
                    "floor": floor,
                    "maxLoad": max_load,
                    "overcurrentThreshold": metadata["overcurrent_threshold"],
                    "overcurrentEnabled": metadata["overcurrent_enabled"],
                },
            }
        )

    @app.route("/api/devices/cb/<string:device_id>", methods=["DELETE"])
    def delete_circuit_breaker(device_id):
        user, err = _get_current_user()
        if err:
            return err

        if device_id not in shared.CUSTOM_CB_DEVICES or shared.CUSTOM_CB_DEVICES[device_id].get("user_id") != user["id"]:
            return jsonify({"status": "error", "message": "CB not found or no permission"}), 404

        cb_name = shared.CUSTOM_CB_DEVICES[device_id].get("name", device_id)
        if device_id in shared.DEVICE_METADATA_CACHE:
            del shared.DEVICE_METADATA_CACHE[device_id]
        if device_id in shared.CUSTOM_CB_DEVICES:
            del shared.CUSTOM_CB_DEVICES[device_id]
        if device_id in shared.latest_data:
            del shared.latest_data[device_id]

        delete_device(device_id)

        logging.info("Deleted CB: %s (ID: %s)", cb_name, device_id)

        socketio.emit(
            "device_removed",
            {"device_id": device_id, "timestamp": datetime.now().isoformat()},
            room=f"user_{user['id']}_dashboard",
        )

        return jsonify({"status": "success", "message": f"CB '{cb_name}' deleted successfully"})

    @app.route("/api/devices/cb", methods=["GET"])
    def list_circuit_breakers():
        user, err = _get_current_user()
        if err:
            return err

        cb_list = []
        for device_id, meta in shared.CUSTOM_CB_DEVICES.items():
            if meta.get("user_id") != user["id"]:
                continue
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
                    "overcurrentThreshold": meta.get("overcurrent_threshold", 20.0),
                    "overcurrentEnabled": meta.get("overcurrent_enabled", False),
                    "attributes": device_info.get("attributes", {}),
                    "telemetry": device_info.get("telemetry", {}),
                }
            )

        return jsonify({"status": "success", "data": cb_list, "count": len(cb_list)})

    @app.route("/api/device/<string:device_id>", methods=["GET"])
    def get_device_detail(device_id):
        user, err = _get_current_user()
        if err:
            return err

        if device_id in shared.CUSTOM_CB_DEVICES and shared.CUSTOM_CB_DEVICES[device_id].get("user_id") != user["id"]:
            return jsonify({"status": "error", "message": "No permission"}), 403

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

    @app.route("/api/device/<string:device_id>/history", methods=["GET"])
    def get_device_history(device_id):
        user, err = _get_current_user()
        if err:
            return err

        if device_id in shared.CUSTOM_CB_DEVICES and shared.CUSTOM_CB_DEVICES[device_id].get("user_id") != user["id"]:
            return jsonify({"status": "error", "message": "No permission"}), 403

        period = request.args.get("period", "day").lower()
        full_mode = period == "all"
        logging.info("Device history request for: %s, period: %s", device_id, period)

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
                start_ts_param = request.args.get("startTs")

                if start_ts_param is None and cursor_param is None:
                    one_year_ago = now - timedelta(days=365)
                    start_ts = int(one_year_ago.timestamp() * 1000)
                    logging.info("No startTs/cursor provided for 'all' mode, using 1 year ago: %s", start_ts)
                else:
                    try:
                        start_ts = int(cursor_param) if cursor_param is not None else int(start_ts_param or 0)
                    except ValueError:
                        return jsonify({"status": "error", "message": "cursor/startTs must be an integer timestamp in ms"}), 400

                full_history = []
                cursor = start_ts
                seen_ts_ms = set()
                next_cursor = None
                has_more = False
                reached_page_limit = False

                adaptive_chunk_ms = chunk_ms
                min_chunk_ms = 60 * 60 * 1000  # 1 hour

                while cursor <= end_ts:
                    chunk_end = min(cursor + adaptive_chunk_ms - 1, end_ts)
                    logging.debug(
                        "Full history fetch chunk for %s: cursor=%s, chunk_end=%s, chunk_size_ms=%s",
                        device_id, cursor, chunk_end, adaptive_chunk_ms,
                    )
                    try:
                        raw_chunk = _fetch_timeseries(
                            device_id,
                            start_ts=cursor,
                            end_ts=chunk_end,
                            limit=20000,
                            agg="NONE",
                            interval=0,
                            timeout=35,
                        )
                    except requests.RequestException as fetch_err:
                        logging.warning(
                            "Full history fetch failed for %s in [%s,%s]: %s",
                            device_id, cursor, chunk_end, fetch_err,
                        )
                        if adaptive_chunk_ms <= min_chunk_ms:
                            raise fetch_err
                        adaptive_chunk_ms = max(min_chunk_ms, adaptive_chunk_ms // 2)
                        logging.warning("Reducing chunk size to %sms and retrying", adaptive_chunk_ms)
                        continue

                    chunk_history = _build_history(raw_chunk, include_ts_ms=True)
                    logging.debug("Received %d points from chunk [%s,%s]", len(chunk_history), cursor, chunk_end)

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
                            logging.info(
                                "Reached page limit for %s: %d points collected, nextCursor=%s",
                                device_id, len(full_history), next_cursor,
                            )
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
                    device_id, len(full_history), chunk_days, has_more,
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
                limit = 5000
                agg = "NONE"
                interval = 0
            elif period == "month":
                start_time = now - timedelta(days=30)
                limit = 10000
                agg = "NONE"
                interval = 0
            else:  # day
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                limit = 96
                agg = "NONE"
                interval = 0

            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)

            logging.info(
                "Fetching %s history for device %s: start_ts=%s, end_ts=%s, limit=%s",
                period, device_id, start_ts, end_ts, limit,
            )

            try:
                raw_data = _fetch_timeseries(device_id, start_ts=start_ts, end_ts=end_ts, limit=limit * 4, agg=agg, interval=interval)
            except Exception as e:
                logging.warning("Failed to fetch from CoreIoT with agg/interval for %s: %s", device_id, e)
                try:
                    raw_data = _fetch_timeseries(device_id, start_ts=start_ts, end_ts=end_ts, limit=10000, agg="NONE", interval=0)
                except Exception as fallback_err:
                    logging.error("Fallback fetch also failed for %s: %s", device_id, fallback_err)
                    raise fallback_err

            history = _build_history(raw_data)
            if period == "day":
                energy_by_bucket = _derive_energy_from_total(history, period)
            else:
                energy_profile_by_ts = _derive_energy_profile_from_total(history)

            logging.info("Fetched %d history points for device %s, period %s", len(history), device_id, period)

            if period == "day":
                day_start = start_time
                current_hour = now.hour
                filled_history = {}

                for hour_offset in range(current_hour + 1):
                    hour_time = day_start + timedelta(hours=hour_offset)
                    hour_key = hour_time.replace(minute=0, second=0, microsecond=0).isoformat()
                    filled_history[hour_key] = {
                        "timestamp": hour_key,
                        "power": 0.0,
                        "voltage": 0.0,
                        "current": 0.0,
                        "energy": 0.0,
                    }

                for point in history:
                    ts = datetime.fromisoformat(point["timestamp"])
                    hour_key = ts.replace(minute=0, second=0, microsecond=0).isoformat()
                    if hour_key in filled_history:
                        point["timestamp"] = hour_key
                        filled_history[hour_key] = point

                history = sorted(filled_history.values(), key=lambda x: x["timestamp"])
                logging.info(
                    "Filled day view for hours 00-%d (current hour): %d points, now=%s",
                    current_hour, len(history), now.isoformat(),
                )

            if period in ("week", "month") and energy_profile_by_ts:
                logging.debug("Energy profile by timestamp for period %s has %d points", period, len(energy_profile_by_ts))
                for point in history:
                    point["energy"] = float(energy_profile_by_ts.get(point["timestamp"], 0.0))
                logging.debug("Updated history points with daily cumulative energy profile (period=%s)", period)
            elif energy_by_bucket:
                logging.debug("Energy by bucket for period %s: %s", period, energy_by_bucket)
                for point in history:
                    ts_point = datetime.fromisoformat(point["timestamp"])
                    if period == "day":
                        bucket_key = ts_point.replace(minute=0, second=0, microsecond=0).isoformat()
                    else:
                        bucket_key = ts_point.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                    point["energy"] = float(energy_by_bucket.get(bucket_key, 0.0))
                logging.debug("Updated history points with energy from buckets (period=%s)", period)
            else:
                interval_hours = 1.0 if period == "day" else 24.0
                logging.warning("No energy_by_bucket data, falling back to power-based calculation (period=%s)", period)
                for point in history:
                    power_w = float(point.get("power") or 0.0)
                    point["energy"] = round(max(0.0, power_w) * interval_hours / 1000.0, 6)

            for point in history:
                point.pop("energy_total", None)

            total_energy = sum(float(p.get("energy", 0.0)) for p in history)
            logging.info(
                "Returning %s history for device %s: %d points, total energy=%.6f kWh",
                period, device_id, len(history), total_energy,
            )
            if period == "day":
                for point in history[-5:]:
                    logging.debug("Last points for day view - %s: energy=%.6f kWh", point.get("timestamp"), point.get("energy", 0.0))

            if len(history) > limit:
                step = max(1, len(history) // limit)
                history = history[::step][:limit]
                logging.info("Downsampled to %d points", len(history))

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

    @app.route("/api/device/<string:device_id>/history/full", methods=["GET"])
    def get_device_history_full(device_id):
        """Alias: reuse /history với period=all."""
        args = request.args.to_dict(flat=True)
        args["period"] = "all"
        with app.test_request_context(query_string=args):
            return get_device_history(device_id)

    logging.info("Device routes registered.")
