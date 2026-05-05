"""
Database module — MongoDB backend.
Re-exports all database functions so existing imports remain unchanged.
"""
from db_connection import init_indexes

# Core: hourly_kwh, training_log, plug_hourly_energy
from db_core import (
    save_hourly_kwh,
    get_all_history,
    log_training_result,
    save_plug_hourly_energy,
    list_plug_hourly_energy,
    get_plug_consumption_totals,
    get_device_hourly_average,
    get_device_daily_runtime_average,
)

# Budget profiles & device usage preferences
from db_budget import (
    get_current_energy_budget_profile,
    list_energy_budget_profiles,
    upsert_energy_budget_profile,
    update_energy_budget_analysis,
    get_device_usage_preferences,
    get_device_usage_preference,
    upsert_device_usage_preference,
    create_default_preferences_for_devices,
)

# Recommendation runs, actions, execution log
from db_recommendations import (
    create_recommendation_run,
    update_recommendation_run,
    get_recommendation_run,
    list_recommendation_runs,
    add_recommendation_action,
    get_recommendation_action,
    list_recommendation_actions,
    update_recommendation_action,
    log_schedule_execution,
)

# Schedule CRUD
from db_schedules import (
    create_schedule,
    get_all_schedules,
    get_schedule_by_id,
    update_schedule,
    delete_schedule,
    get_enabled_schedules,
)

# User management (NEW - for future login/register)
from db_users import (
    create_user,
    find_user_by_email,
    find_user_by_username,
    find_user_by_id,
    update_user,
    update_last_login,
    list_users,
    delete_user,
)

# Device management
from db_devices import (
    create_device,
    get_device_by_id,
    get_devices_by_user,
    get_all_devices,
    update_device,
    delete_device,
)


def init_db():
    """Initialize MongoDB indexes for all collections."""
    init_indexes()


# Auto-initialize on import (same behavior as original SQLite version)
init_db()