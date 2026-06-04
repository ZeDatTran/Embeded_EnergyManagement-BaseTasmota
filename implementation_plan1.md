# Kế hoạch Triển khai: Xác thực Gmail, Khôi phục mật khẩu và Gửi cảnh báo quá tải qua Gmail

Kế hoạch này tích hợp các tính năng liên quan đến email vào hệ thống Smart Home, bao gồm:
1. **Xác thực Email (Gmail Verification)**: Gửi mã OTP 6 chữ số tới Gmail của người dùng để kích hoạt trạng thái xác thực.
2. **Khôi phục mật khẩu (Password Recovery)**: Gửi mã reset mật khẩu tới Gmail khi người dùng yêu cầu, cho phép cập nhật lại mật khẩu mới.
3. **Cảnh báo quá tải qua Gmail (Email Alerts)**: Tự động gửi email cảnh báo chi tiết khi thiết bị tự động tắt do dòng điện vượt quá ngưỡng giới hạn (DANGER threshold).

---

## 🛠 Giải pháp Kỹ thuật (Technical Design)

### 1. Cấu hình SMTP & Gửi Email (`app_core/email_utils.py`)
*   Sử dụng thư viện chuẩn `smtplib` và `email` trong Python.
*   Cấu hình thông qua biến môi trường trong tệp `.env`:
    *   `SMTP_HOST` (Mặc định: `smtp.gmail.com`)
    *   `SMTP_PORT` (Mặc định: `587` cho TLS hoặc `465` cho SSL)
    *   `SMTP_USER` (Tài khoản gửi)
    *   `SMTP_PASS` (Mật khẩu ứng dụng - App Password)
    *   `SMTP_FROM` (Tên hiển thị người gửi)
*   **Cơ chế dự phòng (Simulated Fallback)**: Nếu không cấu hình các biến SMTP, hệ thống sẽ in nội dung email ra console/file logs thay vì báo lỗi crash. Điều này đảm bảo quá trình phát triển không bị gián đoạn.

### 2. Thiết kế Cơ sở dữ liệu (MongoDB Users Schema)
Cập nhật collection `users` bằng cách bổ sung các trường sau:
*   `email_verified` (boolean, mặc định `False`): Trạng thái xác thực email.
*   `verification_code` (string, mặc định `None`): Mã OTP xác thực hiện tại.
*   `verification_code_expires_at` (string ISO, mặc định `None`): Thời gian hết hạn của OTP xác thực (10 phút).
*   `reset_code` (string, mặc định `None`): Mã OTP khôi phục mật khẩu.
*   `reset_code_expires_at` (string ISO, mặc định `None`): Thời gian hết hạn của OTP khôi phục (10 phút).

Chúng ta sẽ chỉnh sửa danh sách `allowed` trong [db_users.py](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/backend/db_users.py) để cho phép cập nhật các trường này.

### 3. Thiết kế Các Endpoint API Backend (`app_core/auth_routes.py`)
Bổ sung các endpoints sau:
*   `POST /api/auth/send-verification`: (Yêu cầu Token) Tạo và gửi OTP 6 chữ số tới Gmail của tài khoản đang đăng nhập.
*   `POST /api/auth/verify-email`: (Yêu cầu Token) Nhận mã OTP và cập nhật `email_verified = True`.
*   `POST /api/auth/forgot-password`: (Công khai) Nhận `email`, kiểm tra sự tồn tại của tài khoản, tạo mã OTP khôi phục mật khẩu và gửi email.
*   `POST /api/auth/reset-password`: (Công khai) Nhận `email`, `code` và `new_password`. Nếu mã hợp lệ và chưa hết hạn, cập nhật mật khẩu mới (hash qua `generate_password_hash`).

### 4. Logic Gửi Cảnh báo Thiết bị tắt do Vượt ngưỡng (`app_core/workers.py`)
*   Trong hàm xử lý WebSocket của CoreIoT, khi dòng điện đo được từ thiết bị (`ENERGY-Current`) vượt quá ngưỡng (`threshold`):
    1.  Hệ thống thực hiện RPC tắt thiết bị.
    2.  Hệ thống lấy thông tin tài khoản qua `device_user_id` để lấy `email`.
    3.  Gửi email cảnh báo mềm với nội dung chi tiết: Tên thiết bị, Dòng điện đo được, Ngưỡng tối đa, và Thời gian ngắt điện.
*   **Cơ chế chống spam (Spam Prevention / Rate Limiting)**: Sử dụng một cache tạm `last_email_sent_at` theo định dạng `device_id -> timestamp` để giới hạn tần suất gửi email cảnh báo quá tải tối đa **1 lần mỗi 5 phút** cho mỗi thiết bị.

### 5. Giao diện Người dùng (Frontend React/Next.js)
*   **Khôi phục Mật khẩu**:
    *   Tạo trang [forgot-password/page.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/app/%28auth%29/forgot-password/page.tsx) với giao diện Glassmorphic đồng bộ. Trang này chứa luồng 2 bước: Nhập email để nhận OTP -> Nhập mã OTP và mật khẩu mới.
    *   Liên kết "Quên mật khẩu?" trên trang Đăng nhập.
*   **Trạng thái Xác thực Email**:
    *   Trên trang [profile/page.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/app/%28dashboard%29/profile/page.tsx), hiển thị badge trạng thái email "Đã xác thực" (màu xanh) hoặc "Chưa xác thực" (màu đỏ).
    *   Nếu chưa xác thực, hiển thị nút "Xác thực ngay" mở Dialog (Modal) nhập mã OTP. Người dùng có thể yêu cầu gửi mã mới và nhập mã để xác thực tài khoản trực tiếp.

---

## 📂 Các Tệp Tin Thay đổi (Proposed Changes)

### Backend (Python)

#### [MODIFY] [db_users.py](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/backend/db_users.py)
*   Cập nhật hàm `create_user` để thêm trường `email_verified=False` mặc định.
*   Thêm các trường mới vào tập hợp `allowed` trong hàm `update_user`.

#### [NEW] [email_utils.py](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/backend/app_core/email_utils.py)
*   Tạo module gửi email qua SMTP và có tính năng fallback in ra log.
*   Thiết kế giao diện template HTML cho 3 loại email: Xác thực, Khôi phục mật khẩu, Cảnh báo quá tải.

#### [MODIFY] [auth_routes.py](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/backend/app_core/auth_routes.py)
*   Tích hợp các endpoints `/api/auth/send-verification`, `/api/auth/verify-email`, `/api/auth/forgot-password`, `/api/auth/reset-password`.
*   Cập nhật hàm `_sanitise_user` để ẩn mã code và hiển thị `email_verified`.

#### [MODIFY] [workers.py](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/backend/app_core/workers.py)
*   Tích hợp logic gửi email cảnh báo quá tải khi thiết bị tự động ngắt điện.
*   Thêm cơ chế kiểm soát spam (5 phút/email/thiết bị).

---

### Frontend (Next.js & TypeScript)

#### [MODIFY] [auth-api.ts](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/lib/auth-api.ts)
*   Cập nhật interface `AuthUser` thêm trường `email_verified: boolean`.
*   Thêm các hàm gọi API: `sendVerificationCode`, `verifyEmail`, `forgotPassword`, `resetPassword`.

#### [MODIFY] [login/page.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/app/%28auth%29/login/page.tsx)
*   Thêm liên kết dẫn tới trang khôi phục mật khẩu `/forgot-password`.

#### [NEW] [forgot-password/page.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/app/%28auth%29/forgot-password/page.tsx)
*   Tạo trang nhập email, nhận mã khôi phục và đặt mật khẩu mới với hiệu ứng kính mờ và hoạt ảnh sang trọng.

#### [MODIFY] [profile/page.tsx](file:///d:/talieu/hk252/TOTNGHIEP/Doan1/frontend/app/%28dashboard%29/profile/page.tsx)
*   Thêm hiển thị badge trạng thái xác thực email.
*   Bổ sung Modal/Dialog yêu cầu gửi OTP và nhập OTP trực tiếp để hoàn thành xác thực.

---

## 🧪 Kế hoạch Xác minh & Kiểm thử (Verification Plan)

### Kiểm thử Tự động & Unit (Backend & Mail Logs)
*   Chạy backend và kiểm tra các log email khi thực hiện các yêu cầu mà không cấu hình SMTP để kiểm tra tính năng fallback.
*   Kiểm tra tính hợp lệ của mã OTP hết hạn.

### Kiểm thử Thủ công (Manual Flow)
1.  **Xác thực Email**:
    *   Đăng nhập vào một tài khoản chưa xác thực -> vào trang hồ sơ (Profile) -> bấm "Xác thực ngay".
    *   Xác nhận log in ra mã OTP (hoặc nhận email thực tế nếu cấu hình).
    *   Nhập mã OTP đúng -> tài khoản cập nhật thành "Đã xác thực" thành công.
    *   Nhập mã OTP hết hạn/sai -> báo lỗi tương ứng.
2.  **Khôi phục Mật khẩu**:
    *   Vào trang `/login` -> bấm "Quên mật khẩu?" -> chuyển hướng tới `/forgot-password`.
    *   Nhập email -> bấm "Gửi mã xác nhận".
    *   Nhập mã reset và mật khẩu mới -> đổi mật khẩu thành công và chuyển hướng về đăng nhập.
3.  **Cảnh báo Quá tải**:
    *   Kích hoạt thiết bị chạy dòng điện vượt ngưỡng cài đặt (ví dụ: mô phỏng gửi dữ liệu đo được > ngưỡng thiết lập).
    *   Xác nhận thiết bị tự động chuyển sang trạng thái "OFF" (ngắt điện).
    *   Xác nhận email cảnh báo quá tải được gửi đi (hoặc in log) với các thông tin chi tiết.
    *   Mô phỏng vượt ngưỡng tiếp theo trong vòng dưới 5 phút, xác nhận KHÔNG có email cảnh báo spam được gửi liên tục.
