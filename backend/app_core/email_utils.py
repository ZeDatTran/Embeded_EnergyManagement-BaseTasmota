import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load SMTP configurations from environment
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an HTML email using SMTP. Falls back to console simulation if SMTP is not configured."""
    if not SMTP_USER or not SMTP_PASS:
        logging.warning("=== [EMAIL SIMULATOR] ===")
        logging.warning("To: %s", to_email)
        logging.warning("Subject: %s", subject)
        logging.warning("SMTP not configured (SMTP_USER/SMTP_PASS are missing in .env). Simulating dispatch...")
        logging.warning("Content:\n%s", html_content)
        logging.warning("=========================")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
        server.quit()
        logging.info("Email sent successfully to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logging.error("Failed to send email to %s: %s", to_email, str(e))
        return False


def get_verification_email_html(username: str, code: str) -> str:
    """Generate HTML template for account verification."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f1f5f9; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 32px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); }}
            .header {{ text-align: center; border-bottom: 1px solid #334155; padding-bottom: 20px; margin-bottom: 24px; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #3b82f6; }}
            .greeting {{ font-size: 18px; margin-bottom: 16px; color: #f8fafc; }}
            .message {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 24px; }}
            .code-container {{ text-align: center; background-color: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin: 24px 0; }}
            .code {{ font-size: 32px; font-weight: bold; color: #10b981; letter-spacing: 6px; font-family: monospace; }}
            .footer {{ font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #334155; padding-top: 20px; margin-top: 32px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">⚡ Smart Home</div>
            </div>
            <div class="greeting">Xin chào {username},</div>
            <div class="message">
                Cảm ơn bạn đã đăng ký sử dụng hệ thống quản lý nhà thông minh Smart Home. 
                Vui lòng sử dụng mã xác thực dưới đây để hoàn tất việc xác thực địa chỉ email của bạn:
            </div>
            <div class="code-container">
                <div class="code">{code}</div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 8px;">Mã xác thực có hiệu lực trong vòng 10 phút.</div>
            </div>
            <div class="message">
                Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email này hoặc liên hệ hỗ trợ nếu nghi ngờ tài khoản bị xâm nhập.
            </div>
            <div class="footer">
                Đây là email tự động từ hệ thống Smart Home. Vui lòng không phản hồi email này.
            </div>
        </div>
    </body>
    </html>
    """


def get_reset_password_email_html(username: str, code: str) -> str:
    """Generate HTML template for password reset."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f1f5f9; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 32px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); }}
            .header {{ text-align: center; border-bottom: 1px solid #334155; padding-bottom: 20px; margin-bottom: 24px; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #3b82f6; }}
            .greeting {{ font-size: 18px; margin-bottom: 16px; color: #f8fafc; }}
            .message {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 24px; }}
            .code-container {{ text-align: center; background-color: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin: 24px 0; }}
            .code {{ font-size: 32px; font-weight: bold; color: #3b82f6; letter-spacing: 6px; font-family: monospace; }}
            .footer {{ font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #334155; padding-top: 20px; margin-top: 32px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">⚡ Smart Home</div>
            </div>
            <div class="greeting">Xin chào {username},</div>
            <div class="message">
                Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản Smart Home liên kết với email này. 
                Hãy sử dụng mã OTP khôi phục dưới đây để tiến hành thiết lập mật khẩu mới:
            </div>
            <div class="code-container">
                <div class="code">{code}</div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 8px;">Mã này có hiệu lực trong vòng 10 phút.</div>
            </div>
            <div class="message" style="color: #f43f5e; font-weight: 500;">
                Lưu ý: Tuyệt đối không chia sẻ mã này với bất kỳ ai để tránh bị mất tài khoản.
            </div>
            <div class="footer">
                Đây là email tự động từ hệ thống Smart Home. Vui lòng không phản hồi email này.
            </div>
        </div>
    </body>
    </html>
    """


def get_overload_alert_email_html(username: str, device_name: str, current: float, threshold: float) -> str:
    """Generate HTML template for device overload auto-shutdown warning."""
    import time
    now_str = time.strftime("%H:%M:%S - %d/%m/%Y")
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f1f5f9; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #1e293b; border: 2px solid #ef4444; border-radius: 16px; padding: 32px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5); }}
            .header {{ text-align: center; border-bottom: 1px solid #ef4444; padding-bottom: 20px; margin-bottom: 24px; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #ef4444; }}
            .greeting {{ font-size: 18px; margin-bottom: 16px; color: #f8fafc; }}
            .message {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 24px; }}
            .details-container {{ background-color: #1a0e0e; border: 1px solid #ef4444; border-radius: 12px; padding: 20px; margin: 24px 0; }}
            .details-row {{ display: flex; justify-content: space-between; border-bottom: 1px solid #2e1818; padding: 8px 0; font-size: 14px; }}
            .details-row:last-child {{ border-bottom: none; }}
            .label {{ color: #94a3b8; font-weight: 500; }}
            .value {{ color: #f1f5f9; font-weight: bold; }}
            .danger-text {{ color: #f43f5e; }}
            .success-text {{ color: #10b981; }}
            .footer {{ font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #334155; padding-top: 20px; margin-top: 32px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">⚠️ CẢNH BÁO QUÁ TẢI THIẾT BỊ</div>
            </div>
            <div class="greeting">Xin chào {username},</div>
            <div class="message">
                Hệ thống Smart Home phát hiện thiết bị của bạn đã vượt quá ngưỡng dòng điện cho phép và đã tự động ngắt điện lập tức để đảm bảo an toàn phòng chống cháy nổ.
            </div>
            <div class="details-container">
                <div style="font-size: 16px; font-weight: bold; color: #f43f5e; margin-bottom: 12px; border-bottom: 1px solid #ef4444; padding-bottom: 6px;">Thông tin chi tiết:</div>
                <div class="details-row">
                    <span class="label">Thiết bị:</span>
                    <span class="value">{device_name}</span>
                </div>
                <div class="details-row">
                    <span class="label">Dòng điện đo được:</span>
                    <span class="value danger-text">{current} A</span>
                </div>
                <div class="details-row">
                    <span class="label">Ngưỡng tối đa thiết lập:</span>
                    <span class="value">{threshold} A</span>
                </div>
                <div class="details-row">
                    <span class="label">Trạng thái hiện tại:</span>
                    <span class="value danger-text">ĐÃ TẮT TỰ ĐỘNG (OFF)</span>
                </div>
                <div class="details-row">
                    <span class="label">Thời gian ngắt điện:</span>
                    <span class="value">{now_str}</span>
                </div>
            </div>
            <div class="message">
                Vui lòng kiểm tra lại thiết bị điện nói trên trước khi bật lại để tránh hư hỏng hoặc sự cố nghiêm trọng hơn.
            </div>
            <div class="footer">
                Đây là cảnh báo tự động từ hệ thống Smart Home. Vui lòng không phản hồi email này.
            </div>
        </div>
    </body>
    </html>
    """
