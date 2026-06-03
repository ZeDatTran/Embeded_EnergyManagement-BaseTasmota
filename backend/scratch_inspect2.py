import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from db_connection import get_db

db = get_db()
print("Hourly_kwh docs:", db.hourly_kwh.count_documents({}))
hourly_global = db.hourly_kwh.find_one()
print("Hourly Global Example:", hourly_global)

# Check user_forecasts total
print("User Forecasts docs:", db.user_forecasts.count_documents({}))
user_f = db.user_forecasts.find_one()
if user_f:
    print("User ID with forecast:", user_f["user_id"])
