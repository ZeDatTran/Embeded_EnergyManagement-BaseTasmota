import threading

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from app_core import shared
from app_core.api import register_routes
from app_core.socket_events import register_socket_handlers
from app_core.workers import periodic_data_logger, schedule_executor, start_websocket


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

register_routes(app, socketio)
register_socket_handlers(socketio)


def start_background_jobs():
    threading.Thread(target=periodic_data_logger, daemon=True).start()
    threading.Thread(target=lambda: start_websocket(socketio), daemon=True).start()
    threading.Thread(target=lambda: schedule_executor(socketio), daemon=True).start()


if __name__ == "__main__":
    print("=" * 60)
    print(" SMART HOME BACKEND - FULL FEATURES")
    print("=" * 60)
    print(f" Forecast Enabled: {shared.FORECAST_ENABLED}")
    print(" Auto-Shutdown Enabled: True")
    print(" Activity Logs Enabled: True")
    print(" Realtime Alerts Enabled: True")
    print(" Schedule Executor Enabled: True")
    print("=" * 60)

    start_background_jobs()

    if shared.FORECAST_ENABLED:
        shared.load_hourly_kwh_from_db()

    print(" Server starting on http://0.0.0.0:5000")
    print(" Schedule executor running...")
    print("=" * 60)

    socketio.run(app, debug=True, port=5000, host="0.0.0.0", allow_unsafe_werkzeug=True)
