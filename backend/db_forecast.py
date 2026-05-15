from datetime import datetime
from db_connection import get_db

def save_user_forecast(user_id, forecast_data):
    """Save or update the latest forecast result for a specific user."""
    db = get_db()
    forecast_data["user_id"] = user_id
    forecast_data["updated_at"] = datetime.utcnow()
    
    db.user_forecasts.update_one(
        {"user_id": user_id},
        {"$set": forecast_data},
        upsert=True
    )

def get_user_forecast(user_id):
    """Retrieve the latest forecast result for a specific user."""
    db = get_db()
    return db.user_forecasts.find_one({"user_id": user_id})
