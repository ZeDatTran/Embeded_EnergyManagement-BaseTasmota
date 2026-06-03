import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('JWT_TOKEN')
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {token}',
    'X-Authorization': f'Bearer {token}'
}

# 1. Fetch devices
print("1. Lấy danh sách thiết bị...")
resp = requests.get('http://127.0.0.1:5000/api/devices/cb', headers=headers)
if resp.status_code != 200:
    print("Lỗi khi lấy danh sách thiết bị:", resp.text)
    exit(1)

devices = resp.json().get('data', [])
if not devices:
    print("Không tìm thấy thiết bị nào trong tài khoản của bạn để test.")
    exit(1)

target_device = devices[0]
device_id = target_device['id']
device_name = target_device.get('name', 'Unknown')

print(f"-> Chọn thiết bị: {device_name} ({device_id})")

# 2. Test control ON
url = f'http://127.0.0.1:5000/api/control/{device_id}/on'
print(f"\n2. Bắt đầu test độ trễ điều khiển (Gửi lệnh BẬT)...")

start_time = time.time()
try:
    resp = requests.post(url, headers=headers, timeout=10)
    end_time = time.time()
    
    latency = (end_time - start_time) * 1000 # to milliseconds
    print(f"Mã trạng thái HTTP: {resp.status_code}")
    print(f"Thời gian phản hồi (API Response Latency): {latency:.2f} ms")
    print(f"Kết quả từ máy chủ: {resp.json()}")
    
except Exception as e:
    print("Lỗi kết nối:", e)
