#Forecast API routes
#Module  load  ``shared.FORECAST_ENABLED`` is ``True``.
import logging
import os
import time

import requests
from flask import jsonify, request

from app_core import shared
from app_core.auth_routes import _get_current_user
from database import save_user_forecast, get_user_forecast
from datetime import datetime


def register_forecast_routes(app):
    """Đăng ký các route dự báo (chỉ gọi khi FORECAST_ENABLED=True)."""

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _push_ml_analysis_to_coreiot(device_id: str, forecast_payload: dict):
        """Push ML analysis telemetry và prediction attributes lên CoreIoT cho một thiết bị."""
        now_ms = int(time.time() * 1000)
        predicted_bill_vnd = round(float(forecast_payload.get("PredictedBillVND", 0) or 0), 2)
        predicted_kwh = round(float(forecast_payload.get("TotalKwhForecasted", 0) or 0), 6)
        values = {
            "ml_predicted_bill_vnd": predicted_bill_vnd,
            "ml_total_kwh_forecasted": predicted_kwh,
            "ml_total_kwh_month": round(float(forecast_payload.get("TotalKwhMonth", 0) or 0), 6),
            "ml_consumed_this_month_kwh": round(float(forecast_payload.get("ConsumedThisMonthKwh", 0) or 0), 6),
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

    def _month_consumption_from_energy_summary_source(user_id: str, timeout_sec: float = 20.0) -> float:
        """Tính tiêu thụ tháng (kWh) từ ENERGY-Total delta — chỉ thiết bị đã đăng ký."""
        now = datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_ts = int(start_of_month.timestamp() * 1000)
        end_ts = int(now.timestamp() * 1000)

        device_ids = [d for d in shared.get_tracked_device_ids(user_id) if d]

        total_month_kwh = 0.0
        for device_id in device_ids:
            try:
                url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                params = {
                    "keys": "ENERGY-Total",
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "limit": 50000,
                    "agg": "NONE",
                }
                resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=timeout_sec)
                if resp.ok:
                    entries = resp.json().get("ENERGY-Total", [])
                    if len(entries) >= 2:
                        parsed = []
                        for e in entries:
                            try:
                                parsed.append((int(e["ts"]), max(0.0, float(e["value"] or 0))))
                            except Exception:
                                continue
                        parsed.sort(key=lambda x: x[0])

                        prev_total = parsed[0][1]
                        device_kwh = 0.0
                        for _, cur_total in parsed[1:]:
                            delta = cur_total - prev_total
                            if delta > 0:
                                device_kwh += delta
                            prev_total = cur_total

                        total_month_kwh += device_kwh
                        logging.info("Device %s accurate month consumption: %.4f kWh", device_id, device_kwh)
            except Exception as e:
                logging.warning("Accurate fetch failed for %s: %s", device_id, e)

        return round(max(0.0, total_month_kwh), 6)

    # ------------------------------------------------------------------ #
    # Routes                                                               #
    # ------------------------------------------------------------------ #

    @app.route("/api/forecast", methods=["GET"])
    @app.route("/forecast", methods=["GET"])
    def trigger_forecast():
        user, err = _get_current_user()
        if err:
            response, status_code = err
            return response, status_code

        plugs = shared.get_all_plugs_for_forecast(user["id"])
        logging.info("--- MANUAL FORECAST TRIGGERED ---")
        try:
            forecast_coreiot_timeout = float(os.getenv("FORECAST_COREIOT_TIMEOUT_SEC", "6"))
        except ValueError:
            forecast_coreiot_timeout = 6.0

        def _coreiot_hourly_kwh(start_dt: datetime, end_dt: datetime) -> dict[str, float]:
            """Tính kWh theo giờ từ ENERGY-Total delta — chỉ thiết bị đã đăng ký."""
            start_ts = int(start_dt.timestamp() * 1000)
            end_ts = int(end_dt.timestamp() * 1000)
            device_ids = shared.get_tracked_device_ids(user["id"])
            if not device_ids:
                logging.warning("Forecast: no registered devices for user %s", user["id"])
                return {}

            totals_by_hour_iso: dict[str, float] = {}
            for device_id in device_ids:
                try:
                    url = f"{shared.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
                    params = {
                        "keys": "ENERGY-Total",
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "limit": 50000,
                        "agg": "NONE",
                        "interval": 0,
                    }
                    resp = requests.get(url, headers=shared.HEADERS, params=params, timeout=forecast_coreiot_timeout)
                    resp.raise_for_status()
                    raw = resp.json()

                    entries = raw.get("ENERGY-Total", [])
                    if len(entries) < 2:
                        logging.info("Forecast: not enough ENERGY-Total entries for device %s", device_id)
                        continue

                    parsed = []
                    for e in entries:
                        try:
                            parsed.append((int(e["ts"]), max(0.0, float(e.get("value") or 0.0))))
                        except (TypeError, ValueError, KeyError):
                            continue
                    parsed.sort(key=lambda x: x[0])

                    prev_ts_ms, prev_total = parsed[0]
                    for ts_ms, total_kwh in parsed[1:]:
                        delta = total_kwh - prev_total
                        if delta > 0:
                            time_gap_min = (ts_ms - prev_ts_ms) / 60000
                            if time_gap_min > 30 and delta < 0.05:
                                prev_ts_ms, prev_total = ts_ms, total_kwh
                                continue
                            dt_hour = datetime.fromtimestamp(ts_ms / 1000).replace(minute=0, second=0, microsecond=0)
                            iso_ts = dt_hour.strftime("%Y-%m-%dT%H:00:00")
                            totals_by_hour_iso[iso_ts] = round(
                                totals_by_hour_iso.get(iso_ts, 0.0) + delta, 6
                            )
                        prev_ts_ms, prev_total = ts_ms, total_kwh

                    logging.info("Forecast: device %s contributed %d hourly buckets", device_id, len(totals_by_hour_iso))
                except Exception as e:
                    logging.warning("Forecast source skipped device %s due to error: %s", device_id, e)

            return dict(sorted(totals_by_hour_iso.items()))

        def _coreiot_latest_total_kwh() -> float:
            device_ids = shared.get_tracked_device_ids(user["id"])
            if not device_ids:
                return 0.0

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
                    if not isinstance(raw, dict):
                        logging.warning("Unexpected non-dict response for %s: %s", device_id, raw)
                        continue

                    entries = raw.get("ENERGY-Total", [])
                    if not entries or not isinstance(entries, list):
                        continue

                    first_entry = entries[0]
                    if isinstance(first_entry, dict):
                        total_kwh += float(first_entry.get("value") or 0.0)
                except Exception as e:
                    logging.warning("Forecast total source skipped device %s due to error: %s", device_id, e)

            return round(max(0.0, total_kwh), 6)

        with shared.lock:
            if len(shared.hourly_kwh_global) < 1:
                logging.info("Forecast cache is sparse, attempting CoreIoT monthly history fetch")

            now = datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            coreiot_history = _coreiot_hourly_kwh(start_of_month, now)
            if coreiot_history:
                consumed = _month_consumption_from_energy_summary_source(user["id"], forecast_coreiot_timeout)
                if consumed <= 0:
                    consumed = sum(coreiot_history.values())
                recent_history = dict(sorted(coreiot_history.items(), key=lambda x: x[0], reverse=True)[:1200])
            else:
                consumed = _month_consumption_from_energy_summary_source(user["id"], forecast_coreiot_timeout)
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

            save_user_forecast(user["id"], result)
            return jsonify(result)

        return jsonify({"status": "error", "message": "AI Server not responding"}), 500

    @app.route("/api/forecast/push-coreiot", methods=["POST"])
    def push_forecast_to_coreiot():
        """Push latest forecast analysis data lên CoreIoT dưới dạng telemetry."""
        user, err = _get_current_user()
        if err:
            response, status_code = err
            return response, status_code

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
            forecast_payload = get_user_forecast(user["id"])
            if not forecast_payload:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Chưa có dữ liệu dự báo. Vui lòng nhấn nút 'Dự báo' trước.",
                        }
                    ),
                    404,
                )

        ok, result = _push_ml_analysis_to_coreiot(device_id, forecast_payload)
        if ok:
            return jsonify({"status": "success", "result": result})
        return jsonify({"status": "error", "result": result}), 502

    @app.route("/api/forecast/summary", methods=["GET"])
    @app.route("/forecast/summary", methods=["GET"])
    def forecast_summary():
        user, err = _get_current_user()
        if err:
            response, status_code = err
            return response, status_code

        try:
            full_result = get_user_forecast(user["id"])
            if full_result:
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

    logging.info("Forecast routes registered.")
