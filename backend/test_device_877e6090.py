#!/usr/bin/env python3
"""
Test script to debug specific device (877e6090)
"""
import requests
import json
from datetime import datetime

API_URL = "http://localhost:5000"
# Testing the actual problematic device from conversation history
DEVICE_ID = "877e6090-1ae7-11f1-8e7d-45cdb4e6c818"

def test_device():
    """Fetch device data for debugging"""  
    print(f"\nTesting PROBLEMATIC DEVICE: {DEVICE_ID}")
    print("="*60)
    
    for period in ["day", "week", "month"]:
        url = f"{API_URL}/device/{DEVICE_ID}/history"
        params = {"period": period}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                history = data.get("history", [])
                total_energy = sum(float(p.get("energy", 0.0)) for p in history)
                print(f"\n{period.upper()}: {len(history)} points, Total={total_energy:.3f} kWh")
                
                if history:
                    # Show actual values
                    print(f"  First 3 entries:")
                    for p in history[:3]:
                        print(f"    {p.get('timestamp')}: {p.get('energy', 0.0):.3f} kWh")
                    
                    if len(history) > 6:
                        print(f"  ...")
                    
                    print(f"  Last 3 entries:")
                    for p in history[-3:]:
                        print(f"    {p.get('timestamp')}: {p.get('energy', 0.0):.3f} kWh")
            else:
                print(f"✗ Error: {data.get('message')}")
        except Exception as e:
            print(f"✗ Exception: {e}")

if __name__ == "__main__":
    print(f"Testing Device: {DEVICE_ID}")
    print(f"API: {API_URL}")
    test_device()
