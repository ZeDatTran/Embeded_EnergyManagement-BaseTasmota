import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
import xgboost as xgb
try:
    from catboost import CatBoostRegressor
    HAS_CATBOOST = True
except Exception:
    HAS_CATBOOST = False
import joblib
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import get_all_history, list_plug_hourly_energy

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "data" / "power_history.db"
UCI_DATA_PATH = ROOT_DIR / "household_power_consumption.txt"
SCALER_IMPROVED_PATH = ROOT_DIR / "scaler_improved.pkl"
MODELS_DIR = ROOT_DIR / "models"

load_dotenv(ROOT_DIR / ".env")
CORE_IOT_URL = os.getenv("CORE_IOT_URL", "https://app.coreiot.io")
JWT_TOKEN = os.getenv("JWT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
HEADERS = {"Authorization": f"Bearer {JWT_TOKEN}"} if JWT_TOKEN else {}

def create_advanced_features(df):
    """
    Enhanced feature engineering with more sophisticated time series features
    """
    df = df.copy()

    # ===== EXPLICIT LINEAR TREND LAYER =====
    # Build a deterministic time index and estimate a global linear baseline.
    # The model can then learn deviations from this baseline instead of over-trusting
    # historically high absolute levels.
    df['time_idx'] = np.arange(len(df), dtype=float)
    if len(df) >= 2:
        trend_slope, trend_intercept = np.polyfit(df['time_idx'], df['kwh_hour'].astype(float), 1)
    elif len(df) == 1:
        trend_slope, trend_intercept = 0.0, float(df['kwh_hour'].iloc[0])
    else:
        trend_slope, trend_intercept = 0.0, 0.0

    df['linear_trend'] = trend_slope * df['time_idx'] + trend_intercept
    df['kwh_detrended'] = df['kwh_hour'] - df['linear_trend']
    df['trend_slope'] = trend_slope
    
    # ===== TEMPORAL FEATURES =====
    df['hour'] = df.index.hour
    df['dayofweek'] = df.index.dayofweek
    df['month'] = df.index.month
    df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)
    df['quarter'] = df.index.quarter
    df['is_holiday_period'] = df['month'].isin([1, 12]).astype(int)
    
    # ===== LAG FEATURES (24/48/168/long horizon) =====
    df['kwh_lag_1h'] = df['kwh_hour'].shift(1)
    df['kwh_lag_24h'] = df['kwh_hour'].shift(24)
    df['kwh_lag_48h'] = df['kwh_hour'].shift(48)
    df['kwh_lag_168h'] = df['kwh_hour'].shift(168)  # 1 week
    # Use 2-week lag only when history is long enough; otherwise fallback to 1-week lag.
    long_lag_hours = 336 if len(df) >= 500 else 168
    df['kwh_lag_336h'] = df['kwh_hour'].shift(long_lag_hours)

    # Keep this column usable even with short/sparse histories.
    if df['kwh_lag_336h'].isna().all():
        df['kwh_lag_336h'] = df['kwh_lag_168h']
    
    # ===== ROLLING STATISTICS (NEW) =====
    for window in [6, 24, 48]:
        df[f'kwh_rolling_mean_{window}h'] = df['kwh_hour'].shift(24).rolling(window=window).mean()
        df[f'kwh_rolling_std_{window}h'] = df['kwh_hour'].shift(24).rolling(window=window).std()
        df[f'kwh_rolling_min_{window}h'] = df['kwh_hour'].shift(24).rolling(window=window).min()
        df[f'kwh_rolling_max_{window}h'] = df['kwh_hour'].shift(24).rolling(window=window).max()
    
    # ===== TREND FEATURES (NEW) =====
    df['kwh_trend_24h'] = (df['kwh_hour'].shift(24) - df['kwh_hour'].shift(48)) / (df['kwh_hour'].shift(48) + 0.01)
    df['kwh_trend_168h'] = (df['kwh_lag_168h'] - df['kwh_lag_336h']) / (df['kwh_lag_336h'] + 0.01)

    # ===== DETRENDED FEATURES (NEW) =====
    df['kwh_detrended_lag_24h'] = df['kwh_detrended'].shift(24)
    df['kwh_detrended_lag_168h'] = df['kwh_detrended'].shift(168)
    df['kwh_detrended_roll_mean_24h'] = df['kwh_detrended'].shift(24).rolling(window=24).mean()
    df['kwh_detrended_roll_std_24h'] = df['kwh_detrended'].shift(24).rolling(window=24).std()
    
    # ===== INTERACTION FEATURES (NEW) =====
    df['hour_kwh_interaction'] = df['hour'] * df['kwh_lag_24h']
    df['daytype_kwh_interaction'] = df['is_weekend'] * df['kwh_lag_24h']
    
    return df.dropna()


def fetch_coreiot_history_df(lookback_days: int = 60, chunk_days: int = 7) -> pd.DataFrame:
    """Fetch hourly energy history from CoreIoT"""
    if not JWT_TOKEN:
        print("[WARN] JWT_TOKEN missing - using UCI fallback")
        return pd.DataFrame(columns=["kwh_hour"])

    if not GROUP_ID:
        print("[WARN] GROUP_ID missing - skip tenant-wide fetch and use fallback source")
        return pd.DataFrame(columns=["kwh_hour"])

    try:
        devices_url = f"{CORE_IOT_URL}/api/entityGroup/{GROUP_ID}/entities?pageSize=100&page=0&entityType=DEVICE"
        devices_resp = requests.get(devices_url, headers=HEADERS, timeout=20)
        devices_resp.raise_for_status()
        payload = devices_resp.json()

        if isinstance(payload, dict):
            entities = payload.get("data", [])
        elif isinstance(payload, list):
            entities = payload
        else:
            entities = []

        device_ids = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if isinstance(ent.get("id"), dict):
                dev_id = ent["id"].get("id")
            elif isinstance(ent.get("entityId"), dict):
                dev_id = ent["entityId"].get("id")
            else:
                dev_id = ent.get("id")
            if dev_id:
                device_ids.append(dev_id)

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

    except Exception as e:
        print(f"[WARN] CoreIoT fetch failed: {e}")
        return pd.DataFrame(columns=["kwh_hour"])


def load_data_for_training():
    """Load training data with priority: CoreIoT > Personal DB > UCI"""
    
    min_required_hours = 240
    
    # Try CoreIoT first
    df = pd.DataFrame(columns=["kwh_hour"])
    try:
        lookback_days = int(os.getenv("COREIOT_LOOKBACK_DAYS", "60"))
    except ValueError:
        lookback_days = 60
    
    df = fetch_coreiot_history_df(lookback_days=lookback_days)
    if len(df) >= min_required_hours:
        print(f"[INFO] Using CoreIoT data: {len(df)} hourly points")
        return df
    
    # Try personal DB
    if DB_PATH.exists():
        try:
            history = get_all_history()
            plug_rows = list_plug_hourly_energy()
            
            hour_totals = {}
            for row in plug_rows:
                hour_bucket = row.get("hour_bucket")
                if not hour_bucket:
                    continue
                try:
                    kwh_val = float(row.get("energy_kwh") or 0.0)
                except (TypeError, ValueError):
                    continue
                hour_totals[hour_bucket] = hour_totals.get(hour_bucket, 0.0) + max(0.0, kwh_val)
            
            merged_history = dict(history)
            for ts, total_kwh in hour_totals.items():
                merged_history[ts] = round(total_kwh, 6)
            
            if merged_history:
                df = pd.DataFrame([{"datetime": k, "kwh_hour": v} for k, v in merged_history.items()])
                df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
                df = df.dropna(subset=["datetime"])
                df = df.set_index("datetime").sort_index()
                
                if len(df) >= min_required_hours:
                    print(f"[INFO] Using Personal DB data: {len(df)} hourly points")
                    return df
        except Exception as e:
            print(f"[WARN] Personal DB failed: {e}")
    
    # Fallback to UCI
    print("[INFO] Using UCI dataset (household_power_consumption.txt)")
    path = UCI_DATA_PATH
    if not path.exists():
        raise FileNotFoundError("Need household_power_consumption.txt")
    
    df_raw = pd.read_csv(path, sep=';', na_values=['?'], low_memory=False)
    df_raw['datetime'] = pd.to_datetime(df_raw['Date'] + ' ' + df_raw['Time'], dayfirst=True)
    df_raw = df_raw.set_index('datetime').ffill()
    df_hourly = df_raw['Global_active_power'].astype(float).resample('h').mean()
    df = df_hourly.to_frame(name='kwh_hour')
    
    return df


def train_improved_models():
    """Train improved models with better features and parameters"""
    
    # Load data
    df = load_data_for_training()
    print(f"\n📈 Data shape: {df.shape}")
    total_hours = len(df)
    
    # Create advanced features
    print("\n[STEP] Creating advanced features...")
    df_features = create_advanced_features(df)
    print(f"[OK] Features created. Shape: {df_features.shape}")

    if len(df_features) < 5:
        raise ValueError(
            f"Not enough training samples after feature engineering ({len(df_features)}). "
            "Increase COREIOT_LOOKBACK_DAYS or ensure denser telemetry."
        )
    
    # Define features (exclude target + helper columns that are not available at inference time)
    FEATURES = [
        col for col in df_features.columns
        if col not in {'kwh_hour', 'kwh_detrended'}
    ]
    TARGET = 'kwh_hour'
    
    X = df_features[FEATURES]
    y = df_features[TARGET]
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    # Keep a dedicated scaler for the improved feature set.
    joblib.dump(scaler, SCALER_IMPROVED_PATH)
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.15, shuffle=False
    )
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    print("\n" + "="*60)
    print("TRAINING IMPROVED MODELS WITH ADVANCED FEATURES")
    print("="*60)
    
    scores = {}
    
    # [1] XGBoost - TUNED (with anti-collapse fallback)
    print("\n  [1/3] Training XGBoost (Tuned)...")
    xgb_params_primary = {
        "n_estimators": 400,
        "learning_rate": 0.015,
        "max_depth": 7,
        "min_child_weight": 1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "gamma": 1,
        "reg_alpha": 0.5,
        "reg_lambda": 1,
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": 0,
    }
    model_xgb = xgb.XGBRegressor(**xgb_params_primary)
    model_xgb.fit(X_train, y_train)

    y_pred_xgb_train = model_xgb.predict(X_train)
    y_pred_xgb_test = model_xgb.predict(X_test)
    xgb_train_r2 = r2_score(y_train, y_pred_xgb_train)
    xgb_test_r2 = r2_score(y_test, y_pred_xgb_test)
    xgb_pred_std = float(np.std(y_pred_xgb_test))

    # Auto-retrain if XGBoost collapses to near-constant predictions or severe underfit.
    if xgb_pred_std < 1e-6 or (xgb_train_r2 < 0.1 and xgb_test_r2 < 0.1):
        print("     XGBoost appears underfit/collapsed -> retry with relaxed params...")
        xgb_params_fallback = {
            "n_estimators": 700,
            "learning_rate": 0.03,
            "max_depth": 6,
            "min_child_weight": 1,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "gamma": 0,
            "reg_alpha": 0,
            "reg_lambda": 1,
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
            "random_state": 42,
            "n_jobs": -1,
            "verbosity": 0,
        }
        model_xgb = xgb.XGBRegressor(**xgb_params_fallback)
        model_xgb.fit(X_train, y_train)
        y_pred_xgb_train = model_xgb.predict(X_train)
        y_pred_xgb_test = model_xgb.predict(X_test)
        xgb_train_r2 = r2_score(y_train, y_pred_xgb_train)
        xgb_test_r2 = r2_score(y_test, y_pred_xgb_test)

    joblib.dump(model_xgb, MODELS_DIR / "model_xgb_improved.pkl")
    scores['XGBoost'] = {
        'train': xgb_train_r2,
        'test': xgb_test_r2,
        'rmse': np.sqrt(mean_squared_error(y_test, y_pred_xgb_test))
    }
    print(f"     Train R²: {scores['XGBoost']['train']:.4f} | Test R²: {scores['XGBoost']['test']:.4f}")
    
    # [2] Random Forest - TUNED
    print("  [2/3] Training Random Forest (Tuned)...")
    model_rf = RandomForestRegressor(
        n_estimators=150,      # ⬆️ Increased
        max_depth=18,          # Slightly deeper
        min_samples_split=5,   # NEW
        min_samples_leaf=2,    # NEW
        max_features='sqrt',   # NEW: Feature randomness
        random_state=42,
        n_jobs=-1,
        verbose=0
    )
    model_rf.fit(X_train, y_train)
    joblib.dump(model_rf, MODELS_DIR / "model_rf_improved.pkl")
    y_pred_rf_train = model_rf.predict(X_train)
    y_pred_rf_test = model_rf.predict(X_test)
    scores['RandomForest'] = {
        'train': r2_score(y_train, y_pred_rf_train),
        'test': r2_score(y_test, y_pred_rf_test),
        'rmse': np.sqrt(mean_squared_error(y_test, y_pred_rf_test))
    }
    print(f"     Train R²: {scores['RandomForest']['train']:.4f} | Test R²: {scores['RandomForest']['test']:.4f}")
    
    # [3] CatBoost - robust on small/medium tabular data
    print("  [3/3] Training CatBoost...")
    cat_path = MODELS_DIR / "model_cat_improved.pkl"
    if HAS_CATBOOST:
        try:
            model_cat = CatBoostRegressor(
                iterations=300,
                depth=6,
                learning_rate=0.03,
                loss_function="RMSE",
                random_seed=42,
                verbose=False,
            )
            model_cat.fit(X_train, y_train)
            joblib.dump(model_cat, cat_path)
            y_pred_cat_train = model_cat.predict(X_train)
            y_pred_cat_test = model_cat.predict(X_test)
            scores['CatBoost'] = {
                'train': r2_score(y_train, y_pred_cat_train),
                'test': r2_score(y_test, y_pred_cat_test),
                'rmse': np.sqrt(mean_squared_error(y_test, y_pred_cat_test))
            }
            print(f"     Train R²: {scores['CatBoost']['train']:.4f} | Test R²: {scores['CatBoost']['test']:.4f}")
        except Exception as e:
            if cat_path.exists():
                cat_path.unlink()
            print(f"     Skipped CatBoost: training failed ({e})")
            scores['CatBoost'] = {
                'train': float('nan'),
                'test': float('nan'),
                'rmse': float('nan')
            }
    else:
        if cat_path.exists():
            cat_path.unlink()
        print("     Skipped CatBoost: package not installed.")
        scores['CatBoost'] = {
            'train': float('nan'),
            'test': float('nan'),
            'rmse': float('nan')
        }

    mlp_path = MODELS_DIR / "model_mlp_improved.pkl"
    if mlp_path.exists():
        mlp_path.unlink()
        print("  Removed stale model_mlp_improved.pkl (MLP disabled).")
    
    # Print summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    for model_name, model_scores in scores.items():
        print(f"\n{model_name}:")
        print(f"  Train R²: {model_scores['train']:.4f}")
        print(f"  Test R²:  {model_scores['test']:.4f}")
        print(f"  RMSE:     {model_scores['rmse']:.6f} kWh")
    
    # Feature importance
    print("\n" + "="*60)
    print("TOP 10 MOST IMPORTANT FEATURES")
    print("="*60)
    xgb_importance = pd.DataFrame({
        'feature': FEATURES,
        'importance': model_xgb.feature_importances_
    }).sort_values('importance', ascending=False).head(10)
    
    for idx, row in xgb_importance.iterrows():
        print(f"  {row['feature']:<30} : {row['importance']:.4f}")
    
    print("\n[OK] Improved models saved to " + str(MODELS_DIR))
    print("[OK] This is the production training pipeline.")


if __name__ == "__main__":
    train_improved_models()
