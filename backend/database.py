import json
import os
import sqlite3
import uuid
from datetime import datetime
from threading import Lock

DB_PATH = "data/power_history.db"
os.makedirs("data", exist_ok=True)
lock = Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn, table_name: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in cur.fetchall()}


def _ensure_column(conn, table_name: str, column_name: str, definition: str):
    columns = _table_columns(conn, table_name)
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _row_to_schedule(row: sqlite3.Row) -> dict:
    metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else None
    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            metadata = None

    return {
        "id": row["id"],
        "name": row["name"],
        "targetId": row["target_id"],
        "action": row["action"],
        "time": row["time"],
        "days": json.loads(row["days"]),
        "enabled": bool(row["enabled"]),
        "runOnce": bool(row["run_once"]) if "run_once" in row.keys() else False,
        "source": row["source"] if "source" in row.keys() else "manual",
        "sourceRunId": row["source_run_id"] if "source_run_id" in row.keys() else None,
        "approvalStatus": row["approval_status"] if "approval_status" in row.keys() else "manual",
        "executionPriority": row["execution_priority"] if "execution_priority" in row.keys() else 100,
        "expiresAt": row["expires_at"] if "expires_at" in row.keys() else None,
        "metadata": metadata,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def init_db():
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS hourly_kwh (
                timestamp TEXT PRIMARY KEY,
                kwh REAL NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS training_log (
                date TEXT PRIMARY KEY,
                r2_rf REAL, r2_xgb REAL, r2_mlp REAL, r2_lr REAL,
                note TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('on', 'off')),
                time TEXT NOT NULL,
                days TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )"""
        )

        _ensure_column(conn, "schedules", "source", "TEXT NOT NULL DEFAULT 'manual'")
        _ensure_column(conn, "schedules", "source_run_id", "TEXT")
        _ensure_column(conn, "schedules", "approval_status", "TEXT NOT NULL DEFAULT 'manual'")
        _ensure_column(conn, "schedules", "execution_priority", "INTEGER NOT NULL DEFAULT 100")
        _ensure_column(conn, "schedules", "expires_at", "TEXT")
        _ensure_column(conn, "schedules", "metadata_json", "TEXT")
        _ensure_column(conn, "schedules", "run_once", "INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            """CREATE TABLE IF NOT EXISTS energy_budget_profiles (
                id TEXT PRIMARY KEY,
                month_key TEXT NOT NULL UNIQUE,
                target_bill_vnd REAL NOT NULL,
                warning_threshold_percent REAL NOT NULL DEFAULT 0.9,
                optimization_mode TEXT NOT NULL DEFAULT 'manual',
                auto_apply_recommendations INTEGER NOT NULL DEFAULT 0,
                target_kwh_month REAL,
                current_spent_vnd REAL,
                current_consumed_kwh REAL,
                latest_forecast_bill_vnd REAL,
                latest_forecast_kwh_month REAL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS device_usage_preferences (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL UNIQUE,
                device_name_snapshot TEXT,
                room_name_snapshot TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                auto_controllable INTEGER NOT NULL DEFAULT 0,
                required_daily_runtime_minutes INTEGER NOT NULL DEFAULT 0,
                min_runtime_block_minutes INTEGER NOT NULL DEFAULT 15,
                max_runtime_block_minutes INTEGER,
                min_off_block_minutes INTEGER NOT NULL DEFAULT 0,
                allowed_days_json TEXT,
                allowed_time_windows_json TEXT,
                blocked_time_windows_json TEXT,
                preferred_time_windows_json TEXT,
                avoid_peak_hours INTEGER NOT NULL DEFAULT 0,
                comfort_weight REAL NOT NULL DEFAULT 0.5,
                saving_weight REAL NOT NULL DEFAULT 0.5,
                hard_must_run INTEGER NOT NULL DEFAULT 0,
                estimated_power_watts REAL,
                standby_power_watts REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS plug_hourly_energy (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                hour_bucket TEXT NOT NULL,
                power_avg_w REAL,
                current_avg_a REAL,
                voltage_avg_v REAL,
                energy_kwh REAL NOT NULL DEFAULT 0,
                on_minutes INTEGER NOT NULL DEFAULT 0,
                samples_count INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'coreiot',
                created_at TEXT NOT NULL,
                UNIQUE(device_id, hour_bucket)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS plug_consumption_profiles (
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
                confidence_score REAL NOT NULL DEFAULT 0.5,
                sample_days INTEGER NOT NULL DEFAULT 0,
                last_profiled_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS budget_recommendation_runs (
                id TEXT PRIMARY KEY,
                budget_profile_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                generated_by TEXT NOT NULL DEFAULT 'system',
                run_type TEXT NOT NULL DEFAULT 'manual',
                planning_horizon_days INTEGER NOT NULL DEFAULT 3,
                strategy TEXT NOT NULL DEFAULT 'balanced',
                baseline_forecast_bill_vnd REAL NOT NULL,
                optimized_forecast_bill_vnd REAL,
                baseline_forecast_kwh REAL NOT NULL,
                optimized_forecast_kwh REAL,
                required_bill_reduction_vnd REAL NOT NULL DEFAULT 0,
                required_kwh_reduction REAL NOT NULL DEFAULT 0,
                achieved_kwh_reduction_estimate REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                summary_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (budget_profile_id) REFERENCES energy_budget_profiles(id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recommendation_actions (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                proposed_action TEXT NOT NULL,
                proposed_start TEXT NOT NULL,
                proposed_end TEXT,
                proposed_duration_minutes INTEGER NOT NULL DEFAULT 0,
                estimated_energy_saved_kwh REAL NOT NULL DEFAULT 0,
                estimated_cost_saved_vnd REAL NOT NULL DEFAULT 0,
                comfort_impact_score REAL NOT NULL DEFAULT 0,
                saving_score REAL NOT NULL DEFAULT 0,
                confidence_score REAL NOT NULL DEFAULT 0.5,
                priority_score REAL NOT NULL DEFAULT 0,
                reason_code TEXT NOT NULL,
                reason_text TEXT,
                approval_status TEXT NOT NULL DEFAULT 'pending',
                mapped_schedule_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES budget_recommendation_runs(id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schedule_execution_log (
                id TEXT PRIMARY KEY,
                schedule_id TEXT,
                source_run_id TEXT,
                device_id TEXT NOT NULL,
                planned_action TEXT NOT NULL,
                executed_action TEXT,
                planned_at TEXT NOT NULL,
                executed_at TEXT,
                execution_status TEXT NOT NULL,
                failure_reason TEXT,
                actual_power_before_w REAL,
                actual_power_after_w REAL,
                actual_current_before_a REAL,
                actual_current_after_a REAL,
                created_at TEXT NOT NULL
            )"""
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plug_hourly_energy_device_hour ON plug_hourly_energy (device_id, hour_bucket DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budget_recommendation_runs_month ON budget_recommendation_runs (month_key, generated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recommendation_actions_run ON recommendation_actions (run_id, approval_status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedule_execution_log_schedule ON schedule_execution_log (schedule_id, planned_at DESC)"
        )
        conn.commit()


def save_hourly_kwh(timestamp_iso: str, kwh: float):
    with lock:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO hourly_kwh (timestamp, kwh) VALUES (?, ?)",
                (timestamp_iso, round(kwh, 6)),
            )
            conn.commit()


def get_all_history():
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT timestamp, kwh FROM hourly_kwh ORDER BY timestamp")
        rows = cur.fetchall()
        return {row["timestamp"]: row["kwh"] for row in rows}


def log_training_result(date_str, scores: dict, note=""):
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO training_log
            (date, r2_rf, r2_xgb, r2_mlp, r2_lr, note)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (date_str, scores.get("rf"), scores.get("xgb"), scores.get("mlp"), scores.get("lr"), note),
        )
        conn.commit()


def save_plug_hourly_energy(
    device_id: str,
    hour_bucket: str,
    energy_kwh: float,
    power_avg_w: float | None = None,
    current_avg_a: float | None = None,
    voltage_avg_v: float | None = None,
    on_minutes: int = 0,
    samples_count: int = 1,
    source: str = "coreiot",
):
    record_id = f"{device_id}:{hour_bucket}"
    created_at = datetime.now().isoformat()
    with lock:
        with _connect() as conn:
            if source == "derived":
                # "derived" rows come from polling ENERGY-Power every ~10s.
                # Do NOT accumulate energy_kwh on conflict: the accurate ENERGY-Total
                # delta (source="coreiot") is the single source of truth for energy_kwh.
                # On a fresh INSERT (no row yet) the value acts as a fallback only.
                # On conflict, only refresh the power/current/voltage metadata.
                conn.execute(
                    """INSERT INTO plug_hourly_energy (
                        id, device_id, hour_bucket, power_avg_w, current_avg_a, voltage_avg_v,
                        energy_kwh, on_minutes, samples_count, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, hour_bucket) DO UPDATE SET
                        power_avg_w = COALESCE(excluded.power_avg_w, plug_hourly_energy.power_avg_w),
                        current_avg_a = COALESCE(excluded.current_avg_a, plug_hourly_energy.current_avg_a),
                        voltage_avg_v = COALESCE(excluded.voltage_avg_v, plug_hourly_energy.voltage_avg_v),
                        samples_count = plug_hourly_energy.samples_count + 1
                    """,
                    (
                        record_id,
                        device_id,
                        hour_bucket,
                        power_avg_w,
                        current_avg_a,
                        voltage_avg_v,
                        round(max(0.0, energy_kwh), 6),
                        max(0, min(60, on_minutes)),
                        max(1, samples_count),
                        source,
                        created_at,
                    ),
                )
            else:
                # "coreiot" rows come from accurate ENERGY-Total delta calculations.
                # Accumulate energy_kwh and override source to mark row as accurate.
                conn.execute(
                    """INSERT INTO plug_hourly_energy (
                        id, device_id, hour_bucket, power_avg_w, current_avg_a, voltage_avg_v,
                        energy_kwh, on_minutes, samples_count, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, hour_bucket) DO UPDATE SET
                        energy_kwh = plug_hourly_energy.energy_kwh + excluded.energy_kwh,
                        power_avg_w = COALESCE(excluded.power_avg_w, plug_hourly_energy.power_avg_w),
                        current_avg_a = COALESCE(excluded.current_avg_a, plug_hourly_energy.current_avg_a),
                        voltage_avg_v = COALESCE(excluded.voltage_avg_v, plug_hourly_energy.voltage_avg_v),
                        on_minutes = MIN(60, plug_hourly_energy.on_minutes + excluded.on_minutes),
                        samples_count = plug_hourly_energy.samples_count + excluded.samples_count,
                        source = excluded.source
                    """,
                    (
                        record_id,
                        device_id,
                        hour_bucket,
                        power_avg_w,
                        current_avg_a,
                        voltage_avg_v,
                        round(max(0.0, energy_kwh), 6),
                        max(0, min(60, on_minutes)),
                        max(1, samples_count),
                        source,
                        created_at,
                    ),
                )
            conn.commit()


def list_plug_hourly_energy(start_iso: str | None = None, end_iso: str | None = None, device_id: str | None = None) -> list[dict]:
    query = "SELECT * FROM plug_hourly_energy WHERE 1 = 1"
    params: list = []
    if start_iso:
        query += " AND hour_bucket >= ?"
        params.append(start_iso)
    if end_iso:
        query += " AND hour_bucket <= ?"
        params.append(end_iso)
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    query += " ORDER BY hour_bucket ASC"

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_plug_consumption_totals(start_iso: str, end_iso: str) -> list[dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT device_id,
                      SUM(energy_kwh) AS total_kwh,
                      AVG(power_avg_w) AS avg_power_w,
                      SUM(on_minutes) AS total_on_minutes,
                      COUNT(*) AS hour_count
               FROM plug_hourly_energy
               WHERE hour_bucket >= ? AND hour_bucket <= ?
               GROUP BY device_id
               ORDER BY total_kwh DESC""",
            (start_iso, end_iso),
        )
        return [dict(row) for row in cur.fetchall()]


def get_device_hourly_average(device_id: str, lookback_days: int = 14) -> dict[int, float]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT CAST(strftime('%H', hour_bucket) AS INTEGER) AS hour_of_day,
                      AVG(energy_kwh) AS avg_kwh
               FROM plug_hourly_energy
               WHERE device_id = ?
                 AND hour_bucket >= datetime('now', ?)
               GROUP BY hour_of_day""",
            (device_id, f"-{lookback_days} days"),
        )
        return {int(row["hour_of_day"]): float(row["avg_kwh"] or 0) for row in cur.fetchall()}


def get_device_daily_runtime_average(device_id: str, lookback_days: int = 14) -> dict:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT AVG(daily_kwh) AS avg_daily_kwh,
                      AVG(active_hours) AS avg_active_hours
               FROM (
                    SELECT DATE(hour_bucket) AS day_key,
                           SUM(energy_kwh) AS daily_kwh,
                           SUM(CASE WHEN energy_kwh > 0.001 THEN 1 ELSE 0 END) AS active_hours
                    FROM plug_hourly_energy
                    WHERE device_id = ?
                      AND hour_bucket >= datetime('now', ?)
                    GROUP BY DATE(hour_bucket)
               )""",
            (device_id, f"-{lookback_days} days"),
        )
        row = cur.fetchone()
        return {
            "avg_daily_kwh": float(row["avg_daily_kwh"] or 0),
            "avg_active_hours": float(row["avg_active_hours"] or 0),
        }


def get_current_energy_budget_profile(month_key: str | None = None) -> dict | None:
    if month_key is None:
        month_key = datetime.now().strftime("%Y-%m")
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM energy_budget_profiles WHERE month_key = ? LIMIT 1",
            (month_key,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_energy_budget_profiles() -> list[dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM energy_budget_profiles ORDER BY month_key DESC")
        return [dict(row) for row in cur.fetchall()]


def upsert_energy_budget_profile(
    month_key: str,
    target_bill_vnd: float,
    warning_threshold_percent: float = 0.9,
    optimization_mode: str = "manual",
    auto_apply_recommendations: bool = False,
) -> dict:
    now = datetime.now().isoformat()
    existing = get_current_energy_budget_profile(month_key)
    profile_id = existing["id"] if existing else str(uuid.uuid4())

    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO energy_budget_profiles (
                    id, month_key, target_bill_vnd, warning_threshold_percent,
                    optimization_mode, auto_apply_recommendations, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(month_key) DO UPDATE SET
                    target_bill_vnd = excluded.target_bill_vnd,
                    warning_threshold_percent = excluded.warning_threshold_percent,
                    optimization_mode = excluded.optimization_mode,
                    auto_apply_recommendations = excluded.auto_apply_recommendations,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_id,
                    month_key,
                    target_bill_vnd,
                    warning_threshold_percent,
                    optimization_mode,
                    1 if auto_apply_recommendations else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
    return get_current_energy_budget_profile(month_key)


def update_energy_budget_analysis(
    month_key: str,
    current_spent_vnd: float,
    current_consumed_kwh: float,
    latest_forecast_bill_vnd: float,
    latest_forecast_kwh_month: float,
    target_kwh_month: float | None = None,
):
    with lock:
        with _connect() as conn:
            conn.execute(
                """UPDATE energy_budget_profiles
                SET current_spent_vnd = ?,
                    current_consumed_kwh = ?,
                    latest_forecast_bill_vnd = ?,
                    latest_forecast_kwh_month = ?,
                    target_kwh_month = ?,
                    updated_at = ?
                WHERE month_key = ?""",
                (
                    current_spent_vnd,
                    current_consumed_kwh,
                    latest_forecast_bill_vnd,
                    latest_forecast_kwh_month,
                    target_kwh_month,
                    datetime.now().isoformat(),
                    month_key,
                ),
            )
            conn.commit()


def get_device_usage_preferences() -> list[dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM device_usage_preferences ORDER BY priority, device_name_snapshot")
        rows = cur.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            for key in (
                "allowed_days_json",
                "allowed_time_windows_json",
                "blocked_time_windows_json",
                "preferred_time_windows_json",
            ):
                item[key] = json.loads(item[key]) if item.get(key) else None
            results.append(item)
        return results


def get_device_usage_preference(device_id: str) -> dict | None:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM device_usage_preferences WHERE device_id = ?", (device_id,))
        row = cur.fetchone()
        if not row:
            return None
        item = dict(row)
        for key in (
            "allowed_days_json",
            "allowed_time_windows_json",
            "blocked_time_windows_json",
            "preferred_time_windows_json",
        ):
            item[key] = json.loads(item[key]) if item.get(key) else None
        return item


def upsert_device_usage_preference(device_id: str, payload: dict) -> dict:
    existing = get_device_usage_preference(device_id)
    pref_id = existing["id"] if existing else str(uuid.uuid4())
    now = datetime.now().isoformat()

    defaults = {
        "device_name_snapshot": payload.get("deviceNameSnapshot"),
        "room_name_snapshot": payload.get("roomNameSnapshot"),
        "priority": payload.get("priority", existing["priority"] if existing else "medium"),
        "auto_controllable": 1 if payload.get("autoControllable", existing["auto_controllable"] if existing else False) else 0,
        "required_daily_runtime_minutes": int(payload.get("requiredDailyRuntimeMinutes", existing["required_daily_runtime_minutes"] if existing else 0) or 0),
        "min_runtime_block_minutes": int(payload.get("minRuntimeBlockMinutes", existing["min_runtime_block_minutes"] if existing else 15) or 15),
        "max_runtime_block_minutes": payload.get("maxRuntimeBlockMinutes", existing["max_runtime_block_minutes"] if existing else None),
        "min_off_block_minutes": int(payload.get("minOffBlockMinutes", existing["min_off_block_minutes"] if existing else 0) or 0),
        "allowed_days_json": json.dumps(payload.get("allowedDays", existing["allowed_days_json"] if existing else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])),
        "allowed_time_windows_json": json.dumps(payload.get("allowedTimeWindows", existing["allowed_time_windows_json"] if existing else None)),
        "blocked_time_windows_json": json.dumps(payload.get("blockedTimeWindows", existing["blocked_time_windows_json"] if existing else None)),
        "preferred_time_windows_json": json.dumps(payload.get("preferredTimeWindows", existing["preferred_time_windows_json"] if existing else None)),
        "avoid_peak_hours": 1 if payload.get("avoidPeakHours", existing["avoid_peak_hours"] if existing else False) else 0,
        "comfort_weight": float(payload.get("comfortWeight", existing["comfort_weight"] if existing else 0.5) or 0.5),
        "saving_weight": float(payload.get("savingWeight", existing["saving_weight"] if existing else 0.5) or 0.5),
        "hard_must_run": 1 if payload.get("hardMustRun", existing["hard_must_run"] if existing else False) else 0,
        "estimated_power_watts": payload.get("estimatedPowerWatts", existing["estimated_power_watts"] if existing else None),
        "standby_power_watts": payload.get("standbyPowerWatts", existing["standby_power_watts"] if existing else None),
    }

    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO device_usage_preferences (
                    id, device_id, device_name_snapshot, room_name_snapshot, priority,
                    auto_controllable, required_daily_runtime_minutes, min_runtime_block_minutes,
                    max_runtime_block_minutes, min_off_block_minutes, allowed_days_json,
                    allowed_time_windows_json, blocked_time_windows_json, preferred_time_windows_json,
                    avoid_peak_hours, comfort_weight, saving_weight, hard_must_run,
                    estimated_power_watts, standby_power_watts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    device_name_snapshot = excluded.device_name_snapshot,
                    room_name_snapshot = excluded.room_name_snapshot,
                    priority = excluded.priority,
                    auto_controllable = excluded.auto_controllable,
                    required_daily_runtime_minutes = excluded.required_daily_runtime_minutes,
                    min_runtime_block_minutes = excluded.min_runtime_block_minutes,
                    max_runtime_block_minutes = excluded.max_runtime_block_minutes,
                    min_off_block_minutes = excluded.min_off_block_minutes,
                    allowed_days_json = excluded.allowed_days_json,
                    allowed_time_windows_json = excluded.allowed_time_windows_json,
                    blocked_time_windows_json = excluded.blocked_time_windows_json,
                    preferred_time_windows_json = excluded.preferred_time_windows_json,
                    avoid_peak_hours = excluded.avoid_peak_hours,
                    comfort_weight = excluded.comfort_weight,
                    saving_weight = excluded.saving_weight,
                    hard_must_run = excluded.hard_must_run,
                    estimated_power_watts = excluded.estimated_power_watts,
                    standby_power_watts = excluded.standby_power_watts,
                    updated_at = excluded.updated_at
                """,
                (
                    pref_id,
                    device_id,
                    defaults["device_name_snapshot"],
                    defaults["room_name_snapshot"],
                    defaults["priority"],
                    defaults["auto_controllable"],
                    defaults["required_daily_runtime_minutes"],
                    defaults["min_runtime_block_minutes"],
                    defaults["max_runtime_block_minutes"],
                    defaults["min_off_block_minutes"],
                    defaults["allowed_days_json"],
                    defaults["allowed_time_windows_json"],
                    defaults["blocked_time_windows_json"],
                    defaults["preferred_time_windows_json"],
                    defaults["avoid_peak_hours"],
                    defaults["comfort_weight"],
                    defaults["saving_weight"],
                    defaults["hard_must_run"],
                    defaults["estimated_power_watts"],
                    defaults["standby_power_watts"],
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
            conn.commit()
    return get_device_usage_preference(device_id)


def create_default_preferences_for_devices(devices: list[dict]) -> list[dict]:
    created = []
    for device in devices:
        device_id = device.get("id")
        if not device_id:
            continue
        if get_device_usage_preference(device_id):
            continue

        telemetry = device.get("telemetry", {})
        metadata = device.get("metadata", {})
        created.append(
            upsert_device_usage_preference(
                device_id,
                {
                    "deviceNameSnapshot": metadata.get("name") or device.get("name") or device_id,
                    "roomNameSnapshot": metadata.get("location") or device.get("location"),
                    "priority": "medium",
                    "autoControllable": False,
                    "requiredDailyRuntimeMinutes": 60,
                    "minRuntimeBlockMinutes": 30,
                    "minOffBlockMinutes": 15,
                    "allowedDays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    "allowedTimeWindows": None,
                    "blockedTimeWindows": None,
                    "preferredTimeWindows": None,
                    "avoidPeakHours": False,
                    "comfortWeight": 0.5,
                    "savingWeight": 0.5,
                    "hardMustRun": False,
                    "estimatedPowerWatts": float(telemetry.get("ENERGY-Power") or 0) or None,
                },
            )
        )
    return created


def create_recommendation_run(
    budget_profile_id: str,
    month_key: str,
    planning_horizon_days: int,
    strategy: str,
    baseline_forecast_bill_vnd: float,
    baseline_forecast_kwh: float,
    required_bill_reduction_vnd: float,
    required_kwh_reduction: float,
    summary: dict,
    generated_by: str = "system",
    run_type: str = "manual",
) -> dict:
    run_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO budget_recommendation_runs (
                    id, budget_profile_id, month_key, generated_at, generated_by, run_type,
                    planning_horizon_days, strategy, baseline_forecast_bill_vnd,
                    baseline_forecast_kwh, required_bill_reduction_vnd, required_kwh_reduction,
                    summary_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    budget_profile_id,
                    month_key,
                    now,
                    generated_by,
                    run_type,
                    planning_horizon_days,
                    strategy,
                    baseline_forecast_bill_vnd,
                    baseline_forecast_kwh,
                    required_bill_reduction_vnd,
                    required_kwh_reduction,
                    json.dumps(summary, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
    return get_recommendation_run(run_id)


def update_recommendation_run(run_id: str, **fields) -> dict | None:
    allowed = {
        "optimized_forecast_bill_vnd",
        "optimized_forecast_kwh",
        "achieved_kwh_reduction_estimate",
        "status",
        "summary_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_recommendation_run(run_id)

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
    params = list(updates.values()) + [run_id]

    with lock:
        with _connect() as conn:
            conn.execute(f"UPDATE budget_recommendation_runs SET {set_clause} WHERE id = ?", params)
            conn.commit()
    return get_recommendation_run(run_id)


def get_recommendation_run(run_id: str) -> dict | None:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM budget_recommendation_runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        item = dict(row)
        item["summary"] = json.loads(item["summary_json"]) if item.get("summary_json") else None
        return item


def list_recommendation_runs(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM budget_recommendation_runs ORDER BY generated_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item["summary_json"]) if item.get("summary_json") else None
            items.append(item)
        return items


def add_recommendation_action(run_id: str, payload: dict) -> dict:
    action_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO recommendation_actions (
                    id, run_id, device_id, action_type, proposed_action,
                    proposed_start, proposed_end, proposed_duration_minutes,
                    estimated_energy_saved_kwh, estimated_cost_saved_vnd,
                    comfort_impact_score, saving_score, confidence_score,
                    priority_score, reason_code, reason_text, approval_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    action_id,
                    run_id,
                    payload["device_id"],
                    payload["action_type"],
                    payload["proposed_action"],
                    payload["proposed_start"],
                    payload.get("proposed_end"),
                    payload.get("proposed_duration_minutes", 0),
                    payload.get("estimated_energy_saved_kwh", 0),
                    payload.get("estimated_cost_saved_vnd", 0),
                    payload.get("comfort_impact_score", 0),
                    payload.get("saving_score", 0),
                    payload.get("confidence_score", 0.5),
                    payload.get("priority_score", 0),
                    payload.get("reason_code", "budget_control"),
                    payload.get("reason_text"),
                    payload.get("approval_status", "pending"),
                    now,
                    now,
                ),
            )
            conn.commit()
    return get_recommendation_action(action_id)


def get_recommendation_action(action_id: str) -> dict | None:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM recommendation_actions WHERE id = ?", (action_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_recommendation_actions(run_id: str) -> list[dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM recommendation_actions WHERE run_id = ? ORDER BY priority_score DESC, estimated_cost_saved_vnd DESC",
            (run_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def update_recommendation_action(action_id: str, **fields) -> dict | None:
    allowed = {"approval_status", "mapped_schedule_id", "updated_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
    params = list(updates.values()) + [action_id]
    with lock:
        with _connect() as conn:
            conn.execute(f"UPDATE recommendation_actions SET {set_clause} WHERE id = ?", params)
            conn.commit()
    return get_recommendation_action(action_id)


def log_schedule_execution(
    schedule_id: str | None,
    source_run_id: str | None,
    device_id: str,
    planned_action: str,
    planned_at: str,
    execution_status: str,
    executed_action: str | None = None,
    executed_at: str | None = None,
    failure_reason: str | None = None,
    actual_power_before_w: float | None = None,
    actual_power_after_w: float | None = None,
    actual_current_before_a: float | None = None,
    actual_current_after_a: float | None = None,
):
    log_id = str(uuid.uuid4())
    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO schedule_execution_log (
                    id, schedule_id, source_run_id, device_id, planned_action,
                    executed_action, planned_at, executed_at, execution_status,
                    failure_reason, actual_power_before_w, actual_power_after_w,
                    actual_current_before_a, actual_current_after_a, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log_id,
                    schedule_id,
                    source_run_id,
                    device_id,
                    planned_action,
                    executed_action,
                    planned_at,
                    executed_at,
                    execution_status,
                    failure_reason,
                    actual_power_before_w,
                    actual_power_after_w,
                    actual_current_before_a,
                    actual_current_after_a,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()


# === SCHEDULE FUNCTIONS ===

def create_schedule(
    name: str,
    target_id: str,
    action: str,
    time: str,
    days: list,
    enabled: bool = True,
    run_once: bool = False,
    source: str = "manual",
    source_run_id: str | None = None,
    approval_status: str = "manual",
    execution_priority: int = 100,
    expires_at: str | None = None,
    metadata: dict | None = None,
) -> dict:
    schedule_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    days_json = json.dumps(days)
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

    with lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO schedules (
                    id, name, target_id, action, time, days, enabled, run_once,
                    source, source_run_id, approval_status, execution_priority,
                    expires_at, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    schedule_id,
                    name,
                    target_id,
                    action,
                    time,
                    days_json,
                    1 if enabled else 0,
                    1 if run_once else 0,
                    source,
                    source_run_id,
                    approval_status,
                    execution_priority,
                    expires_at,
                    metadata_json,
                    created_at,
                ),
            )
            conn.commit()

    return get_schedule_by_id(schedule_id)


def get_all_schedules() -> list:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        return [_row_to_schedule(row) for row in cur.fetchall()]


def get_schedule_by_id(schedule_id: str) -> dict | None:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        row = cur.fetchone()
        return _row_to_schedule(row) if row else None


def update_schedule(
    schedule_id: str,
    name: str = None,
    target_id: str = None,
    action: str = None,
    time: str = None,
    days: list = None,
    enabled: bool = None,
    run_once: bool = None,
    approval_status: str = None,
    expires_at: str = None,
    metadata: dict | None = None,
) -> dict | None:
    with lock:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None

            new_name = name if name is not None else row["name"]
            new_target_id = target_id if target_id is not None else row["target_id"]
            new_action = action if action is not None else row["action"]
            new_time = time if time is not None else row["time"]
            new_days = json.dumps(days) if days is not None else row["days"]
            new_enabled = (1 if enabled else 0) if enabled is not None else row["enabled"]
            new_run_once = (1 if run_once else 0) if run_once is not None else (row["run_once"] if "run_once" in row.keys() else 0)
            new_approval_status = approval_status if approval_status is not None else row["approval_status"]
            new_expires_at = expires_at if expires_at is not None else row["expires_at"]
            new_metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else row["metadata_json"]
            updated_at = datetime.now().isoformat()

            cur.execute(
                """UPDATE schedules
                SET name = ?, target_id = ?, action = ?, time = ?, days = ?, enabled = ?, run_once = ?,
                    approval_status = ?, expires_at = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?""",
                (
                    new_name,
                    new_target_id,
                    new_action,
                    new_time,
                    new_days,
                    new_enabled,
                    new_run_once,
                    new_approval_status,
                    new_expires_at,
                    new_metadata_json,
                    updated_at,
                    schedule_id,
                ),
            )
            conn.commit()

    return get_schedule_by_id(schedule_id)


def delete_schedule(schedule_id: str) -> bool:
    with lock:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cur.rowcount > 0


def get_enabled_schedules() -> list:
    now = datetime.now()
    allowed_status = {"manual", "approved", "auto_approved"}
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM schedules WHERE enabled = 1 ORDER BY execution_priority ASC, created_at DESC")
        rows = cur.fetchall()
        schedules = []
        for row in rows:
            schedule = _row_to_schedule(row)
            if schedule["approvalStatus"] not in allowed_status:
                continue
            expires_at = schedule.get("expiresAt")
            if expires_at:
                try:
                    if datetime.fromisoformat(expires_at) < now:
                        continue
                except ValueError:
                    pass
            schedules.append(schedule)
        return schedules


init_db()