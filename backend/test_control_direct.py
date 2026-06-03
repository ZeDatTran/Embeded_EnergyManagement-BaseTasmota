import time
import os
import sys

# Add backend to path
sys.path.insert(0, r'd:\talieu\hk252\TOTNGHIEP\Doan1\backend')

from app_core import shared

# Load devices from DB to populate shared.CUSTOM_CB_DEVICES
shared.load_devices_from_db()

device_ids = list(shared.CUSTOM_CB_DEVICES.keys())

if not device_ids:
    print("Không tìm thấy thiết bị nào trong Database cục bộ.")
else:
    device_id = device_ids[0]
    device_name = shared.CUSTOM_CB_DEVICES[device_id].get('name', 'Unknown')
    print(f"Bắt đầu test độ trễ điều khiển trực tiếp trên Backend với thiết bị: {device_name} ({device_id})")
    print(f"Đang gửi lệnh RPC 'ON' tới CoreIoT...")

    start_time = time.time()
    
    # Gửi lệnh điều khiển
    success, result = shared.send_rpc_to_device(device_id, "ON")
    
    end_time = time.time()
    latency = (end_time - start_time) * 1000 # to ms

    print("-" * 50)
    print(f"Trạng thái thành công: {success}")
    print(f"Độ trễ thời gian (Latency): {latency:.2f} ms")
    print(f"Chi tiết phản hồi: {result}")
    
    if "503" in str(result) or not success:
        print("\nLưu ý: Máy chủ CoreIoT hiện đang bị lỗi/bảo trì (503 Service Unavailable) nên lệnh không thể đến ESP32.")
