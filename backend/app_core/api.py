"""API aggregator
module routes:
    app_core/routes/
        general_routes.py   — GET /api/, GET /api/check-token
        device_routes.py    — CRUD CB devices, check-data, device history
        control_routes.py   — POST /api/control/<id>/<cmd>, POST /api/control/group/<cmd>
        schedule_routes.py  — CRUD /api/schedules + auto-scenarios
        forecast_routes.py  — GET /api/forecast, POST /api/forecast/push-coreiot, GET /api/forecast/summary
        energy_routes.py    — GET /api/energy, GET /api/energy/summary
"""
import logging

from app_core import shared
from app_core.analysis_routes import register_analysis_routes
from app_core.routes.general_routes import register_general_routes
from app_core.routes.device_routes import register_device_routes
from app_core.routes.control_routes import register_control_routes
from app_core.routes.schedule_routes import register_schedule_routes

# Forecast & Energy chỉ import khi cần (tránh lỗi import nếu ML deps thiếu)
if shared.FORECAST_ENABLED:
    from app_core.routes.forecast_routes import register_forecast_routes
    from app_core.routes.energy_routes import register_energy_routes


def register_routes(app, socketio):
    """Đăng ký tất cả API routes vào Flask app."""

    # Analysis routes (giữ nguyên từ trước)
    register_analysis_routes(app)

    # Các nhóm route chính
    register_general_routes(app)
    register_device_routes(app, socketio)
    register_control_routes(app)
    register_schedule_routes(app, socketio)

    if shared.FORECAST_ENABLED:
        register_forecast_routes(app)
        register_energy_routes(app)
        logging.info("Forecast & Energy routes registered (FORECAST_ENABLED=True).")
    else:
        logging.info("Forecast & Energy routes SKIPPED (FORECAST_ENABLED=False).")

    logging.info("All API routes registered successfully.")
