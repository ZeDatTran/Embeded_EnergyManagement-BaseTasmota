import threading
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

from app_core import shared
from app_core.api import register_routes

from app_core.auth_routes import register_auth_routes

from app_core.chatbot_api import chatbot_bp

from app_core.socket_events import register_socket_handlers
from app_core.workers import periodic_data_logger, schedule_executor, start_websocket


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
shared.socketio_instance = socketio  # expose to chatbot_api for state-sync broadcasts

register_routes(app, socketio)

register_auth_routes(app)

app.register_blueprint(chatbot_bp)

register_socket_handlers(socketio)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logging.exception("Unhandled error on %s: %s", request.path, error)
    return jsonify({"status": "error", "message": str(error)}), 500


def start_background_jobs():
    threading.Thread(target=periodic_data_logger, daemon=True).start()
    threading.Thread(target=lambda: start_websocket(socketio), daemon=True).start()
    threading.Thread(target=lambda: schedule_executor(socketio), daemon=True).start()


if __name__ == "__main__":
    # Configure logging for debug output
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print(" SMART HOME BACKEND - FULL FEATURES")
    print("=" * 60)
    print(f" Forecast Enabled: {shared.FORECAST_ENABLED}")
    print(" Auto-Shutdown Enabled: True")
    print(" Activity Logs Enabled: True")
    print(" Realtime Alerts Enabled: True")
    print(" Schedule Executor Enabled: True")
    print("=" * 60)

    shared.load_devices_from_db()
    start_background_jobs()

    if shared.FORECAST_ENABLED:
        shared.load_hourly_kwh_from_db()

    print(" Server starting on http://0.0.0.0:5000")
    print(" Schedule executor running...")
    print("=" * 60)

    socketio.run(app, debug=True, port=5000, host="0.0.0.0", allow_unsafe_werkzeug=True)
