import sys
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from db_connection import get_db

db = get_db()
forecast = db.user_forecasts.find_one()
if not forecast or "PredictedHourlyDetails" not in forecast:
    print("No predictions found")
    sys.exit()

predictions = forecast["PredictedHourlyDetails"]

# Fetch actual from plug_hourly_energy
actuals = db.plug_hourly_energy.find()
actual_by_hour = {}
for doc in actuals:
    hr = doc["hour_bucket"]
    actual_by_hour[hr] = actual_by_hour.get(hr, 0) + doc.get("energy_kwh", 0)

print("Predictions length:", len(predictions))
print("Actuals length:", len(actual_by_hour))

matched = 0
for hr, pred_dict in predictions.items():
    if hr in actual_by_hour:
        matched += 1
        print(f"[{hr}] Actual: {actual_by_hour[hr]:.4f} - Pred: {pred_dict}")
    else:
        # Just to see some mismatch
        pass

print("Matched hours:", matched)

# Also check hourly_kwh
actual_hourly = db.hourly_kwh.find()
hourly_kwh_dict = {doc["timestamp"]: doc["kwh"] for doc in actual_hourly}
matched_hourly = 0
print("\nComparing with hourly_kwh:")
for hr, pred_dict in predictions.items():
    if hr in hourly_kwh_dict:
        matched_hourly += 1
        print(f"[{hr}] Actual: {hourly_kwh_dict[hr]:.4f} - Pred: {pred_dict}")
        
print("Matched hours (hourly_kwh):", matched_hourly)
