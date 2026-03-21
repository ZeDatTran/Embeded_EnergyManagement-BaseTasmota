PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Core hourly energy history used by existing forecast flow.
CREATE TABLE IF NOT EXISTS hourly_kwh (
    timestamp TEXT PRIMARY KEY,
    kwh REAL NOT NULL CHECK (kwh >= 0)
);

CREATE TABLE IF NOT EXISTS training_log (
    date TEXT PRIMARY KEY,
    r2_rf REAL,
    r2_xgb REAL,
    r2_mlp REAL,
    r2_lr REAL,
    note TEXT
);

-- Expanded schedules table for both manual and optimizer-generated schedules.
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('on', 'off')),
    time TEXT NOT NULL,
    days TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'optimizer', 'system', 'imported')),
    source_run_id TEXT,
    approval_status TEXT NOT NULL DEFAULT 'manual' CHECK (approval_status IN ('manual', 'pending', 'approved', 'auto_approved', 'rejected')),
    execution_priority INTEGER NOT NULL DEFAULT 100,
    expires_at TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedules_enabled_time
    ON schedules (enabled, time);

CREATE INDEX IF NOT EXISTS idx_schedules_source
    ON schedules (source, source_run_id);

CREATE INDEX IF NOT EXISTS idx_schedules_approval_status
    ON schedules (approval_status);

-- Monthly budget profile configured by the user.
CREATE TABLE IF NOT EXISTS energy_budget_profiles (
    id TEXT PRIMARY KEY,
    month_key TEXT NOT NULL UNIQUE,
    target_bill_vnd REAL NOT NULL CHECK (target_bill_vnd > 0),
    warning_threshold_percent REAL NOT NULL DEFAULT 0.9
        CHECK (warning_threshold_percent > 0 AND warning_threshold_percent <= 1.5),
    optimization_mode TEXT NOT NULL DEFAULT 'manual'
        CHECK (optimization_mode IN ('manual', 'assisted', 'automatic')),
    auto_apply_recommendations INTEGER NOT NULL DEFAULT 0
        CHECK (auto_apply_recommendations IN (0, 1)),
    target_kwh_month REAL,
    current_spent_vnd REAL,
    current_consumed_kwh REAL,
    latest_forecast_bill_vnd REAL,
    latest_forecast_kwh_month REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_energy_budget_profiles_status
    ON energy_budget_profiles (status);

-- User preferences and constraints for each plug/device.
CREATE TABLE IF NOT EXISTS device_usage_preferences (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL UNIQUE,
    device_name_snapshot TEXT,
    room_name_snapshot TEXT,
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('critical', 'high', 'medium', 'low', 'flexible')),
    auto_controllable INTEGER NOT NULL DEFAULT 0
        CHECK (auto_controllable IN (0, 1)),
    required_daily_runtime_minutes INTEGER NOT NULL DEFAULT 0
        CHECK (required_daily_runtime_minutes >= 0),
    min_runtime_block_minutes INTEGER NOT NULL DEFAULT 15
        CHECK (min_runtime_block_minutes >= 0),
    max_runtime_block_minutes INTEGER,
    min_off_block_minutes INTEGER NOT NULL DEFAULT 0
        CHECK (min_off_block_minutes >= 0),
    allowed_days_json TEXT,
    allowed_time_windows_json TEXT,
    blocked_time_windows_json TEXT,
    preferred_time_windows_json TEXT,
    avoid_peak_hours INTEGER NOT NULL DEFAULT 0
        CHECK (avoid_peak_hours IN (0, 1)),
    comfort_weight REAL NOT NULL DEFAULT 0.5
        CHECK (comfort_weight >= 0 AND comfort_weight <= 1),
    saving_weight REAL NOT NULL DEFAULT 0.5
        CHECK (saving_weight >= 0 AND saving_weight <= 1),
    hard_must_run INTEGER NOT NULL DEFAULT 0
        CHECK (hard_must_run IN (0, 1)),
    estimated_power_watts REAL,
    standby_power_watts REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        max_runtime_block_minutes IS NULL
        OR max_runtime_block_minutes >= min_runtime_block_minutes
    )
);

CREATE INDEX IF NOT EXISTS idx_device_usage_preferences_priority
    ON device_usage_preferences (priority, auto_controllable);

-- Hourly telemetry aggregates for each plug.
CREATE TABLE IF NOT EXISTS plug_hourly_energy (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    hour_bucket TEXT NOT NULL,
    power_avg_w REAL,
    current_avg_a REAL,
    voltage_avg_v REAL,
    energy_kwh REAL NOT NULL DEFAULT 0 CHECK (energy_kwh >= 0),
    on_minutes INTEGER NOT NULL DEFAULT 0 CHECK (on_minutes >= 0 AND on_minutes <= 60),
    samples_count INTEGER NOT NULL DEFAULT 0 CHECK (samples_count >= 0),
    source TEXT NOT NULL DEFAULT 'coreiot'
        CHECK (source IN ('coreiot', 'derived', 'backfill', 'manual')),
    created_at TEXT NOT NULL,
    UNIQUE (device_id, hour_bucket)
);

CREATE INDEX IF NOT EXISTS idx_plug_hourly_energy_device_hour
    ON plug_hourly_energy (device_id, hour_bucket DESC);

CREATE INDEX IF NOT EXISTS idx_plug_hourly_energy_hour_bucket
    ON plug_hourly_energy (hour_bucket DESC);

-- Aggregate profiling per plug to speed up recommendation generation.
CREATE TABLE IF NOT EXISTS plug_consumption_profiles (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL UNIQUE,
    baseline_hourly_kwh_json TEXT,
    weekday_hourly_kwh_json TEXT,
    weekend_hourly_kwh_json TEXT,
    peak_hour_windows_json TEXT,
    typical_runtime_windows_json TEXT,
    avg_daily_kwh REAL,
    avg_monthly_kwh REAL,
    avg_power_when_on_w REAL,
    standby_power_w REAL,
    confidence_score REAL NOT NULL DEFAULT 0.5
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    sample_days INTEGER NOT NULL DEFAULT 0 CHECK (sample_days >= 0),
    last_profiled_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plug_consumption_profiles_confidence
    ON plug_consumption_profiles (confidence_score DESC);

-- Each optimization/planning attempt is recorded as a run.
CREATE TABLE IF NOT EXISTS budget_recommendation_runs (
    id TEXT PRIMARY KEY,
    budget_profile_id TEXT NOT NULL,
    month_key TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_by TEXT NOT NULL DEFAULT 'system',
    run_type TEXT NOT NULL DEFAULT 'manual'
        CHECK (run_type IN ('manual', 'scheduled', 'reactive', 'automatic')),
    planning_horizon_days INTEGER NOT NULL DEFAULT 3
        CHECK (planning_horizon_days > 0),
    strategy TEXT NOT NULL DEFAULT 'balanced'
        CHECK (strategy IN ('conservative', 'balanced', 'aggressive')),
    baseline_forecast_bill_vnd REAL NOT NULL,
    optimized_forecast_bill_vnd REAL,
    baseline_forecast_kwh REAL NOT NULL,
    optimized_forecast_kwh REAL,
    required_bill_reduction_vnd REAL NOT NULL DEFAULT 0,
    required_kwh_reduction REAL NOT NULL DEFAULT 0,
    achieved_kwh_reduction_estimate REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'applied', 'rejected', 'expired')),
    summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (budget_profile_id) REFERENCES energy_budget_profiles (id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_budget_recommendation_runs_month
    ON budget_recommendation_runs (month_key, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_budget_recommendation_runs_status
    ON budget_recommendation_runs (status, generated_at DESC);

-- Detailed optimizer actions per plug.
CREATE TABLE IF NOT EXISTS recommendation_actions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    action_type TEXT NOT NULL
        CHECK (action_type IN ('turn_off_window', 'delay_start', 'shorten_runtime', 'move_to_offpeak', 'cap_runtime', 'turn_on_window')),
    proposed_action TEXT NOT NULL CHECK (proposed_action IN ('on', 'off')),
    proposed_start TEXT NOT NULL,
    proposed_end TEXT,
    proposed_duration_minutes INTEGER NOT NULL DEFAULT 0 CHECK (proposed_duration_minutes >= 0),
    estimated_energy_saved_kwh REAL NOT NULL DEFAULT 0,
    estimated_cost_saved_vnd REAL NOT NULL DEFAULT 0,
    comfort_impact_score REAL NOT NULL DEFAULT 0 CHECK (comfort_impact_score >= 0),
    saving_score REAL NOT NULL DEFAULT 0 CHECK (saving_score >= 0),
    confidence_score REAL NOT NULL DEFAULT 0.5
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    priority_score REAL NOT NULL DEFAULT 0,
    reason_code TEXT NOT NULL,
    reason_text TEXT,
    approval_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (approval_status IN ('pending', 'approved', 'rejected', 'auto_approved', 'applied', 'skipped')),
    mapped_schedule_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES budget_recommendation_runs (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (mapped_schedule_id) REFERENCES schedules (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CHECK (proposed_end IS NULL OR proposed_end >= proposed_start)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_actions_run
    ON recommendation_actions (run_id, approval_status);

CREATE INDEX IF NOT EXISTS idx_recommendation_actions_device
    ON recommendation_actions (device_id, proposed_start);

-- Optional rules that steer compilation of recommendations to schedules.
CREATE TABLE IF NOT EXISTS schedule_generation_rules (
    id TEXT PRIMARY KEY,
    device_id TEXT,
    avoid_peak_hours INTEGER NOT NULL DEFAULT 0 CHECK (avoid_peak_hours IN (0, 1)),
    peak_windows_json TEXT,
    max_daily_start_events INTEGER NOT NULL DEFAULT 4 CHECK (max_daily_start_events >= 0),
    max_daily_stop_events INTEGER NOT NULL DEFAULT 4 CHECK (max_daily_stop_events >= 0),
    combine_adjacent_slots INTEGER NOT NULL DEFAULT 1 CHECK (combine_adjacent_slots IN (0, 1)),
    default_schedule_action_mode TEXT NOT NULL DEFAULT 'absolute'
        CHECK (default_schedule_action_mode IN ('absolute', 'delta')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schedule_generation_rules_device
    ON schedule_generation_rules (device_id);

-- Runtime log of executed optimizer/manual schedules.
CREATE TABLE IF NOT EXISTS schedule_execution_log (
    id TEXT PRIMARY KEY,
    schedule_id TEXT,
    source_run_id TEXT,
    device_id TEXT NOT NULL,
    planned_action TEXT NOT NULL CHECK (planned_action IN ('on', 'off')),
    executed_action TEXT CHECK (executed_action IN ('on', 'off')),
    planned_at TEXT NOT NULL,
    executed_at TEXT,
    execution_status TEXT NOT NULL
        CHECK (execution_status IN ('success', 'failed', 'skipped', 'pending')),
    failure_reason TEXT,
    actual_power_before_w REAL,
    actual_power_after_w REAL,
    actual_current_before_a REAL,
    actual_current_after_a REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES schedules (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (source_run_id) REFERENCES budget_recommendation_runs (id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_schedule_execution_log_schedule
    ON schedule_execution_log (schedule_id, planned_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedule_execution_log_run
    ON schedule_execution_log (source_run_id, planned_at DESC);

-- High-level optimizer execution result for auditing and future learning.
CREATE TABLE IF NOT EXISTS optimization_execution_log (
    id TEXT PRIMARY KEY,
    recommendation_run_id TEXT,
    schedule_id TEXT,
    device_id TEXT NOT NULL,
    planned_action TEXT NOT NULL CHECK (planned_action IN ('on', 'off')),
    executed_action TEXT CHECK (executed_action IN ('on', 'off')),
    planned_time TEXT NOT NULL,
    executed_time TEXT,
    execution_status TEXT NOT NULL
        CHECK (execution_status IN ('success', 'failed', 'skipped', 'pending')),
    failure_reason TEXT,
    estimated_energy_saved_kwh REAL,
    actual_energy_saved_kwh REAL,
    estimated_cost_saved_vnd REAL,
    actual_cost_saved_vnd REAL,
    actual_power_before REAL,
    actual_power_after REAL,
    actual_current_before REAL,
    actual_current_after REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_run_id) REFERENCES budget_recommendation_runs (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES schedules (id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_optimization_execution_log_run
    ON optimization_execution_log (recommendation_run_id, planned_time DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_execution_log_device
    ON optimization_execution_log (device_id, planned_time DESC);

-- Trigger helpers for updated_at maintenance.
CREATE TRIGGER IF NOT EXISTS trg_energy_budget_profiles_updated_at
AFTER UPDATE ON energy_budget_profiles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE energy_budget_profiles
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_device_usage_preferences_updated_at
AFTER UPDATE ON device_usage_preferences
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE device_usage_preferences
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_plug_consumption_profiles_updated_at
AFTER UPDATE ON plug_consumption_profiles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE plug_consumption_profiles
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_budget_recommendation_runs_updated_at
AFTER UPDATE ON budget_recommendation_runs
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE budget_recommendation_runs
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_recommendation_actions_updated_at
AFTER UPDATE ON recommendation_actions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE recommendation_actions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_schedule_generation_rules_updated_at
AFTER UPDATE ON schedule_generation_rules
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE schedule_generation_rules
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

COMMIT;