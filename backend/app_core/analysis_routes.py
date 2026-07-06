import logging
from datetime import datetime, timedelta

import requests
from flask import jsonify, request

from app_core import shared
from app_core.auth_routes import _get_current_user


def _merge_wrap_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not windows:
        return windows
    windows = sorted(windows, key=lambda item: item[0])
    if len(windows) > 1 and windows[0][0] == 0 and windows[-1][1] == 23:
        merged = [(windows[-1][0], windows[0][1])]
        merged.extend(windows[1:-1])
        return merged
    return windows


def _fetch_hourly_power(device_id: str, start_ts: int, end_ts: int, lookback_days: int) -> list[tuple[datetime, float]]:
    url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {
        "keys": "ENERGY-Power",
        "startTs": start_ts,
        "endTs": end_ts,
        "limit": min(10000, lookback_days * 24 + 100),
        "agg": "AVG",
        "interval": 3600000,
    }
    response = requests.get(url, headers=shared.HEADERS, params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()

    points = []
    for entry in payload.get("ENERGY-Power", []):
        ts = entry.get("ts")
        if ts is None:
            continue
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000).replace(minute=0, second=0, microsecond=0)
            power_w = float(entry.get("value") or 0.0)
        except (TypeError, ValueError):
            continue
        points.append((dt, max(0.0, power_w)))
    return points


def register_analysis_routes(app):
    @app.route("/api/analysis/plug-activity-windows", methods=["GET"])
    def analyze_plug_activity_windows():
        """Analyze active time windows for each plug directly from CoreIoT hourly power history."""
        try:
            user, err = _get_current_user()
            if err:
                return err

            lookback_days = int(request.args.get("lookbackDays", 14) or 14)
            min_active_power_w = float(request.args.get("minActivePowerW", 7) or 7)
            top_hours = int(request.args.get("topHours", 4) or 4)
            buffer_hours = int(request.args.get("bufferHours", 0) or 0)

            if lookback_days < 1 or lookback_days > 90:
                return jsonify({"status": "error", "message": "lookbackDays must be between 1 and 90"}), 400
            if top_hours < 1 or top_hours > 12:
                return jsonify({"status": "error", "message": "topHours must be between 1 and 12"}), 400
            if buffer_hours < 0 or buffer_hours > 3:
                return jsonify({"status": "error", "message": "bufferHours must be between 0 and 3"}), 400

            now = datetime.now()
            start_dt = now - timedelta(days=lookback_days)
            start_ts = int(start_dt.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
            end_ts = int(now.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)

            tracked_device_ids = shared.get_user_devices(user["id"])
            if not tracked_device_ids:
                return jsonify({"status": "empty", "message": "No plugs available for analysis", "data": []}), 200

            analysis_results = []
            skipped = []

            for device_id in tracked_device_ids:
                try:
                    points = _fetch_hourly_power(device_id, start_ts, end_ts, lookback_days)
                except Exception as fetch_err:
                    skipped.append({"deviceId": device_id, "reason": str(fetch_err)})
                    continue

                if not points:
                    skipped.append({"deviceId": device_id, "reason": "No ENERGY-Power history"})
                    continue

                hour_stats: dict[int, dict] = {
                    hour: {
                        "samples": 0,
                        "active_samples": 0,
                        "total_power_w": 0.0,
                        "weekday_active": 0,
                        "weekend_active": 0,
                    }
                    for hour in range(24)
                }

                for dt, power_w in points:
                    bucket = hour_stats[dt.hour]
                    bucket["samples"] += 1
                    bucket["total_power_w"] += power_w
                    if power_w >= min_active_power_w:
                        bucket["active_samples"] += 1
                        if dt.weekday() < 5:
                            bucket["weekday_active"] += 1
                        else:
                            bucket["weekend_active"] += 1

                scored_hours = []
                for hour in range(24):
                    item = hour_stats[hour]
                    samples = item["samples"]
                    if samples <= 0:
                        continue

                    avg_power_w = item["total_power_w"] / samples
                    active_ratio = item["active_samples"] / samples
                    score = (active_ratio * 0.6) + (min(1.0, avg_power_w / max(min_active_power_w * 2.0, 1.0)) * 0.4)
                    scored_hours.append(
                        {
                            "hour": hour,
                            "avgPowerW": round(avg_power_w, 2),
                            "activeRatio": round(active_ratio, 3),
                            "score": round(score, 3),
                            "weekdayActiveSamples": item["weekday_active"],
                            "weekendActiveSamples": item["weekend_active"],
                            "samples": samples,
                        }
                    )

                if not scored_hours:
                    skipped.append({"deviceId": device_id, "reason": "No analyzable hourly points"})
                    continue

                scored_hours.sort(key=lambda x: x["score"], reverse=True)
                top_active_hours = scored_hours[:top_hours]

                max_score = scored_hours[0]["score"]
                active_hour_set = sorted(
                    [
                        h["hour"]
                        for h in scored_hours
                        if h["activeRatio"] >= 0.45 or h["score"] >= max_score * 0.65
                    ]
                )

                windows = []
                if active_hour_set:
                    window_start = active_hour_set[0]
                    prev = active_hour_set[0]
                    for hour in active_hour_set[1:]:
                        if hour == prev + 1:
                            prev = hour
                            continue
                        windows.append((window_start, prev))
                        window_start = hour
                        prev = hour
                    windows.append((window_start, prev))

                windows = _merge_wrap_windows(windows)
                formatted_windows = [
                    {
                        "startHour": start,
                        "endHour": end,
                        "label": f"{start:02d}:00-{((end + 1) % 24):02d}:00",
                    }
                    for start, end in windows
                ]

                expanded_hour_set = sorted(
                    {
                        (hour + delta) % 24
                        for hour in active_hour_set
                        for delta in range(-buffer_hours, buffer_hours + 1)
                    }
                )

                buffered_windows = []
                if expanded_hour_set:
                    start = expanded_hour_set[0]
                    prev = expanded_hour_set[0]
                    for hour in expanded_hour_set[1:]:
                        if hour == prev + 1:
                            prev = hour
                            continue
                        buffered_windows.append((start, prev))
                        start = hour
                        prev = hour
                    buffered_windows.append((start, prev))
                buffered_windows = _merge_wrap_windows(buffered_windows)
                formatted_buffered_windows = [
                    {
                        "startHour": start,
                        "endHour": end,
                        "label": f"{start:02d}:00-{((end + 1) % 24):02d}:00",
                    }
                    for start, end in buffered_windows
                ]

                metadata = (
                    shared.CUSTOM_CB_DEVICES.get(device_id)
                    or shared.DEVICE_METADATA_CACHE.get(device_id)
                    or shared.latest_data.get(device_id, {}).get("metadata")
                    or {}
                )

                analysis_results.append(
                    {
                        "deviceId": device_id,
                        "deviceName": metadata.get("name") or f"Device {device_id[-6:]}",
                        "location": metadata.get("location"),
                        "dataPoints": len(points),
                        "minActivePowerW": min_active_power_w,
                        "bufferHours": buffer_hours,
                        "activeWindows": formatted_windows,
                        "recommendedWindows": formatted_buffered_windows,
                        "topActiveHours": top_active_hours,
                    }
                )

            analysis_results.sort(
                key=lambda item: sum(hour.get("score", 0.0) for hour in item.get("topActiveHours", [])),
                reverse=True,
            )

            return jsonify(
                {
                    "status": "success",
                    "data": analysis_results,
                    "meta": {
                        "lookbackDays": lookback_days,
                        "bufferHours": buffer_hours,
                        "source": "coreiot_direct",
                        "totalDevices": len(tracked_device_ids),
                        "analyzedDevices": len(analysis_results),
                        "skippedDevices": len(skipped),
                        "skipped": skipped,
                    },
                }
            )
        except Exception as e:
            logging.error("Error analyzing plug activity windows: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/analysis/monthly-plug-activity", methods=["GET"])
    def analyze_monthly_plug_activity():
        """Analyze plug activity within one month and return active hour windows by day."""
        try:
            user, err = _get_current_user()
            if err:
                return err

            lookback_days = int(request.args.get("lookbackDays", 30) or 30)
            min_active_power_w = float(request.args.get("minActivePowerW", 10) or 10)

            if lookback_days < 1 or lookback_days > 90:
                return jsonify({"status": "error", "message": "lookbackDays must be between 1 and 90"}), 400

            now = datetime.now()
            start_dt = now - timedelta(days=lookback_days)
            start_ts = int(start_dt.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
            end_ts = int(now.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)

            tracked_device_ids = shared.get_user_devices(user["id"])
            if not tracked_device_ids:
                return jsonify({"status": "empty", "message": "No plugs available", "data": []}), 200

            analysis_results = []
            skipped = []

            for device_id in tracked_device_ids:
                try:
                    points = _fetch_hourly_power(device_id, start_ts, end_ts, lookback_days)
                except Exception as fetch_err:
                    skipped.append({"deviceId": device_id, "reason": str(fetch_err)})
                    continue

                if len(points) < 1:
                    skipped.append({"deviceId": device_id, "reason": "No power data"})
                    continue

                hour_stats = {i: {"samples": 0, "total_power_w": 0.0, "active_samples": 0} for i in range(24)}

                for dt, power_w in points:
                    hour = dt.hour
                    hour_stats[hour]["samples"] += 1
                    hour_stats[hour]["total_power_w"] += power_w
                    if power_w >= min_active_power_w:
                        hour_stats[hour]["active_samples"] += 1

                scored_hours = []
                for hour in range(24):
                    item = hour_stats[hour]
                    samples = item["samples"]
                    if samples <= 0:
                        continue

                    avg_power_w = item["total_power_w"] / samples
                    active_ratio = item["active_samples"] / samples
                    score = (active_ratio * 0.6) + (min(1.0, avg_power_w / max(min_active_power_w * 2.0, 1.0)) * 0.4)
                    scored_hours.append(
                        {
                            "hour": hour,
                            "avgPowerW": round(avg_power_w, 2),
                            "activeRatio": round(active_ratio, 3),
                            "activeSamples": item["active_samples"],
                            "totalSamples": samples,
                            "score": round(score, 3),
                        }
                    )

                if not scored_hours:
                    skipped.append({"deviceId": device_id, "reason": "No analyzable data"})
                    continue

                scored_hours.sort(key=lambda x: x["score"], reverse=True)

                max_score = scored_hours[0]["score"] if scored_hours else 0
                active_hour_set = sorted(
                    [
                        h["hour"]
                        for h in scored_hours
                        if h["activeRatio"] >= 0.45 or h["score"] >= max_score * 0.65
                    ]
                )

                windows = []
                if active_hour_set:
                    window_start = active_hour_set[0]
                    prev = active_hour_set[0]
                    for hour in active_hour_set[1:]:
                        if hour == prev + 1:
                            prev = hour
                            continue
                        windows.append((window_start, prev))
                        window_start = hour
                        prev = hour
                    windows.append((window_start, prev))

                windows = _merge_wrap_windows(windows)
                formatted_windows = [
                    {
                        "start": f"{start:02d}:00",
                        "end": f"{((end + 1) % 24):02d}:00",
                        "startHour": start,
                        "endHour": end,
                    }
                    for start, end in windows
                ]

                metadata = (
                    shared.CUSTOM_CB_DEVICES.get(device_id)
                    or shared.DEVICE_METADATA_CACHE.get(device_id)
                    or shared.latest_data.get(device_id, {}).get("metadata")
                    or {}
                )

                total_active_hours = sum(h["activeSamples"] for h in scored_hours)
                total_potential_hours = sum(h["totalSamples"] for h in scored_hours)

                analysis_results.append(
                    {
                        "deviceId": device_id,
                        "deviceName": metadata.get("name") or f"Device {device_id[-6:]}",
                        "location": metadata.get("location", "N/A"),
                        "activeWindows": formatted_windows,
                        "hourlyAnalysis": scored_hours,
                        "stats": {
                            "dataPoints": len(points),
                            "totalActiveHours": total_active_hours,
                            "totalPotentialHours": total_potential_hours,
                            "avgActivityRatio": round(total_active_hours / total_potential_hours, 3)
                            if total_potential_hours > 0
                            else 0,
                            "minActivePowerW": min_active_power_w,
                            "lookbackDays": lookback_days,
                        },
                    }
                )

            analysis_results.sort(
                key=lambda item: item["stats"]["totalActiveHours"],
                reverse=True,
            )

            return jsonify(
                {
                    "status": "success",
                    "data": analysis_results,
                    "meta": {
                        "lookbackDays": lookback_days,
                        "source": "coreiot_direct",
                        "totalDevices": len(tracked_device_ids),
                        "analyzedDevices": len(analysis_results),
                        "skippedDevices": len(skipped),
                        "skipped": skipped,
                    },
                }
            )
        except Exception as e:
            logging.error("Error analyzing monthly plug activity: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500
