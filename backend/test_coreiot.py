import requests
import os
from dotenv import load_dotenv

load_dotenv()
jwt = os.getenv('JWT_TOKEN')
url = 'https://app.coreiot.io/api/auth/user'
headers = {'X-Authorization': f'Bearer {jwt}', 'Accept': 'application/json'}

print('Đang kiểm tra kết nối tới CoreIoT (https://app.coreiot.io)...')
try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f'HTTP Status: {resp.status_code}')
    if resp.status_code == 200:
        print('Kết nối thành công. Token còn hợp lệ.')
        user_info = resp.json()
        print(f'User Email: {user_info.get("email")}')
    elif resp.status_code == 401:
        print('Lỗi 401: Token đã hết hạn (Expired) hoặc không hợp lệ.')
        print(resp.text)
    else:
        print(f'Lỗi khác: {resp.text}')
except Exception as e:
    print('Lỗi kết nối (Network Error):', e)
