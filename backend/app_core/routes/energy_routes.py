#Energy API routes 
#Module load  ``shared.FORECAST_ENABLED`` is ``True``.

import logging
from datetime import datetime, timedelta

import requests
from flask import jsonify, request

from app_core import shared
from app_core.auth_routes import _get_current_user
from app_core.utils.electricity_bill import calculate_vietnam_electricity_bill


def register_energy_routes(app):
    """Đăng ký các route dữ liệu năng lượng (chỉ gọi khi FORECAST_ENABLED=True)."""

    @app.route("/api/energy", methods=["GET"])
    def get_energy_data():
        user, err = _get_current_user()
        if err:
            response, status_code = err
            return response, status_code

        period = request.args.get("period", "day")
        requested_device_id = (request.args.get("deviceId") or "").strip()
        req_year = request.args.get("year")
        req_month = request.args.get("month")
        now = datetime.now()

        start_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "day":
            start_time = start_of_today
            end_time = now
        elif period == "week":
            seven_days_ago = now - timedelta(days=7)
            start_time = max(seven_days_ago, start_of_this_month)
            end_time = now
        elif period == "month":
            if req_year and req_month:
                try:
                    y, m = int(req_year), int(req_month)
                    start_time = datetime(y, m, 1)
                    if m == 12:
                        end_time = datetime(y + 1, 1, 1) - timedelta(seconds=1)
                    else:
                        end_time = datetime(y, m + 1, 1) - timedelta(seconds=1)
                    if y == now.year and m == now.month:
                        end_time = now
                except (ValueError, TypeError):
                    start_time = start_of_this_month
                    end_time = now
            else:
                start_time = start_of_this_month
                end_time = now
        else:
            start_time = now - timedelta(hours=24)
            end_time = now

        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)

        if requested_device_id:
            device_ids = [requested_device_id]
        else:
            device_ids = shared.get_tracked_device_ids(user["id"])

        if not device_ids:
            return jsonify([])

        if period == "day":
            interval_ms = 3600000   # 1 giờ
            is_hourly = True
        else:
            interval_ms = 86400000  # 1 ngày
            is_hourly = False

        totals_by_interval_ts: dict[int, float] = {}
        for device_id in device_ids:
            try:
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"

                all_entries = []
                seen_ts = set()
                chunk_duration_ms = 7 * 86400 * 1000  # 7 ngày
                chunk_start = start_ts

                while chunk_start < end_ts:
                    chunk_end = min(chunk_start + chunk_duration_ms, end_ts)
                    try:
                        params = {
                            "keys": "ENERGY-Total",
                            "startTs": chunk_start,
                            "endTs": chunk_end,
                            "limit": 50000,
                            "agg": "NONE",
                            "interval": 0,
                        }
                        resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                        resp.raise_for_status()
                        raw = resp.json()
                        entries = raw.get("ENERGY-Total", [])
                        for entry in entries:
                            ts = entry.get("ts")
                            if ts not in seen_ts:
                                seen_ts.add(ts)
                                all_entries.append(entry)
                    except Exception as chunk_err:
                        logging.warning(
                            "Energy chunk fetch failed for device %s [%s-%s]: %s",
                            device_id, chunk_start, chunk_end, chunk_err,
                        )
                    chunk_start = chunk_end

                if not all_entries:
                    continue

                parsed = []
                for entry in all_entries:
                    try:
                        ts_ms = int(entry.get("ts"))
                        val = float(entry.get("value") or 0.0)
                        parsed.append((ts_ms, max(0.0, val)))
                    except (TypeError, ValueError):
                        continue

                if len(parsed) < 2:
                    continue

                parsed.sort(key=lambda x: x[0])
                logging.info(
                    "Energy data for device %s: %d points, first=%s (%.4f), last=%s (%.4f)",
                    device_id, len(parsed),
                    datetime.fromtimestamp(parsed[0][0] / 1000).isoformat(), parsed[0][1],
                    datetime.fromtimestamp(parsed[-1][0] / 1000).isoformat(), parsed[-1][1],
                )

                prev_ts_ms, prev_total = parsed[0]
                device_total_kwh = 0.0
                for ts_ms, total_kwh in parsed[1:]:
                    delta = total_kwh - prev_total

                    if delta < 0:
                        logging.debug(
                            "Counter reset for device %s at %s: %.4f -> %.4f",
                            device_id, datetime.fromtimestamp(ts_ms / 1000).isoformat(), prev_total, total_kwh,
                        )
                        prev_ts_ms, prev_total = ts_ms, total_kwh
                        continue

                    if delta == 0:
                        prev_ts_ms, prev_total = ts_ms, total_kwh
                        continue

                    dt = datetime.fromtimestamp(ts_ms / 1000)
                    if is_hourly:
                        dt_interval = dt.replace(minute=0, second=0, microsecond=0)
                    else:
                        dt_interval = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    interval_ts = int(dt_interval.timestamp() * 1000)
                    totals_by_interval_ts[interval_ts] = totals_by_interval_ts.get(interval_ts, 0.0) + delta
                    device_total_kwh += delta

                    prev_ts_ms, prev_total = ts_ms, total_kwh

                logging.info("Device %s total energy from deltas: %.4f kWh", device_id, device_total_kwh)
            except Exception as e:
                logging.warning("Energy aggregation skipped device %s due to error: %s", device_id, e)

        total_kwh = sum(totals_by_interval_ts.values())
        total_cost = calculate_vietnam_electricity_bill(total_kwh) if total_kwh > 0 else 0.0
        avg_price_per_kwh = total_cost / total_kwh if total_kwh > 0 else 0.0

        response_data = []
        current_ts = start_ts
        dt_start = datetime.fromtimestamp(current_ts / 1000)
        if not is_hourly:
            dt_start = dt_start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            dt_start = dt_start.replace(minute=0, second=0, microsecond=0)
        current_ts = int(dt_start.timestamp() * 1000)

        while current_ts <= end_ts:
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

        if not response_data:
            with shared.lock:
                sorted_items = sorted(shared.hourly_kwh_global.items(), key=lambda x: x[0])
                recent_items = sorted_items[-750:]

                total_kwh_fallback = sum(kwh for _, kwh in recent_items if datetime.fromisoformat(_) >= start_time)
                total_cost_fallback = calculate_vietnam_electricity_bill(total_kwh_fallback) if total_kwh_fallback > 0 else 0.0
                avg_price_fallback = total_cost_fallback / total_kwh_fallback if total_kwh_fallback > 0 else 0.0

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

    @app.route("/api/energy/summary", methods=["GET"])
    def get_energy_summary():
        """Trả về tóm tắt năng lượng cho các card trên trang Energy.
        - ``day``: tính từ hourly telemetry (ENERGY-Power) như biểu đồ.
        - ``month``: dùng cumulative total (ENERGY-Total).
        """
        user, err = _get_current_user()
        if err:
            response, status_code = err
            return response, status_code

        period = request.args.get("period", "month")
        requested_device_id = (request.args.get("deviceId") or "").strip()

        if period not in ["day", "month"]:
            return jsonify({"status": "success", "data": {"totalConsumption": 0.0, "totalCost": 0.0}})

        if requested_device_id:
            device_ids = [requested_device_id]
        else:
            device_ids = shared.get_tracked_device_ids(user["id"])

        if not device_ids:
            return jsonify({"status": "success", "data": {"totalConsumption": 0.0, "totalCost": 0.0}})

        total_kwh = 0.0

        if period == "day":
            now = datetime.now()
            start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_today.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)

            for device_id in device_ids:
                try:
                    url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                    params = {
                        "keys": "ENERGY-Total",
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "limit": 50000,
                        "orderBy": "ASC",
                    }
                    resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                    resp.raise_for_status()
                    raw = resp.json()

                    entries = raw.get("ENERGY-Total", [])
                    if not entries:
                        continue

                    parsed = []
                    for entry in entries:
                        try:
                            ts_ms = int(entry.get("ts"))
                            val = float(entry.get("value") or 0.0)
                            parsed.append((ts_ms, max(0.0, val)))
                        except (TypeError, ValueError):
                            continue

                    if len(parsed) < 2:
                        continue

                    parsed.sort(key=lambda x: x[0])
                    prev_total = parsed[0][1]
                    for _, cur_total in parsed[1:]:
                        delta = cur_total - prev_total
                        if delta > 0:
                            total_kwh += delta
                        prev_total = cur_total
                except Exception as e:
                    logging.warning("Energy summary (day) skipped device %s due to error: %s", device_id, e)

        else:  # month
            now = datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_month.timestamp() * 1000)
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
                        "interval": 86400000,  # mỗi ngày
                    }
                    resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=20)
                    resp.raise_for_status()
                    raw = resp.json()

                    for entry in raw.get("ENERGY-Power", []):
                        try:
                            power_w = float(entry.get("value") or 0.0)
                            kwh_day = max(0.0, power_w) * 24.0 / 1000.0
                            total_kwh += kwh_day
                        except (TypeError, ValueError):
                            continue
                except Exception as e:
                    logging.warning("Energy summary (month) skipped device %s due to error: %s", device_id, e)

        total_kwh = round(max(0.0, total_kwh), 4)
        total_cost = round(calculate_vietnam_electricity_bill(total_kwh), 2)
        return jsonify(
            {
                "status": "success",
                "data": {
                    "totalConsumption": total_kwh,
                    "totalCost": total_cost,
                },
                "source": "power_history",
            }
        )

    logging.info("Energy routes registered.")
