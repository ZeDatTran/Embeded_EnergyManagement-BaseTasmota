import requests
import time

url = 'http://127.0.0.1:5000/api/chat'
headers = {'Content-Type': 'application/json'}
payload = {'message': 'Bật tất cả thiết bị'}

print('Gửi câu hỏi tới Chatbot: "Bật tất cả thiết bị"')
start_time = time.time()

try:
    response = requests.post(url, headers=headers, json=payload, timeout=15)
    end_time = time.time()
    
    print(f'Mã trạng thái HTTP: {response.status_code}')
    print(f'Thời gian phản hồi tổng cộng (API Response Time): {end_time - start_time:.3f} giây')
    
    if response.status_code == 200:
        data = response.json()
        print('\nNội dung Chatbot trả về:')
        print(data.get('reply', 'Không có nội dung trả lời'))
    else:
        print('Lỗi:', response.text)
except Exception as e:
    print('Lỗi kết nối tới Backend:', e)
