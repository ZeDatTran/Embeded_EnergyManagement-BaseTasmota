#General API routes home endpoint and token check.
import logging

from flask import jsonify

from app_core import shared


def register_general_routes(app):
    #Đăng ký các route chung: trang chủ API và kiểm tra token.

    @app.route("/api/", methods=["GET"])
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

    @app.route("/api/check-token", methods=["GET"])
    def check_token():
        if shared.verify_token():
            return jsonify({"status": "success", "message": "JWT_TOKEN is valid"})
        return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

    logging.info("General routes registered.")
