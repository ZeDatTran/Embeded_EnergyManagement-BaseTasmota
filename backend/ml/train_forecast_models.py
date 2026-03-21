import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
import xgboost as xgb
import joblib
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import get_all_history, list_plug_hourly_energy


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "data" / "power_history.db"
UCI_DATA_PATH = ROOT_DIR / "household_power_consumption.txt"
SCALER_PATH = ROOT_DIR / "scaler.pkl"
MODELS_DIR = ROOT_DIR / "models"

load_dotenv(ROOT_DIR / ".env")
CORE_IOT_URL = os.getenv("CORE_IOT_URL", "https://app.coreiot.io")
JWT_TOKEN = os.getenv("JWT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
HEADERS = {"Authorization": f"Bearer {JWT_TOKEN}"} if JWT_TOKEN else {}

def create_features(df):
    df = df.copy()
    df['hour'] = df.index.hour
    df['dayofweek'] = df.index.dayofweek
    df['month'] = df.index.month
    df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)
    df['kwh_lag_24h'] = df['kwh_hour'].shift(24)
    df['kwh_lag_48h'] = df['kwh_hour'].shift(48)
    df['kwh_lag_168h'] = df['kwh_hour'].shift(168)
    df['kwh_rolling_mean_24h'] = df['kwh_hour'].shift(24).rolling(window=24).mean()
    return df.dropna()


def load_personal_history_df() -> pd.DataFrame:
    """Load real hourly history from DB, backfilling from plug_hourly_energy when needed."""
    history = get_all_history()

    # If hourly_kwh is sparse, build per-hour totals from plug telemetry aggregates.
    plug_rows = list_plug_hourly_energy()
    hour_totals: dict[str, float] = {}
    for row in plug_rows:
        hour_bucket = row.get("hour_bucket")
        if not hour_bucket:
            continue
        try:
            kwh_val = float(row.get("energy_kwh") or 0.0)
        except (TypeError, ValueError):
            continue
        hour_totals[hour_bucket] = hour_totals.get(hour_bucket, 0.0) + max(0.0, kwh_val)

    # Prefer plug-aggregated totals when present for the same hour.
    merged_history = dict(history)
    for ts, total_kwh in hour_totals.items():
        merged_history[ts] = round(total_kwh, 6)

    if not merged_history:
        return pd.DataFrame(columns=["kwh_hour"])

    df = pd.DataFrame([{"datetime": k, "kwh_hour": v} for k, v in merged_history.items()])
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"])
    df = df.set_index("datetime").sort_index()
    return df


def fetch_coreiot_history_df(lookback_days: int = 60, chunk_days: int = 7) -> pd.DataFrame:
    """Fetch hourly energy history directly from CoreIoT and aggregate across devices."""
    if not JWT_TOKEN:
        raise RuntimeError("Missing JWT_TOKEN in .env")

    devices_url = f"{CORE_IOT_URL}/api/tenant/devices?pageSize=100&page=0"
    if GROUP_ID:
        devices_url += f"&groupId={GROUP_ID}"

    devices_resp = requests.get(devices_url, headers=HEADERS, timeout=20)
    devices_resp.raise_for_status()
    devices_data = devices_resp.json().get("data", [])
    device_ids = [d.get("id", {}).get("id") for d in devices_data if d.get("id", {}).get("id")]

    if not device_ids:
        return pd.DataFrame(columns=["kwh_hour"])

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=max(1, lookback_days))
    chunk_delta = timedelta(days=max(1, chunk_days))
    power_by_hour: dict[str, float] = {}

    for device_id in device_ids:
        cursor = start_dt
        while cursor < end_dt:
            chunk_end = min(cursor + chunk_delta, end_dt)
            start_ts = int(cursor.timestamp() * 1000)
            end_ts = int(chunk_end.timestamp() * 1000)

            url = f"{CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
            params = {
                "keys": "ENERGY-Power",
                "startTs": start_ts,
                "endTs": end_ts,
                "limit": 10000,
                "agg": "AVG",
                "interval": 3600000,
            }
            resp = requests.get(url, headers=HEADERS, params=params, timeout=25)
            resp.raise_for_status()
            raw = resp.json()

            for entry in raw.get("ENERGY-Power", []):
                ts_ms = entry.get("ts")
                val = entry.get("value")
                if ts_ms is None:
                    continue
                try:
                    power_w = float(val or 0.0)
                except (TypeError, ValueError):
                    continue
                hour_key = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%dT%H:00:00")
                power_by_hour[hour_key] = power_by_hour.get(hour_key, 0.0) + max(0.0, power_w)

            cursor = chunk_end

    if not power_by_hour:
        return pd.DataFrame(columns=["kwh_hour"])

    rows = []
    for hour_key, total_power_w in power_by_hour.items():
        rows.append({"datetime": hour_key, "kwh_hour": round(total_power_w / 1000.0, 6)})

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).set_index("datetime").sort_index()
    return df

def train_all_models(use_personal_data=False, use_coreiot_data=True):
    FEATURES = ['hour','dayofweek','month','is_weekend',
                'kwh_lag_24h','kwh_lag_48h','kwh_lag_168h','kwh_rolling_mean_24h']
    TARGET = 'kwh_hour'

    # Prefer real history from SQLite when requested.
    # Need enough points for lag_168h + rolling_24h and a stable split.
    min_required_hours = 240
    df = pd.DataFrame(columns=["kwh_hour"])

    if use_coreiot_data:
        try:
            lookback_days = int(os.getenv("COREIOT_LOOKBACK_DAYS", "60"))
        except ValueError:
            lookback_days = 60
        try:
            df = fetch_coreiot_history_df(lookback_days=lookback_days, chunk_days=7)
            if len(df) >= min_required_hours:
                print(f"Using CoreIoT data: {len(df)} hourly points")
                use_personal_data = True
            else:
                print(f"CoreIoT data < {min_required_hours} hours -> fallback DB/UCI")
                use_personal_data = False
        except Exception as e:
            print(f"CoreIoT fetch failed -> fallback DB/UCI: {e}")
            use_personal_data = False

    if not use_personal_data and DB_PATH.exists():
        df = load_personal_history_df()
        if len(df) >= min_required_hours:
            print(f"Using personal data from DB: {len(df)} hourly points")
            use_personal_data = True
        else:
            print(f"Personal data < {min_required_hours} hours -> use UCI")
            use_personal_data = False
    else:
        print("No personal DB or disabled → use UCI")
        use_personal_data = False

    if not use_personal_data:
        path = UCI_DATA_PATH
        if not path.exists():
            raise FileNotFoundError("Need household_power_consumption.txt")
        df_raw = pd.read_csv(path, sep=';', na_values=['?'], low_memory=False)
        df_raw['datetime'] = pd.to_datetime(df_raw['Date'] + ' ' + df_raw['Time'], dayfirst=True)
        df_raw = df_raw.set_index('datetime').ffill()
        df_hourly = df_raw['Global_active_power'].astype(float).resample('h').mean()
        df = df_hourly.to_frame(name='kwh_hour')

    df_features = create_features(df)
    X = df_features[FEATURES]
    y = df_features[TARGET]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    joblib.dump(scaler, SCALER_PATH)

    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.1, shuffle=False)
    os.makedirs(MODELS_DIR, exist_ok=True)

    print("\n🔨 Training models...")
    
    # [PRIORITY 1] XGBoost - Tốt nhất cho time series
    print("  [1/4] Training XGBoost...")
    model_xgb = xgb.XGBRegressor(
        n_estimators=300,      # Tăng từ 200
        learning_rate=0.02,    # Giảm để học chậm hơn, chính xác hơn
        max_depth=6,           # Thêm depth
        random_state=42, 
        n_jobs=-1
    )
    model_xgb.fit(X_train, y_train)
    joblib.dump(model_xgb, MODELS_DIR / "model_xgb.pkl")
    
    # [PRIORITY 2] Random Forest - Rất ổn định
    print("  [2/4] Training Random Forest...")
    model_rf = RandomForestRegressor(
        n_estimators=100,      # Tăng từ 50
        max_depth=15,          # Thêm depth
        random_state=42, 
        n_jobs=-1
    )
    model_rf.fit(X_train, y_train)
    joblib.dump(model_rf, MODELS_DIR / "model_rf.pkl")
    
    # [PRIORITY 3] MLP - Có thể học non-linear
    print("  [3/4] Training MLP...")
    model_mlp = MLPRegressor(
        hidden_layer_sizes=(64, 32, 16),  # Thêm layers
        max_iter=300,                      # Tăng iterations
        activation='relu',
        random_state=42,
        early_stopping=True,
        validation_fraction=0.1
    )
    model_mlp.fit(X_train, y_train)
    joblib.dump(model_mlp, MODELS_DIR / "model_mlp.pkl")
    
    

    # Evaluate
    scores = {
        "xgb": round(model_xgb.score(X_test, y_test), 4),
        "rf": round(model_rf.score(X_test, y_test), 4),
        "mlp": round(model_mlp.score(X_test, y_test), 4),
    }

    print(f"\n TRAINING COMPLETE!")
    print(f" R² Scores:")
    print(f"   XGBoost:      {scores['xgb']} ")
    print(f"   RandomForest: {scores['rf']} ")
    print(f"   MLP:          {scores['mlp']} ")
    print(f"\nEnsemble will use: XGBoost + RandomForest (+ MLP if stable)")
    
    return scores

if __name__ == "__main__":
    train_all_models(use_personal_data=True, use_coreiot_data=True)
    print("\n Creating ensemble model...")
    os.system("python -m ml.run_ensemble")