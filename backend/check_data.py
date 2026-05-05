#!/usr/bin/env python3
"""
Script kiểm tra dữ liệu đã thu thập được (MongoDB version)
Chạy: python check_data.py
"""

import os
import json
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/smart_home")


def get_db():
    client = MongoClient(MONGO_URI)
    return client.get_default_database()


def check_database_exists():
    """Kiểm tra kết nối MongoDB"""
    try:
        db = get_db()
        db.command("ping")
        collections = db.list_collection_names()
        print(f"✅ Kết nối MongoDB thành công: {MONGO_URI}")
        print(f"📦 Số collections: {len(collections)}")
        if collections:
            print(f"   Collections: {', '.join(collections)}")
        return True
    except Exception as e:
        print(f"❌ Không thể kết nối MongoDB: {e}")
        return False


def check_hourly_kwh_data():
    """Kiểm tra dữ liệu trong collection hourly_kwh"""
    print("\n" + "=" * 60)
    print("📊 COLLECTION HOURLY_KWH - Dữ liệu tiêu thụ điện theo giờ")
    print("=" * 60)

    try:
        db = get_db()
        col = db.hourly_kwh
        total = col.count_documents({})
        print(f"\n📈 Tổng số record: {total}")

        if total == 0:
            print("⚠️  KHÔNG có dữ liệu nào!")
            return

        pipeline_range = [
            {"$group": {
                "_id": None,
                "first": {"$min": "$timestamp"},
                "last": {"$max": "$timestamp"},
                "total_kwh": {"$sum": "$kwh"},
            }}
        ]
        result = list(col.aggregate(pipeline_range))
        if result:
            r = result[0]
            print(f"🕐 Thời gian đầu tiên: {r['first']}")
            print(f"🕐 Thời gian mới nhất: {r['last']}")
            print(f"⚡ Tổng điện tiêu thụ: {r['total_kwh']:.2f} kWh")

        print(f"\n📋 10 record MỚI NHẤT:")
        print("-" * 60)
        print(f"{'Thời gian':<20} {'kWh':>10}")
        print("-" * 60)

        docs = col.find().sort("timestamp", -1).limit(10)
        for doc in docs:
            print(f"{doc['timestamp']:<20} {doc['kwh']:>10.4f}")

    except Exception as e:
        print(f"❌ Lỗi: {e}")


def check_training_log():
    """Kiểm tra log huấn luyện model AI"""
    print("\n" + "=" * 60)
    print("🤖 COLLECTION TRAINING_LOG - Lịch sử huấn luyện AI")
    print("=" * 60)

    try:
        db = get_db()
        col = db.training_log
        total = col.count_documents({})
        print(f"\n📈 Tổng số lần train: {total}")

        if total == 0:
            print("⚠️  Chưa có lịch sử train AI")
            return

        print(f"\n📋 5 lần train GẦN NHẤT:")
        print("-" * 80)
        print(f"{'Ngày':<12} {'R2_RF':>8} {'R2_XGB':>8} {'R2_MLP':>8} {'R2_LR':>8} {'Note':<20}")
        print("-" * 80)

        docs = col.find().sort("date", -1).limit(5)
        for doc in docs:
            print(f"{doc.get('date',''):<12} {doc.get('r2_rf',0):>8.4f} {doc.get('r2_xgb',0):>8.4f} "
                  f"{doc.get('r2_mlp',0):>8.4f} {doc.get('r2_lr',0):>8.4f} {doc.get('note',''):<20}")

    except Exception as e:
        print(f"❌ Lỗi: {e}")


def check_schedules():
    """Kiểm tra schedules"""
    print("\n" + "=" * 60)
    print("📅 COLLECTION SCHEDULES")
    print("=" * 60)

    try:
        db = get_db()
        total = db.schedules.count_documents({})
        enabled = db.schedules.count_documents({"enabled": True})
        print(f"\n📈 Tổng: {total} | Đang bật: {enabled}")

        if total > 0:
            print(f"\n📋 5 schedule GẦN NHẤT:")
            docs = db.schedules.find().sort("created_at", -1).limit(5)
            for doc in docs:
                status = "🟢" if doc.get("enabled") else "🔴"
                print(f"  {status} {doc.get('name', 'N/A')} | {doc.get('action', '')} | {doc.get('time', '')} | {doc.get('days', [])}")

    except Exception as e:
        print(f"❌ Lỗi: {e}")


def check_users():
    """Kiểm tra users"""
    print("\n" + "=" * 60)
    print("👤 COLLECTION USERS")
    print("=" * 60)

    try:
        db = get_db()
        total = db.users.count_documents({})
        print(f"\n📈 Tổng số users: {total}")

        if total > 0:
            docs = db.users.find({}, {"password_hash": 0}).sort("created_at", -1).limit(5)
            for doc in docs:
                print(f"  📧 {doc.get('email', 'N/A')} | {doc.get('username', 'N/A')} | Role: {doc.get('role', 'N/A')}")

    except Exception as e:
        print(f"❌ Lỗi: {e}")


def check_forecast_result():
    """Kiểm tra file kết quả dự báo"""
    print("\n" + "=" * 60)
    print("🔮 FILE FORECAST_RESULT.JSON - Kết quả dự báo")
    print("=" * 60)

    if not os.path.exists("forecast_result.json"):
        print("⚠️  File forecast_result.json KHÔNG tồn tại")
        return

    try:
        with open("forecast_result.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"\n✅ File tồn tại")
        print(f"📦 Kích thước: {os.path.getsize('forecast_result.json'):,} bytes")
        print(f"\n📊 KẾT QUẢ DỰ BÁO:")
        print(f"💰 Tiền điện dự kiến: {data.get('PredictedBillVND', 0):,.0f} VNĐ")
        print(f"⚡ Tổng kWh dự báo: {data.get('TotalKwhForecasted', 0):.2f} kWh")
        print(f"⚡ Tổng kWh cả tháng: {data.get('TotalKwhMonth', 0):.2f} kWh")

    except Exception as e:
        print(f"❌ Lỗi đọc file: {e}")


def main():
    print("=" * 60)
    print("🔍 CÔNG CỤ KIỂM TRA DỮ LIỆU - MongoDB")
    print("=" * 60)

    if not check_database_exists():
        print("\n💡 HƯỚNG DẪN:")
        print("1. Đảm bảo MongoDB đang chạy")
        print("2. Kiểm tra MONGO_URI trong file .env")
        return

    check_hourly_kwh_data()
    check_training_log()
    check_schedules()
    check_users()
    check_forecast_result()

    print("\n✅ HOÀN THÀNH KIỂM TRA!")
    print("=" * 60)


if __name__ == "__main__":
    main()