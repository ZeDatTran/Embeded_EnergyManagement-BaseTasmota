import asyncio
import websockets
import json
import pandas as pd
import numpy as np
import joblib
import os
import signal
from pathlib import Path

try:
    from .ensemble_model_improved import ImprovedModelEnsemble
except ImportError:
    from ensemble_model_improved import ImprovedModelEnsemble


ROOT_DIR = Path(__file__).resolve().parent.parent
ENSEMBLE_PATH = ROOT_DIR / "ensemble_model_improved.pkl"
SCALER_PATH = ROOT_DIR / "scaler_improved.pkl"

# --- Tải model/scaler ---
try:
    scaler = joblib.load(SCALER_PATH)
    ensemble_model = ImprovedModelEnsemble(use_improved=True)
except FileNotFoundError:
    print("Lỗi: thiếu improved artifacts. Vui lòng chạy 'python -m ml.train_improved_models' trước.")
    exit()

print("Đã tải Improved Ensemble Model và scaler_improved.pkl.")

# Tên các cột (giống hệt lúc train)
IMPROVED_FEATURES = [
    'hour', 'dayofweek', 'month', 'is_weekend', 'quarter', 'is_holiday_period',
    'kwh_lag_1h', 'kwh_lag_24h', 'kwh_lag_48h', 'kwh_lag_168h', 'kwh_lag_336h',
    'kwh_rolling_mean_6h', 'kwh_rolling_std_6h', 'kwh_rolling_min_6h', 'kwh_rolling_max_6h',
    'kwh_rolling_mean_24h', 'kwh_rolling_std_24h', 'kwh_rolling_min_24h', 'kwh_rolling_max_24h',
    'kwh_rolling_mean_48h', 'kwh_rolling_std_48h', 'kwh_rolling_min_48h', 'kwh_rolling_max_48h',
    'kwh_trend_24h', 'kwh_trend_168h', 'hour_kwh_interaction', 'daytype_kwh_interaction'
]
FEATURES = IMPROVED_FEATURES
TARGET = 'kwh_hour'


def _build_improved_features(forecast_df: pd.DataFrame, ts: pd.Timestamp) -> dict:
    last_known = float(forecast_df.iloc[-1][TARGET])

    def get_lag(hours: int, default_val: float) -> float:
        t = ts - pd.Timedelta(hours=hours)
        if t in forecast_df.index:
            return float(forecast_df.loc[t][TARGET])
        return default_val

    def rolling_stat(hours_back_start: int, hours_back_end: int, stat: str, default_val: float) -> float:
        start = ts - pd.Timedelta(hours=hours_back_start)
        end = ts - pd.Timedelta(hours=hours_back_end)
        idx = pd.date_range(start, end, freq='h')
        values = forecast_df.loc[forecast_df.index.intersection(idx)][TARGET]
        if len(values) == 0:
            return default_val
        if stat == 'mean':
            return float(values.mean())
        if stat == 'std':
            return float(values.std()) if len(values) > 1 else 0.0
        if stat == 'min':
            return float(values.min())
        if stat == 'max':
            return float(values.max())
        return default_val

    lag_1 = get_lag(1, last_known)
    lag_24 = get_lag(24, last_known)
    lag_48 = get_lag(48, lag_24)
    lag_168 = get_lag(168, lag_48)
    lag_336 = get_lag(336, lag_168)

    rolling_mean_6 = rolling_stat(30, 25, 'mean', lag_24)
    rolling_std_6 = rolling_stat(30, 25, 'std', 0.0)
    rolling_min_6 = rolling_stat(30, 25, 'min', lag_24)
    rolling_max_6 = rolling_stat(30, 25, 'max', lag_24)

    rolling_mean_24 = rolling_stat(48, 25, 'mean', lag_24)
    rolling_std_24 = rolling_stat(48, 25, 'std', 0.0)
    rolling_min_24 = rolling_stat(48, 25, 'min', lag_24)
    rolling_max_24 = rolling_stat(48, 25, 'max', lag_24)

    rolling_mean_48 = rolling_stat(72, 25, 'mean', lag_24)
    rolling_std_48 = rolling_stat(72, 25, 'std', 0.0)
    rolling_min_48 = rolling_stat(72, 25, 'min', lag_24)
    rolling_max_48 = rolling_stat(72, 25, 'max', lag_24)

    trend_24 = (lag_24 - lag_48) / (lag_48 + 0.01)
    trend_168 = (lag_168 - lag_336) / (lag_336 + 0.01)

    return {
        'hour': ts.hour,
        'dayofweek': ts.dayofweek,
        'month': ts.month,
        'is_weekend': int(ts.dayofweek >= 5),
        'quarter': ((ts.month - 1) // 3) + 1,
        'is_holiday_period': int(ts.month in [1, 12]),
        'kwh_lag_1h': lag_1,
        'kwh_lag_24h': lag_24,
        'kwh_lag_48h': lag_48,
        'kwh_lag_168h': lag_168,
        'kwh_lag_336h': lag_336,
        'kwh_rolling_mean_6h': rolling_mean_6,
        'kwh_rolling_std_6h': rolling_std_6,
        'kwh_rolling_min_6h': rolling_min_6,
        'kwh_rolling_max_6h': rolling_max_6,
        'kwh_rolling_mean_24h': rolling_mean_24,
        'kwh_rolling_std_24h': rolling_std_24,
        'kwh_rolling_min_24h': rolling_min_24,
        'kwh_rolling_max_24h': rolling_max_24,
        'kwh_rolling_mean_48h': rolling_mean_48,
        'kwh_rolling_std_48h': rolling_std_48,
        'kwh_rolling_min_48h': rolling_min_48,
        'kwh_rolling_max_48h': rolling_max_48,
        'kwh_trend_24h': trend_24,
        'kwh_trend_168h': trend_168,
        'hour_kwh_interaction': ts.hour * lag_24,
        'daytype_kwh_interaction': int(ts.dayofweek >= 5) * lag_24,
    }

# --- Hàm tính tiền điện ---
def calculate_vietnam_electricity_bill(total_kwh):
    tiers = [
        (100, 1984),   # Bậc 1
        (100, 2050),   # Bậc 2
        (200, 2380),   # Bậc 3
        (200, 2998),   # Bậc 4
        (200, 3350),   # Bậc 5
        (float('inf'), 3460)  # Bậc 6
    ]
    
    bill = 0
    kwh_remaining = total_kwh
    
    for tier_limit, price in tiers:
        if kwh_remaining <= 0:
            break
        kwh_in_tier = min(kwh_remaining, tier_limit)
        bill += kwh_in_tier * price
        kwh_remaining -= kwh_in_tier
    
    return bill * 1.08  # VAT 8%

# --- Hàm dự báo ---
async def forecast_with_ensemble(history_df):
    history_df.sort_index(inplace=True)
    start_time = history_df.index.max()
    end_of_month = (start_time + pd.offsets.MonthEnd(0)).floor('h') 
    
    if start_time >= end_of_month:
        return 0, {}, {} 
        
    future_timestamps = pd.date_range(start=start_time + pd.Timedelta(hours=1), 
                                      end=end_of_month, freq='h')
    
    forecast_df = history_df[[TARGET]].copy()
    hourly_predictions = [] 
    hourly_details = {} 

    for ts in future_timestamps:
        try:
            temp_features = _build_improved_features(forecast_df, ts)
        except Exception:
            last_known = float(forecast_df.iloc[-1][TARGET])
            temp_features = {k: 0.0 for k in FEATURES}
            if 'hour' in temp_features:
                temp_features['hour'] = float(ts.hour)
            if 'dayofweek' in temp_features:
                temp_features['dayofweek'] = float(ts.dayofweek)
            if 'month' in temp_features:
                temp_features['month'] = float(ts.month)
            if 'is_weekend' in temp_features:
                temp_features['is_weekend'] = float(int(ts.dayofweek >= 5))
            for key in ['kwh_lag_1h', 'kwh_lag_24h', 'kwh_lag_48h', 'kwh_lag_168h', 'kwh_lag_336h', 'kwh_rolling_mean_24h']:
                if key in temp_features:
                    temp_features[key] = last_known
        
        features_row_df = pd.DataFrame([temp_features], columns=FEATURES).fillna(0)
        scaled_features = scaler.transform(features_row_df)

        result = ensemble_model.predict_with_confidence(scaled_features)
        prediction = float(result["ensemble_prediction"])
        details = result.get("individual_predictions", {})
        
        hourly_predictions.append(prediction)
        hourly_details[ts.isoformat()] = details
        
        new_row = pd.DataFrame({TARGET: [prediction]}, index=[ts])
        forecast_df = pd.concat([forecast_df, new_row])

    total_kwh_forecasted = sum(hourly_predictions)
    return total_kwh_forecasted, hourly_predictions, hourly_details

# --- Xử lý WebSocket ---
async def receive_data(websocket):
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"Received Request: {data.get('Type')}") 

                if data.get("Type") == "PredictToEndOfMonth":
                    history_raw = data["History"]
                    kwh_consumed_this_month = float(data["ConsumedThisMonth"])
                    
                    if not history_raw:
                        print("Cảnh báo: Không có dữ liệu lịch sử.")
                        history_df = pd.DataFrame(columns=[TARGET])
                    else:
                        history_df = pd.DataFrame.from_dict(history_raw, orient='index', columns=[TARGET])
                        history_df.index = pd.to_datetime(history_df.index)
                        history_df.sort_index(inplace=True)

                    if history_df.empty:
                         await websocket.send(json.dumps({"Error": "Empty history data"}))
                         await websocket.close()
                         return

                    total_kwh_forecasted, hourly_preds, hourly_details = await forecast_with_ensemble(history_df)
                    
                    total_monthly_kwh = kwh_consumed_this_month + total_kwh_forecasted
                    final_bill_vnd = calculate_vietnam_electricity_bill(total_monthly_kwh)
                    
                    response = {
                        "PredictedBillVND": round(final_bill_vnd),
                        "TotalKwhForecasted": round(total_kwh_forecasted, 2),
                        "TotalKwhMonth": round(total_monthly_kwh, 2),
                        "HourlyPredictions": hourly_preds,
                        "PredictedHourlyDetails": hourly_details 
                    }
                    await websocket.send(json.dumps(response))
                    
                    print(f"--> SENT FORECAST: {response['TotalKwhMonth']} kWh | Bill: {response['PredictedBillVND']:,} VND")
                    
                    # Đóng connection sau khi gửi response
                    await websocket.close()
                    return

                elif data.get("Type") == "Feedback":
                    predicted_details_all = data["PredictedDetails"]
                    actual_kwh_all = data["ActualKwh"]
                    
                    updated_count = 0
                    for timestamp, actual_value in actual_kwh_all.items():
                        if timestamp in predicted_details_all:
                            predicted_details_hour = predicted_details_all[timestamp]
                            if hasattr(ensemble_model, "update_scores"):
                                ensemble_model.update_scores(predicted_details_hour, float(actual_value))
                                updated_count += 1

                    if updated_count > 0:
                        joblib.dump(ensemble_model, ENSEMBLE_PATH)
                        print(f"--> MODEL UPDATED: {updated_count} points feedback processed.")
                    
                    await websocket.send(json.dumps({"Status": f"Feedback received, {updated_count} points updated."}))
                    
                    # Đóng connection sau feedback
                    await websocket.close()
                    return

                else:
                    print("Unknown message type.")

            except Exception as e:
                print(f"Error processing message: {e}")
                
    except Exception as e:
        # Bỏ qua lỗi keepalive ping timeout
        if "keepalive ping timeout" not in str(e).lower():
            print(f"WebSocket error: {e}")

async def main():
    try:
        port = int(os.getenv("FORECAST_SERVER_PORT", "8080"))
    except ValueError:
        port = 8080

    try:
        server = await websockets.serve(
            receive_data,
            "0.0.0.0",
            port,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10
        )
    except OSError as e:
        if getattr(e, "errno", None) == 10048:
            print(f"Lỗi: cổng {port} đang được sử dụng. Hãy tắt tiến trình đang chiếm cổng hoặc đổi FORECAST_SERVER_PORT.")
            return
        raise

    print(f"Forecast Server running on port {port} (Improved Model Only)")

    stop_event = asyncio.Event()

    def _request_shutdown(signum, _frame):
        sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
        print(f"Shutdown signal received: {sig_name}")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_shutdown)
        except Exception:
            pass

    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, _request_shutdown)
        except Exception:
            pass

    try:
        await stop_event.wait()
    finally:
        server.close()
        await server.wait_closed()
        print(f"Forecast Server on port {port} has stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # The signal handler triggers graceful shutdown; this keeps exit clean.
        pass