import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
import statistics

import requests
from flask import jsonify, request

from app_core import shared
from app_core.analysis_routes import register_analysis_routes


def calculate_vietnam_electricity_bill(total_kwh):
    """Vietnam household electricity tiered pricing + 8% VAT"""
    tiers = [
        (100, 1984),   # Bậc 1: 0-50kWh → 1,984đ
        (100, 2050),   # Bậc 2: 50-100 → 2,050đ  
        (200, 2380),   # Bậc 3: 100-200 → 2,380đ
        (200, 2998),   # Bậc 4: 200-400 → 2,998đ
        (200, 3350),   # Bậc 5: 400-600 → 3,350đ
        (float('inf'), 3460)  # Bậc 6: >600 → 3,460đ
    ]
    
    bill = 0
    kwh_remaining = total_kwh
    
    for tier_limit, price in tiers:
        if kwh_remaining <= 0:
            break
        kwh_in_tier = min(kwh_remaining, tier_limit)
        bill += kwh_in_tier * price
        kwh_remaining -= kwh_in_tier
    
    return round(bill * 1.08, 0)  # VAT 8%, round to VND


def register_routes(app, socketio):
    register_analysis_routes(app)

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
            endpoints["/forecast/by-plug"] = "Forecast for each plug individually + push to CoreIoT"
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
            device_ids = shared.get_devices_from_group()

            available_devices = []
            for device_id in device_ids:
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
                    # Keep placeholder metadata; ID is still valid and group-scoped.
                    pass

                is_configured = device_id in shared.CUSTOM_CB_DEVICES
                available_devices.append(
                    {
                        "id": device_id,
                        "name": name,
                        "type": dev_type,
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

    @app.route("/devices/cb/<string:device_id>", methods=["PUT"])
    def update_circuit_breaker(device_id):
        if device_id not in shared.CUSTOM_CB_DEVICES:
            return jsonify(
                {
                    "status": "error",
                    "message": "CB not found or cannot be updated (not a custom CB)",
                }
            ), 404

        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        # Get current metadata
        current_meta = shared.CUSTOM_CB_DEVICES[device_id]
        
        # Update fields if provided
        name = data.get("name", current_meta.get("name"))
        room_type = data.get("roomType", current_meta.get("room_type", "custom"))
        room_name = data.get("roomName", current_meta.get("room_name", ""))
        floor = data.get("floor", current_meta.get("floor"))
        max_load = data.get("maxLoad", current_meta.get("max_load", 32))

        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        # Determine location
        if room_name:
            location = room_name
        elif room_type in shared.ROOM_TYPE_MAP:
            location = shared.ROOM_TYPE_MAP[room_type]
        else:
            location = name

        # Update metadata
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
            room="dashboard",
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
            """Derive per-bucket kWh from ENERGY-Total deltas with reset-safe handling.
            
            Handles:
            - Counter reset (negative delta)
            - Time gaps (>30min = new period, delta=0)  
            - Duplicate register values (tiny delta over large gap = skip)
            - Cross-day boundary (new day = reset)
            - Repeated same delta value in same day (register stuck = skip repeats)
            """
            parsed = []
            for point in history_points:
                try:
                    ts = datetime.fromisoformat(point["timestamp"])
                    total = float(point.get("energy_total") or 0.0)
                    parsed.append((ts, max(0.0, total)))
                except (TypeError, ValueError):
                    continue

            if len(parsed) < 2:
                logging.debug("_derive_energy_from_total: Not enough points (%d) for period %s", len(parsed), bucket_period)
                return {}

            parsed.sort(key=lambda x: x[0])
            logging.debug("_derive_energy_from_total: Processing %d points for period %s", len(parsed), bucket_period)
            logging.debug("First point: ts=%s, total=%.6f", parsed[0][0].isoformat(), parsed[0][1])
            logging.debug("Last point: ts=%s, total=%.6f", parsed[-1][0].isoformat(), parsed[-1][1])
            
            by_bucket = defaultdict(float)
            seen_deltas_by_day = defaultdict(dict)  # Track deltas per day to detect repetition
            
            prev_total = parsed[0][1]
            prev_ts = parsed[0][0]

            for idx, (ts, total) in enumerate(parsed[1:], 1):
                # Calculate time gap in seconds
                time_gap_sec = (ts - prev_ts).total_seconds()
                time_gap_min = time_gap_sec / 60
                day_key = ts.date().isoformat()
                
                delta = total - prev_total
                
                # Handle different scenarios
                if delta < 0:
                    # Counter reset/reboot
                    logging.debug("Point %d: Counter reset detected (%.6f → %.6f), delta=%.6f → 0", idx, prev_total, total, delta)
                    delta = 0.0
                elif time_gap_min > 30:  # Gap > 30 minutes
                    if delta < 0.05:  # Delta too small for such large gap = likely duplicate
                        logging.debug("Point %d: Duplicate value detected (gap=%.0fmin, delta=%.6f), skipping", idx, time_gap_min, delta)
                        delta = 0.0
                    else:
                        logging.debug("Point %d: Gap %.0f min detected with delta %.6f", idx, time_gap_min, delta)
                elif ts.date() > prev_ts.date():  # Crossed day boundary
                    logging.debug("Point %d: Day boundary crossed (%s → %s), delta stays %.6f", idx, prev_ts.date(), ts.date(), delta)
                    seen_deltas_by_day[day_key] = {}  # Reset for new day
                else:
                    # Same day: check if this very small delta is repeated (register stuck at same value)
                    delta_rounded = round(delta, 4)
                    if 0 < delta_rounded <= 0.01 and delta_rounded in seen_deltas_by_day[day_key]:
                        # Same tiny delta (<=0.01) appearing again in same day = likely register didn't budge
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
                
                logging.debug("Point %d: ts=%s, gap=%.0fm, delta=%.6f → bucket=%s", idx, ts.isoformat(), time_gap_min, delta, bucket.isoformat())
                by_bucket[bucket.isoformat()] += delta

            result = {k: round(v, 6) for k, v in by_bucket.items() if v > 0}
            logging.debug("_derive_energy_from_total result for %s: %s", bucket_period, result)
            return result

        def _derive_energy_profile_from_total(history_points) -> dict[str, float]:
            """Build per-point daily cumulative energy profile from ENERGY-Total.

            For each day:
            - baseline starts at first ENERGY-Total point of that day
            - energy = max(total - baseline, 0)
            - if counter resets (total < previous total), reset baseline at that point
            """
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

        def _fetch_timeseries(start_ts, end_ts, limit, agg, interval, timeout=20):
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

        def _fetch_energy_deltas_by_bucket(start_ts: int, end_ts: int, bucket_period: str) -> dict[str, float]:
            """Build energy (kWh) by hour/day from ENERGY-Total deltas with reset-safe logic.
            
            Handles:
            - Counter reset (negative delta)
            - Time gaps (no data for >30min → new period, delta=0)
            - Duplicate register values (tiny delta over large gap → skip)
            - Cross-day boundary (new day → reset accumulation)
            - Repeated same value in same day (register stuck)
            """
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
            logging.debug("_fetch_energy_deltas_by_bucket: Fetched %d raw entries for period %s", len(entries), bucket_period)
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
            logging.debug("First entry (period %s): ts=%d (%.0f), total=%.6f", bucket_period, parsed[0][0], parsed[0][0]/1000, parsed[0][1])
            logging.debug("Last entry (period %s): ts=%d (%.0f), total=%.6f", bucket_period, parsed[-1][0], parsed[-1][0]/1000, parsed[-1][1])
            
            by_bucket = defaultdict(float)
            seen_deltas_by_day = defaultdict(dict)  # Track deltas per day to detect repetition

            prev_total = parsed[0][1]
            prev_ts_ms = parsed[0][0]
            
            for idx, (ts_ms, total_kwh) in enumerate(parsed[1:], 1):
                dt = datetime.fromtimestamp(ts_ms / 1000)
                prev_dt = datetime.fromtimestamp(prev_ts_ms / 1000)
                day_key = dt.date().isoformat()
                
                # Calculate time gap in seconds
                time_gap_sec = (ts_ms - prev_ts_ms) / 1000
                time_gap_min = time_gap_sec / 60
                
                delta = total_kwh - prev_total
                
                # Handle different scenarios
                if delta < 0:
                    # Counter reset/reboot
                    logging.debug("Entry %d: Counter reset (%.6f → %.6f), setting delta=0", idx, prev_total, total_kwh)
                    delta = 0.0
                elif time_gap_min > 30:  # Gap > 30 minutes
                    if delta < 0.05:  # Delta too small for such large gap = likely duplicate register value
                        logging.debug("Entry %d: Duplicate value detected (gap=%.0fmin, delta=%.6f), skipping", idx, time_gap_min, delta)
                        delta = 0.0  # Skip this entry
                    else:
                        # Real consumption, but likely device was off
                        logging.debug("Entry %d: Gap %.0f min detected with delta %.6f, treating as new period", idx, time_gap_min, delta)
                elif dt.date() > prev_dt.date():  # Crossed day boundary
                    # Don't accumulate delta across days
                    logging.debug("Entry %d: Day boundary crossed (%s → %s), delta stays %.6f", idx, prev_dt.date(), dt.date(), delta)
                    seen_deltas_by_day[day_key] = {}  # Reset for new day
                else:
                    # Same day: check if this very small delta is repeated (register stuck at same value)
                    delta_rounded = round(delta, 4)
                    if 0 < delta_rounded <= 0.01 and delta_rounded in seen_deltas_by_day[day_key]:
                        # Same tiny delta (<=0.01) appearing again in same day = likely register didn't budge
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
                    
                logging.debug("Entry %d: ts=%s, gap=%.0fm, delta=%.6f → bucket=%s", idx, dt.isoformat(), time_gap_min, delta, bucket.isoformat())
                by_bucket[bucket.isoformat()] += delta

            result = {k: round(v, 6) for k, v in by_bucket.items() if v > 0}
            logging.debug("_fetch_energy_deltas_by_bucket result for %s: %s", bucket_period, result)
            return result

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
                
                # If no startTs provided, start from 1 year ago (or some reasonable past date)
                if start_ts_param is None and cursor_param is None:
                    # Default to 1 year ago if no starting point given
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

                # Start with user-selected chunk size and automatically shrink on upstream failures.
                adaptive_chunk_ms = chunk_ms
                min_chunk_ms = 60 * 60 * 1000  # 1 hour

                while cursor <= end_ts:
                    chunk_end = min(cursor + adaptive_chunk_ms - 1, end_ts)
                    logging.debug(
                        "Full history fetch chunk for %s: cursor=%s, chunk_end=%s, chunk_size_ms=%s",
                        device_id, cursor, chunk_end, adaptive_chunk_ms
                    )
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
                        logging.warning(
                            "Full history fetch failed for %s in [%s,%s]: %s",
                            device_id, cursor, chunk_end, fetch_err
                        )
                        if adaptive_chunk_ms <= min_chunk_ms:
                            raise fetch_err

                        adaptive_chunk_ms = max(min_chunk_ms, adaptive_chunk_ms // 2)
                        logging.warning(
                            "Reducing chunk size to %sms and retrying",
                            adaptive_chunk_ms,
                        )
                        continue

                    chunk_history = _build_history(raw_chunk, include_ts_ms=True)
                    logging.debug(
                        "Received %d points from chunk [%s,%s]", len(chunk_history), cursor, chunk_end
                    )

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
                                device_id, len(full_history), next_cursor
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
                limit = 5000  # keep enough points for intra-day shape
                agg = "NONE"
                interval = 0
            elif period == "month":
                start_time = now - timedelta(days=30)
                limit = 10000  # keep enough points for intra-day shape
                agg = "NONE"
                interval = 0
            else:  # period == "day"
                # For day view: fetch from 00:00 today to now (not "24h ago")
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                limit = 96  # Request 96 to handle gaps, will downample to 24
                agg = "NONE"
                interval = 0

            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)
            
            logging.info(
                "Fetching %s history for device %s: start_ts=%s, end_ts=%s, limit=%s",
                period, device_id, start_ts, end_ts, limit
            )
            
            try:
                raw_data = _fetch_timeseries(
                    start_ts=start_ts,
                    end_ts=end_ts,
                    limit=limit * 4,  # Request extra to handle gaps
                    agg=agg,
                    interval=interval,
                )
            except Exception as e:
                logging.warning("Failed to fetch from CoreIoT with agg/interval for %s: %s", device_id, e)
                # Fallback: try without aggregation
                try:
                    raw_data = _fetch_timeseries(
                        start_ts=start_ts,
                        end_ts=end_ts,
                        limit=10000,
                        agg="NONE",
                        interval=0,
                    )
                except Exception as fallback_err:
                    logging.error("Fallback fetch also failed for %s: %s", device_id, fallback_err)
                    raise fallback_err
            
            history = _build_history(raw_data)
            if period == "day":
                energy_by_bucket = _derive_energy_from_total(history, period)
            else:
                energy_profile_by_ts = _derive_energy_profile_from_total(history)
            
            # Log for debugging
            logging.info("Fetched %d history points for device %s, period %s", len(history), device_id, period)
            
            # For day view, fill missing hours from start of day to current hour (inclusive)
            if period == "day":
                # Create hourly slots from 00:00 today to current hour
                day_start = start_time
                current_hour = now.hour
                filled_history = {}
                
                # Initialize hours from 00:00 to current hour (inclusive)
                # This ensures biểu đồ kéo dài khi có dữ liệu mới ở giờ tiếp theo
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
                
                # Fill in actual data
                for point in history:
                    ts = datetime.fromisoformat(point["timestamp"])
                    hour_key = ts.replace(minute=0, second=0, microsecond=0).isoformat()
                    if hour_key in filled_history:
                        # Ensure timestamp is hour-rounded, not raw
                        point["timestamp"] = hour_key
                        filled_history[hour_key] = point
                
                # Convert back to list, sorted by time
                history = sorted(filled_history.values(), key=lambda x: x["timestamp"])
                logging.info(
                    "Filled day view for hours 00-%d (current hour): %d points, now=%s",
                    current_hour, len(history), now.isoformat()
                )

            # Recompute energy from ENERGY-Total deltas to avoid reset-related drift and duplicated daily values.
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
                # Fallback: derive interval energy from power to avoid stale ENERGY-Today values.
                interval_hours = 1.0 if period == "day" else 24.0
                logging.warning("No energy_by_bucket data, falling back to power-based calculation (period=%s)", period)
                for point in history:
                    power_w = float(point.get("power") or 0.0)
                    point["energy"] = round(max(0.0, power_w) * interval_hours / 1000.0, 6)

            # Strip internal field before returning payload.
            for point in history:
                point.pop("energy_total", None)
            
            # Log final history for debugging
            total_energy = sum(float(p.get("energy", 0.0)) for p in history)
            logging.info(
                "Returning %s history for device %s: %d points, total energy=%.6f kWh",
                period, device_id, len(history), total_energy
            )
            if period == "day":
                for point in history[-5:]:  # Log last 5 points for day view
                    logging.debug("Last points for day view - %s: energy=%.6f kWh", point.get("timestamp"), point.get("energy", 0.0))
            
            # Downsample if needed (keep only up to limit points)
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

    @app.route("/schedules/auto-scenarios", methods=["POST"])
    def generate_auto_scenarios():
        """Generate data-driven on/off schedules from historical hourly energy usage."""
        try:
            payload = request.get_json(silent=True) or {}
            lookback_days = int(payload.get("lookbackDays", 14) or 14)
            max_devices = int(payload.get("maxDevices", 8) or 8)
            min_samples = int(payload.get("minSamples", 12) or 12)
            auto_apply = bool(payload.get("autoApply", True))
            buffer_hours = int(payload.get("bufferHours", 2) or 2)
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
                """Read hourly history + latest power point directly from CoreIoT."""
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                params = {
                    "keys": "ENERGY-Power",
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "limit": min(10000, lookback_days * 24 + 48),
                    "agg": "AVG",
                    "interval": 3600000,
                }

                history_points: dict[str, dict] = {}
                history_resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=25)
                history_resp.raise_for_status()
                history_payload = history_resp.json()

                for entry in history_payload.get("ENERGY-Power", []):
                    ts = entry.get("ts")
                    if ts is None:
                        continue
                    try:
                        power_w = float(entry.get("value") or 0.0)
                    except (TypeError, ValueError):
                        continue

                    hour_dt = datetime.fromtimestamp(ts / 1000).replace(minute=0, second=0, microsecond=0)
                    hour_key = hour_dt.strftime("%Y-%m-%dT%H:00:00")
                    history_points[hour_key] = {
                        "hour": hour_dt,
                        "energy_kwh": max(0.0, power_w) / 1000.0,
                    }

                latest_params = {"keys": "ENERGY-Power", "limit": 1, "orderBy": "DESC"}
                latest_resp = requests.get(url, headers=shared.HEADERS, params=latest_params, timeout=15)
                latest_resp.raise_for_status()
                latest_payload = latest_resp.json()
                latest_entries = latest_payload.get("ENERGY-Power", [])
                if latest_entries:
                    latest_entry = latest_entries[0]
                    try:
                        latest_ts = int(latest_entry.get("ts"))
                        latest_power_w = float(latest_entry.get("value") or 0.0)
                        latest_dt = datetime.fromtimestamp(latest_ts / 1000).replace(minute=0, second=0, microsecond=0)
                        latest_key = latest_dt.strftime("%Y-%m-%dT%H:00:00")
                        history_points[latest_key] = {
                            "hour": latest_dt,
                            "energy_kwh": max(0.0, latest_power_w) / 1000.0,
                        }
                    except (TypeError, ValueError):
                        pass

                return list(history_points.values())

            tracked_device_ids = shared.get_tracked_device_ids() or shared.get_devices_from_group()
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

                # Select active hours by usage intensity and derive the main continuous window.
                max_hour_energy = max(hourly_energy.values())
                threshold = max_hour_energy * 0.4
                active_hours = sorted([h for h, e in hourly_energy.items() if e >= threshold])
                if not active_hours:
                    continue

                segments = []
                current_segment = [active_hours[0]]
                for h in active_hours[1:]:
                    if h == current_segment[-1] + 1:
                        current_segment.append(h)
                    else:
                        segments.append(current_segment)
                        current_segment = [h]
                segments.append(current_segment)

                best_segment = max(
                    segments,
                    key=lambda seg: sum(hourly_energy.get(hour, 0.0) for hour in seg),
                )
                on_hour = (best_segment[0] - buffer_hours) % 24
                off_hour = (best_segment[-1] + 1 + buffer_hours) % 24

                on_time = f"{on_hour:02d}:00"
                off_time = f"{off_hour:02d}:00"

                weekday_counts = list(weekday_hits.values())
                median_hits = statistics.median(weekday_counts) if weekday_counts else 0
                days = [d for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] if weekday_hits[d] >= median_hits and weekday_hits[d] > 0]
                if not days:
                    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

                metadata = (
                    shared.CUSTOM_CB_DEVICES.get(device_id)
                    or shared.DEVICE_METADATA_CACHE.get(device_id)
                    or shared.latest_data.get(device_id, {}).get("metadata")
                    or {}
                )
                device_name = metadata.get("name") or f"Device {device_id[-6:]}"

                on_name = f"Auto ON {device_name}"
                off_name = f"Auto OFF {device_name}"

                suggestion = {
                    "deviceId": device_id,
                    "deviceName": device_name,
                    "days": days,
                    "onSchedule": {
                        "name": on_name,
                        "targetId": device_id,
                        "action": "on",
                        "time": on_time,
                        "days": days,
                        "enabled": True,
                    },
                    "offSchedule": {
                        "name": off_name,
                        "targetId": device_id,
                        "action": "off",
                        "time": off_time,
                        "days": days,
                        "enabled": True,
                    },
                    "analysis": {
                        "samples": len(device_points),
                        "activeHours": active_hours,
                        "peakWindow": [best_segment[0], best_segment[-1]],
                        "bufferHours": buffer_hours,
                        "extendedWindow": [on_hour, (off_hour - 1) % 24],
                        "dataSource": "coreiot_direct",
                        "totalKwhInWindow": round(
                            sum(hourly_energy.get(hour, 0.0) for hour in best_segment),
                            4,
                        ),
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

                    for schedule_payload in (suggestion["onSchedule"], suggestion["offSchedule"]):
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
                        )
                        created_schedules.append(created)
                        existing_keys.add(dedupe_key)

            if auto_apply and created_schedules:
                for schedule in created_schedules:
                    socketio.emit("schedule_created", schedule, room="schedules")

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

    if shared.FORECAST_ENABLED:
        FORECAST_RESULT_PATH = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "forecast_result.json",
        )

        def _push_ml_analysis_to_coreiot(device_id: str, forecast_payload: dict):
            """Push ML analysis telemetry and prediction attributes to CoreIoT for one device."""
            now_ms = int(time.time() * 1000)
            predicted_bill_vnd = round(float(forecast_payload.get("PredictedBillVND", 0) or 0), 2)
            predicted_kwh = round(float(forecast_payload.get("TotalKwhForecasted", 0) or 0), 6)
            values = {
                "ml_predicted_bill_vnd": predicted_bill_vnd,
                "ml_total_kwh_forecasted": predicted_kwh,
                "ml_total_kwh_month": round(float(forecast_payload.get("TotalKwhMonth", 0) or 0), 6),
                "ml_consumed_this_month_kwh": round(float(forecast_payload.get("ConsumedThisMonthKwh", 0) or 0), 6),
                # New telemetry keys requested for per-plug prediction sync.
                "forecast_price_vnd": predicted_bill_vnd,
                "forecast_kwh_predicted": predicted_kwh,
            }
            telemetry_payload = {"ts": now_ms, "values": values}
            attribute_payload = {
                "forecast_price_vnd": predicted_bill_vnd,
                "forecast_kwh_predicted": predicted_kwh,
            }

            candidate_urls = [
                f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/timeseries/ANY?scope=ANY",
                f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/timeseries/SERVER_SCOPE",
                f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/timeseries/CLIENT_SCOPE",
            ]

            errors = []
            for url in candidate_urls:
                try:
                    resp = requests.post(url, headers=shared.HEADERS, json=telemetry_payload, timeout=20)
                    if 200 <= resp.status_code < 300:
                        attribute_status = {"pushed": False}
                        attribute_url = (
                            f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/attributes/SERVER_SCOPE"
                        )
                        try:
                            attr_resp = requests.post(
                                attribute_url,
                                headers=shared.HEADERS,
                                json=attribute_payload,
                                timeout=20,
                            )
                            attribute_status = {
                                "pushed": 200 <= attr_resp.status_code < 300,
                                "url": attribute_url,
                                "statusCode": attr_resp.status_code,
                                "response": (attr_resp.text or "")[:300],
                            }
                        except Exception as attr_err:
                            attribute_status = {
                                "pushed": False,
                                "url": attribute_url,
                                "error": str(attr_err),
                            }

                        return True, {
                            "deviceId": device_id,
                            "url": url,
                            "statusCode": resp.status_code,
                            "values": values,
                            "attributes": attribute_status,
                        }

                    errors.append(
                        {
                            "url": url,
                            "statusCode": resp.status_code,
                            "response": (resp.text or "")[:300],
                        }
                    )
                except Exception as e:
                    errors.append({"url": url, "error": str(e)})

            return False, {
                "deviceId": device_id,
                "message": "Unable to push ML telemetry to CoreIoT",
                "attempts": errors,
                "payload": telemetry_payload,
            }

        def _month_consumption_from_energy_summary_source(timeout_sec: float = 20.0) -> float:
            """Compute month kWh using the same source/logic as Energy page month summary card."""
            now = datetime.now()
            current_month = now.strftime("%Y-%m")

            if hasattr(shared, "monthly_boundaries") and current_month in shared.monthly_boundaries:
                snapshot = shared.monthly_boundaries[current_month]
                if snapshot.get("closed"):
                    return round(max(0.0, float(snapshot.get("consumed_kwh") or 0.0)), 6)

                total_from_cache = sum(
                    v for k, v in shared.hourly_kwh_global.items() if k.startswith(current_month)
                )
                return round(max(0.0, total_from_cache), 6)

            # Fallback path is also identical to /energy/summary: month ENERGY-Power hourly aggregation.
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_month.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)
            device_ids = shared.get_tracked_device_ids()
            if not device_ids:
                device_ids = shared.get_devices_from_group()

            total_kwh = 0.0
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
                    resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=timeout_sec)
                    resp.raise_for_status()
                    raw = resp.json()

                    for entry in raw.get("ENERGY-Power", []):
                        try:
                            power_w = float(entry.get("value") or 0.0)
                            total_kwh += max(0.0, power_w) / 1000.0
                        except (TypeError, ValueError):
                            continue
                except Exception as e:
                    logging.warning("Month consumption source skipped device %s due to error: %s", device_id, e)

            return round(max(0.0, total_kwh), 6)

        @app.route("/forecast", methods=["GET"])
        def trigger_forecast():
            logging.info("--- MANUAL FORECAST TRIGGERED ---")
            try:
                forecast_coreiot_timeout = float(os.getenv("FORECAST_COREIOT_TIMEOUT_SEC", "6"))
            except ValueError:
                forecast_coreiot_timeout = 6.0

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
                        resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=forecast_coreiot_timeout)
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
                        resp = requests.get(url, headers=shared.HEADERS, timeout=forecast_coreiot_timeout)
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
                    # Keep this identical to /energy/summary month consumption source.
                    consumed = _month_consumption_from_energy_summary_source(forecast_coreiot_timeout)
                    if consumed <= 0:
                        consumed = sum(coreiot_history.values())
                    recent_history = dict(sorted(coreiot_history.items(), key=lambda x: x[0], reverse=True)[:1200])
                else:
                    consumed = _month_consumption_from_energy_summary_source(forecast_coreiot_timeout)
                    if consumed <= 0:
                        consumed = _coreiot_latest_total_kwh()
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
                    with open(FORECAST_RESULT_PATH, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    logging.error("Failed to write forecast result file %s: %s", FORECAST_RESULT_PATH, e)

                return jsonify(result)

            return jsonify({"status": "error", "message": "AI Server not responding"}), 500

        @app.route("/forecast/push-coreiot", methods=["POST"])
        def push_forecast_to_coreiot():
            """Push latest forecast analysis data to CoreIoT as telemetry."""
            data = request.json or {}
            device_id = data.get("deviceId") or shared.ML_ANALYSIS_DEVICE_ID

            if not device_id:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Missing target deviceId. Set ML_ANALYSIS_DEVICE_ID in .env or pass deviceId in body.",
                        }
                    ),
                    400,
                )

            forecast_payload = data.get("forecast")
            if not forecast_payload:
                try:
                    with open(FORECAST_RESULT_PATH, "r", encoding="utf-8") as f:
                        forecast_payload = json.load(f)
                except FileNotFoundError:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "No forecast payload in request and forecast_result.json not found. Call /forecast first or send forecast in request body.",
                            }
                        ),
                        400,
                    )
                except Exception as e:
                    return jsonify({"status": "error", "message": str(e)}), 500

            ok, result = _push_ml_analysis_to_coreiot(device_id, forecast_payload)
            if ok:
                return jsonify({"status": "success", "result": result})
            return jsonify({"status": "error", "result": result}), 502

        @app.route("/forecast/by-plug", methods=["GET"])
        def forecast_by_plug():
            """Forecast energy consumption for each plug individually."""
            logging.info("--- FORECAST BY PLUG TRIGGERED ---")

            now = datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            def _coreiot_hourly_from_energy_total(device_id: str, start_dt: datetime, end_dt: datetime) -> dict:
                """Build hourly kWh series for one device from its ENERGY-Total timeseries."""
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                params = {
                    "keys": "ENERGY-Total",
                    "startTs": int(start_dt.timestamp() * 1000),
                    "endTs": int(end_dt.timestamp() * 1000),
                    "limit": 50000,
                }
                resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
                entries = payload.get("ENERGY-Total", [])
                if not entries:
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
                    return {}

                parsed.sort(key=lambda x: x[0])
                hourly = defaultdict(float)

                prev_total = parsed[0][1]
                for ts_ms, total_kwh in parsed[1:]:
                    dt = datetime.fromtimestamp(ts_ms / 1000)
                    delta = total_kwh - prev_total
                    # Counter reset can make cumulative value drop.
                    if delta < 0:
                        delta = 0.0
                    prev_total = total_kwh

                    if delta <= 0:
                        continue

                    hour_key = dt.replace(
                        minute=0, second=0, microsecond=0
                    ).strftime("%Y-%m-%dT%H:00:00")
                    hourly[hour_key] += delta

                return {k: round(v, 6) for k, v in hourly.items() if v > 0}

            def _coreiot_latest_energy_total(device_id: str) -> float | None:
                """Get the latest real-time ENERGY-Total value for one device from CoreIoT."""
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                params = {
                    "keys": "ENERGY-Total",
                    "limit": 1,
                    "orderBy": "DESC",
                }
                resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
                entries = payload.get("ENERGY-Total", [])
                if not entries:
                    return None

                try:
                    return max(0.0, float(entries[0].get("value") or 0.0))
                except (TypeError, ValueError):
                    return None

            plugs = shared.get_all_plugs_for_forecast()
            if not plugs:
                return jsonify({
                    "status": "empty",
                    "message": "No plugs configured. Please add at least one CB device.",
                    "data": []
                }), 200

            results_by_plug = {}
            total_bill = 0
            total_kwh_forecasted = 0
            total_kwh_month = 0
            push_errors = []

            for plug_info in plugs:
                device_id = plug_info["device_id"]
                plug_name = plug_info["name"]

                try:
                    # Build per-plug history strictly from this device's ENERGY-Total on CoreIoT.
                    history_dict = _coreiot_hourly_from_energy_total(device_id, start_of_month, now)

                    if not history_dict:
                        logging.warning("Forecast for plug %s: ENERGY-Total history unavailable", plug_name)
                        results_by_plug[device_id] = {
                            "plugName": plug_name,
                            "deviceId": device_id,
                            "status": "warning",
                            "message": "No ENERGY-Total history for this plug"
                        }
                        continue

                    history_consumed_this_month = round(sum(history_dict.values()), 6)
                    realtime_total = _coreiot_latest_energy_total(device_id)
                    consumed_this_month = history_consumed_this_month

                    if realtime_total is None:
                        logging.warning(
                            "Realtime ENERGY-Total unavailable for %s (%s), using history consumed=%.3f kWh",
                            plug_name,
                            device_id,
                            consumed_this_month,
                        )
                    else:
                        logging.info(
                            "Realtime ENERGY-Total for %s (%s)=%.3f kWh, history consumed=%.3f kWh (using history to avoid reset drift)",
                            plug_name,
                            device_id,
                            realtime_total,
                            history_consumed_this_month,
                        )

                    logging.info(
                        "Forecasting plug %s (device=%s): Consumed=%.3f kWh from ENERGY-Total delta history",
                        plug_name,
                        device_id,
                        consumed_this_month,
                    )
                    forecast_result = shared.forecast_client.predict(history_dict, consumed_this_month)

                    if not forecast_result:
                        logging.error("Forecast failed for plug %s", plug_name)
                        results_by_plug[device_id] = {
                            "plugName": plug_name,
                            "deviceId": device_id,
                            "status": "error",
                            "message": "ML server failed to forecast"
                        }
                        continue

                    forecast_result["deviceId"] = device_id
                    forecast_result["plugName"] = plug_name
                    forecast_result["ConsumedThisMonthKwh"] = round(consumed_this_month, 2)

                    ok, push_result = _push_ml_analysis_to_coreiot(device_id, forecast_result)
                    if not ok:
                        logging.warning("Failed to push forecast for plug %s to CoreIoT: %s", plug_name, push_result)
                        push_errors.append({
                            "deviceId": device_id,
                            "plugName": plug_name,
                            "error": push_result.get("message", "Unknown error")
                        })
                    else:
                        logging.info(
                            "Forecast pushed to CoreIoT for plug %s: Bill=%d VND, PredKwh=%.3f",
                            plug_name,
                            forecast_result.get("PredictedBillVND", 0),
                            float(forecast_result.get("TotalKwhForecasted", 0) or 0),
                        )

                    total_bill += forecast_result.get("PredictedBillVND", 0)
                    total_kwh_forecasted += forecast_result.get("TotalKwhForecasted", 0)
                    total_kwh_month += forecast_result.get("TotalKwhMonth", 0)

                    results_by_plug[device_id] = {
                        "plugName": plug_name,
                        "deviceId": device_id,
                        "status": "success",
                        "predictedBillVnd": forecast_result.get("PredictedBillVND", 0),
                        "predictedKwh": round(float(forecast_result.get("TotalKwhForecasted", 0) or 0), 3),
                        "totalKwhForecasted": round(forecast_result.get("TotalKwhForecasted", 0), 2),
                        "totalKwhMonth": round(forecast_result.get("TotalKwhMonth", 0), 2),
                        "consumedThisMonthKwh": forecast_result.get("ConsumedThisMonthKwh", 0),
                        "hourlyPredictions": forecast_result.get("HourlyPredictions", []),
                    }

                except Exception as e:
                    logging.error("Error forecasting plug %s: %s", plug_name, e)
                    results_by_plug[device_id] = {
                        "plugName": plug_name,
                        "deviceId": device_id,
                        "status": "error",
                        "message": str(e)
                    }

            response = {
                "status": "success",
                "byPlug": results_by_plug,
                "summary": {
                    "totalPredictedBillVnd": round(total_bill),
                    "totalKwhForecasted": round(total_kwh_forecasted, 2),
                    "totalKwhMonth": round(total_kwh_month, 2),
                },
                "pushErrors": push_errors if push_errors else None,
            }
            
            logging.info("FORECAST BY PLUG COMPLETE -> Total Bill: %d VND", round(total_bill))
            return jsonify(response)

        @app.route("/forecast/summary", methods=["GET"])
        def get_forecast_summary():
            try:
                if os.path.exists(FORECAST_RESULT_PATH):
                    with open(FORECAST_RESULT_PATH, "r", encoding="utf-8") as f:
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
            requested_device_id = (request.args.get("deviceId") or "").strip()
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
            if requested_device_id:
                device_ids = [requested_device_id]
            else:
                device_ids = shared.get_tracked_device_ids()
                if not device_ids:
                    device_ids = shared.get_devices_from_group()

            # Determine aggregation interval based on period
            # Day: hourly, Week/Month: daily
            if period == "day":
                interval_ms = 3600000  # 1 hour
                is_hourly = True
            else:  # week or month
                interval_ms = 86400000  # 1 day
                is_hourly = False

            # Aggregate power data across devices from CoreIoT, then convert to kWh.
            totals_by_interval_ts: dict[int, float] = {}
            for device_id in device_ids:
                try:
                    url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                    params = {
                        "keys": "ENERGY-Power",
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "limit": 10000,
                        "agg": "AVG",
                        "interval": interval_ms,
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
                        # For hourly: group by hour; for daily: group by day
                        if is_hourly:
                            dt_interval = datetime.fromtimestamp(ts / 1000).replace(minute=0, second=0, microsecond=0)
                        else:
                            dt_interval = datetime.fromtimestamp(ts / 1000).replace(hour=0, minute=0, second=0, microsecond=0)
                        interval_ts = int(dt_interval.timestamp() * 1000)
                        # Average power over interval (in watts); for daily interval, CoreIoT returns daily average
                        # Convert: power_w × interval_hours / 1000 = kWh
                        interval_hours = (interval_ms / 3600000)
                        kwh_interval = (power_w * interval_hours) / 1000.0
                        totals_by_interval_ts[interval_ts] = totals_by_interval_ts.get(interval_ts, 0.0) + max(0.0, kwh_interval)
                except Exception as e:
                    logging.warning("Energy aggregation skipped device %s due to error: %s", device_id, e)

            # Calculate total kWh and apply tiered pricing
            total_kwh = sum(totals_by_interval_ts.values())
            total_cost = calculate_vietnam_electricity_bill(total_kwh) if total_kwh > 0 else 0.0
            avg_price_per_kwh = total_cost / total_kwh if total_kwh > 0 else 0.0

            # Generate response with all intervals (fill missing with 0)
            response_data = []
            if totals_by_interval_ts:
                sorted_ts = sorted(totals_by_interval_ts.keys())
                first_ts = sorted_ts[0]
                last_ts = sorted_ts[-1]
                
                # Generate all intervals from first to last
                current_ts = first_ts
                while current_ts <= last_ts:
                    kwh = totals_by_interval_ts.get(current_ts, 0.0)
                    dt_obj = datetime.fromtimestamp(current_ts / 1000)
                    response_data.append(
                        {
                            "timestamp": dt_obj.isoformat(),
                            "consumption": round(max(0.0, kwh), 6),
                            "cost": round(max(0.0, kwh) * avg_price_per_kwh, 2),
                        }
                    )
                    current_ts += interval_ms

            # If upstream telemetry is unavailable, keep backward-compatible fallback.
            if not response_data:
                with shared.lock:
                    sorted_items = sorted(shared.hourly_kwh_global.items(), key=lambda x: x[0])
                    recent_items = sorted_items[-750:]

                    # Calculate total kWh from fallback data
                    total_kwh_fallback = sum((kwh for _, kwh in recent_items if datetime.fromisoformat(_) >= start_time))
                    total_cost_fallback = calculate_vietnam_electricity_bill(total_kwh_fallback) if total_kwh_fallback > 0 else 0.0
                    avg_price_fallback = total_cost_fallback / total_kwh_fallback if total_kwh_fallback > 0 else 0.0

                    # Aggregate by period if needed
                    if period != "day":
                        daily_map: dict[str, float] = {}
                        for iso_ts, kwh in recent_items:
                            try:
                                dt_obj = datetime.fromisoformat(iso_ts)
                                if dt_obj >= start_time:
                                    day_key = dt_obj.strftime("%Y-%m-%d")
                                    daily_map[day_key] = daily_map.get(day_key, 0.0) + kwh
                            except ValueError:
                                continue
                        
                        for day_key in sorted(daily_map.keys()):
                            kwh_daily = daily_map[day_key]
                            response_data.append(
                                {
                                    "timestamp": day_key + "T00:00:00",
                                    "consumption": round(kwh_daily, 6),
                                    "cost": round(kwh_daily * avg_price_fallback, 2),
                                }
                            )
                    else:
                        for iso_ts, kwh in recent_items:
                            try:
                                dt_obj = datetime.fromisoformat(iso_ts)
                                if dt_obj >= start_time:
                                    response_data.append(
                                        {
                                            "timestamp": iso_ts,
                                            "consumption": kwh,
                                            "cost": round(kwh * avg_price_fallback, 2),
                                        }
                                    )
                            except ValueError:
                                continue

            return jsonify(response_data)

        @app.route("/energy/summary", methods=["GET"])
        def get_energy_summary():
            """Return energy summary for Energy page cards.
            For 'day': Calculate from hourly telemetry (ENERGY-Power) like the chart
            For 'month': Use cumulative total (ENERGY-Total)
            """
            period = request.args.get("period", "month")
            requested_device_id = (request.args.get("deviceId") or "").strip()

            if period not in ["day", "month"]:
                return jsonify({"status": "success", "data": {"totalConsumption": 0.0, "totalCost": 0.0}})

            if requested_device_id:
                device_ids = [requested_device_id]
            else:
                device_ids = shared.get_tracked_device_ids()
                if not device_ids:
                    device_ids = shared.get_devices_from_group()

            total_kwh = 0.0

            if period == "day":
                # For 'day': Calculate from hourly power data (ENERGY-Power) to be consistent with chart
                now = datetime.now()
                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_ts = int(start_of_today.timestamp() * 1000)
                end_ts = int(now.timestamp() * 1000)

                for device_id in device_ids:
                    try:
                        url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                        params = {
                            "keys": "ENERGY-Power",
                            "startTs": start_ts,
                            "endTs": end_ts,
                            "limit": 10000,
                            "agg": "AVG",
                            "interval": 3600000,  # hourly
                        }
                        resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                        resp.raise_for_status()
                        raw = resp.json()

                        for entry in raw.get("ENERGY-Power", []):
                            try:
                                power_w = float(entry.get("value") or 0.0)
                                # Convert: power [W] × 1 hour / 1000 = kWh
                                kwh_hour = max(0.0, power_w) / 1000.0
                                total_kwh += kwh_hour
                            except (TypeError, ValueError):
                                continue
                    except Exception as e:
                        logging.warning("Energy summary (day) skipped device %s due to error: %s", device_id, e)

            else:
                # For 'month': single source of truth shared with forecast input.
                total_kwh = _month_consumption_from_energy_summary_source(20.0)

            total_kwh = round(max(0.0, total_kwh), 4)
            total_cost = round(calculate_vietnam_electricity_bill(total_kwh), 2)
            return jsonify({
                "status": "success",
                "data": {
                    "totalConsumption": total_kwh,
                    "totalCost": total_cost,
                },
                "source": "monthly_snapshot" if 'snapshot' in locals() else "power_history"
            })
