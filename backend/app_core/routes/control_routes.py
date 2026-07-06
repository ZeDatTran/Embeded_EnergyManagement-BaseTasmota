"""Control API routes"""
import logging
import time

from flask import jsonify

from app_core import shared
from app_core.auth_routes import _get_current_user


def register_control_routes(app):
    """Đăng ký các route điều khiển thiết bị."""

    @app.route("/api/control/<string:device_id>/<string:command>", methods=["POST"])
    def control_specific_device(device_id, command):
        logging.info("Control request: Device %s, Command: %s", device_id, command)

        user, err = _get_current_user()
        if err:
            return err

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401

        cb_config = shared.CUSTOM_CB_DEVICES.get(device_id)
        if not cb_config or cb_config.get("user_id") != user["id"]:
            return jsonify({"status": "error", "message": "Device not found or unauthorized"}), 404
        if command.lower() not in ["on", "off"]:
            return jsonify({"status": "error", "message": "Invalid command. Only 'on' or 'off' accepted."}), 400

        success, result = shared.send_rpc_to_device(device_id, command.upper())
        if success:
            return jsonify(result), 200

        status_code = 401 if "Token" in result.get("message", "") else 500
        return jsonify(result), status_code

    @app.route("/api/control/group/<string:command>", methods=["POST"])
    def control_group_devices(command):
        logging.info("Group control request: Command: %s", command)

        user, err = _get_current_user()
        if err:
            return err

        if not shared.verify_token():
            return jsonify({"status": "error", "message": "Invalid JWT_TOKEN"}), 401
        if command.lower() not in ["on", "off"]:
            return jsonify({"status": "error", "message": "Invalid command. Only 'on' or 'off' accepted."}), 400

        try:
            device_ids = [k for k, v in shared.CUSTOM_CB_DEVICES.items() if v.get("user_id") == user["id"]]
            if not device_ids:
                return jsonify({"status": "error", "message": "No devices found for user."}), 404
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error getting device list: {e}"}), 500

        results = []
        all_success = True
        cmd_upper = command.upper()

        for dev_id in device_ids:
            success, result = shared.send_rpc_to_device(dev_id, cmd_upper)
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

    logging.info("Control routes registered.")
