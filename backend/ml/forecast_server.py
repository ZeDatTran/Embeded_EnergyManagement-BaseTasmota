import asyncio
import websockets
import json
import pandas as pd
import numpy as np
import joblib
from pathlib import Path

try:
    from .ensemble_model import ModelEnsemble
except ImportError:
    from ensemble_model import ModelEnsemble


ROOT_DIR = Path(__file__).resolve().parent.parent
ENSEMBLE_PATH = ROOT_DIR / "ensemble_model.pkl"
SCALER_PATH = ROOT_DIR / "scaler.pkl"

# --- Tải các mô hình và preprocessors ---
try:
    ensemble_model = joblib.load(ENSEMBLE_PATH)
    scaler = joblib.load(SCALER_PATH)
except FileNotFoundError:
    print("Lỗi: Vui lòng chạy 'python -m ml.train_forecast_models' trước.")
    exit()

print("Đã tải Ensemble Model và Scaler.")

# Tên các cột (giống hệt lúc train)
FEATURES = ['hour', 'dayofweek', 'month', 'is_weekend',
            'kwh_lag_24h', 'kwh_lag_48h', 'kwh_lag_168h',
            'kwh_rolling_mean_24h']
TARGET = 'kwh_hour'

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
        temp_features = {
            'hour': ts.hour, 
            'dayofweek': ts.dayofweek, 
            'month': ts.month,
            'is_weekend': int(ts.dayofweek >= 5), 
        }
        
        try:
            lag_24 = ts - pd.Timedelta(hours=24)
            lag_48 = ts - pd.Timedelta(hours=48)
            lag_168 = ts - pd.Timedelta(hours=168)
            
            def get_lag_value(time_point, default_val):
                if time_point in forecast_df.index:
                    return forecast_df.loc[time_point][TARGET]
                return default_val

            last_known = forecast_df.iloc[-1][TARGET]

            temp_features['kwh_lag_24h'] = get_lag_value(lag_24, last_known)
            temp_features['kwh_lag_48h'] = get_lag_value(lag_48, last_known)
            temp_features['kwh_lag_168h'] = get_lag_value(lag_168, last_known)
            
            start_rolling = ts - pd.Timedelta(hours=48)
            end_rolling = ts - pd.Timedelta(hours=25)
            rolling_data = forecast_df.loc[forecast_df.index.intersection(pd.date_range(start_rolling, end_rolling, freq='h'))][TARGET]
            
            if len(rolling_data) > 0:
                temp_features['kwh_rolling_mean_24h'] = rolling_data.mean()
            else:
                temp_features['kwh_rolling_mean_24h'] = last_known

        except Exception as e:
            temp_features['kwh_lag_24h'] = forecast_df.iloc[-1][TARGET]
            temp_features['kwh_lag_48h'] = forecast_df.iloc[-1][TARGET]
            temp_features['kwh_lag_168h'] = forecast_df.iloc[-1][TARGET]
            temp_features['kwh_rolling_mean_24h'] = forecast_df.iloc[-1][TARGET]
        
        features_row_df = pd.DataFrame([temp_features], columns=FEATURES).fillna(0)
        scaled_features = scaler.transform(features_row_df)
        
        prediction, details = ensemble_model.predict_conservative(scaled_features)
        
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
    server = await websockets.serve(
        receive_data, 
        "0.0.0.0", 
        8080,
        ping_interval=20,
        ping_timeout=60,
        close_timeout=10
    )
    print("Forecast Server running on port 8080 (Conservative Strategy)")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())