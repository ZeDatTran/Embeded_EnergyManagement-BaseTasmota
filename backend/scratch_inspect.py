import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database import get_user_forecast
from db_core import list_plug_hourly_energy
from db_connection import get_db

db = get_db()
forecast = db.user_forecasts.find_one()
if forecast:
    print("Forecast Keys:", forecast.keys())
    if "PredictedHourlyDetails" in forecast:
        details = forecast["PredictedHourlyDetails"]
        print("Sample Details:", list(details.items())[:3])
    else:
        print("No PredictedHourlyDetails")
else:
    print("No forecast found.")

hourly = db.plug_hourly_energy.find_one()
print("Hourly example:", hourly)
