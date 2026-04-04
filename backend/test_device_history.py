#!/usr/bin/env python3
"""
Test script to debug device history energy calculations
"""
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_URL = "http://localhost:5000"
DEVICE_ID = os.getenv("DEVICE_ID", "93671550-1ae7-11f1-8e7d-45cdb4e6c818")  # From .env
TEST_PERIODS = ["day", "week", "month"]

def test_device_history():
    """Fetch and display device history for testing"""
    for period in TEST_PERIODS:
        print(f"\n{'='*60}")
        print(f"Testing period: {period}")
        print(f"{'='*60}")
        
        url = f"{API_URL}/device/{DEVICE_ID}/history"
        params = {"period": period}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                history = data.get("history", [])
                print(f"✓ Got {len(history)} data points")
                
                if history:
                    # Calculate total energy
                    total_energy = sum(float(p.get("energy", 0.0)) for p in history)
                    print(f"✓ Total energy: {total_energy:.6f} kWh")
                    
                    # Show first 5 points
                    print(f"\nFirst 5 points:")
                    for i, point in enumerate(history[:5]):
                        print(f"  [{i}] {point.get('timestamp')}: energy={point.get('energy', 0.0):.6f} kWh")
                    
                    # Show last 5 points
                    if len(history) > 5:
                        print(f"\nLast 5 points:")
                        for i, point in enumerate(history[-5:], len(history)-5):
                            print(f"  [{i}] {point.get('timestamp')}: energy={point.get('energy', 0.0):.6f} kWh")
            else:
                print(f"✗ API returned error: {data.get('message')}")
        except Exception as e:
            print(f"✗ Error: {e}")

if __name__ == "__main__":
    print(f"Device History Test - {datetime.now().isoformat()}")
    print(f"Testing device: {DEVICE_ID}")
    print(f"API URL: {API_URL}")
    print(f"(Using DEVICE_ID from .env: {os.getenv('DEVICE_ID', 'NOT SET')})")
    
    test_device_history()
    
    print(f"\n{'='*60}")
    print("Test completed. Check backend logs for detailed debug info.")
    print(f"{'='*60}")
