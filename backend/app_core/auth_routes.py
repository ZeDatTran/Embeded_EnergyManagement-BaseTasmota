"""Authentication API routes — register, login, current user."""
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
import random

from app_core.email_utils import (
    send_email,
    get_verification_email_html,
    get_reset_password_email_html,
)

import jwt
from flask import jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

from database import (
    create_user,
    find_user_by_email,
    find_user_by_username,
    find_user_by_id,
    update_user,
    update_last_login,
)

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _create_token(user: dict) -> str:
    """Create a JWT token for a user."""
    payload = {
        "user_id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _get_current_user():
    """Extract and validate JWT from Authorization header.
    Returns (user_dict, None) on success or (None, error_response) on failure.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"status": "error", "message": "Token không hợp lệ"}), 401)

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None, (jsonify({"status": "error", "message": "Token đã hết hạn"}), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify({"status": "error", "message": "Token không hợp lệ"}), 401)

    user = find_user_by_id(payload.get("user_id", ""))
    if user is None:
        return None, (jsonify({"status": "error", "message": "Người dùng không tồn tại"}), 401)
    return user, None


def _sanitise_user(user: dict) -> dict:
    """Return user dict without sensitive fields."""
    safe = dict(user)
    safe.pop("password_hash", None)
    safe.pop("verification_code", None)
    safe.pop("verification_code_expires_at", None)
    safe.pop("reset_code", None)
    safe.pop("reset_code_expires_at", None)
    # Expose group_id at top level for convenience
    coreiot = safe.get("coreiot_config") or {}
    safe["group_id"] = coreiot.get("group_id") or None
    # Ensure email_verified defaults to False if not present
    safe["email_verified"] = user.get("email_verified", False)
    return safe


def register_auth_routes(app):
    """Register all /api/auth/* routes on the Flask app."""

    # ── POST /api/auth/register ───────────────────────────────────────
    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Dữ liệu không hợp lệ"}), 400

        email = (data.get("email") or "").strip().lower()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        full_name = (data.get("full_name") or "").strip()

        # ── Validation ────────────────────────────────────────────────
        errors = []
        if not email or not _EMAIL_RE.match(email):
            errors.append("Email không hợp lệ")
        if not username or len(username) < 3:
            errors.append("Tên đăng nhập phải có ít nhất 3 ký tự")
        if not re.match(r"^[a-zA-Z0-9_]+$", username or ""):
            errors.append("Tên đăng nhập chỉ chứa chữ cái, số và dấu gạch dưới")
        if len(password) < 6:
            errors.append("Mật khẩu phải có ít nhất 6 ký tự")
        if errors:
            return jsonify({"status": "error", "message": "; ".join(errors)}), 400

        # ── Uniqueness check ──────────────────────────────────────────
        if find_user_by_email(email):
            return jsonify({"status": "error", "message": "Email đã được sử dụng"}), 409
        if find_user_by_username(username):
            return jsonify({"status": "error", "message": "Tên đăng nhập đã tồn tại"}), 409

        # ── Create user ───────────────────────────────────────────────
        password_hash = generate_password_hash(password)
        user = create_user(
            email=email,
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            role="user",
        )

        token = _create_token(user)
        update_last_login(user["id"])

        logging.info("New user registered: %s (%s)", username, email)
        return jsonify({
            "status": "success",
            "message": "Đăng ký thành công",
            "token": token,
            "user": _sanitise_user(user),
        }), 201

    # ── POST /api/auth/login ──────────────────────────────────────────
    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Dữ liệu không hợp lệ"}), 400

        identifier = (data.get("identifier") or "").strip()
        password = data.get("password") or ""

        if not identifier or not password:
            return jsonify({"status": "error", "message": "Vui lòng nhập đầy đủ thông tin"}), 400

        # Look up by email first, then by username
        user = find_user_by_email(identifier.lower())
        if user is None:
            user = find_user_by_username(identifier)
        if user is None:
            return jsonify({"status": "error", "message": "Tài khoản không tồn tại"}), 401

        if not user.get("is_active", True):
            return jsonify({"status": "error", "message": "Tài khoản đã bị vô hiệu hóa"}), 403

        if not check_password_hash(user.get("password_hash", ""), password):
            return jsonify({"status": "error", "message": "Mật khẩu không đúng"}), 401

        token = _create_token(user)
        update_last_login(user["id"])

        logging.info("User logged in: %s", user["username"])
        return jsonify({
            "status": "success",
            "message": "Đăng nhập thành công",
            "token": token,
            "user": _sanitise_user(user),
        })

    # ── GET /api/auth/me ──────────────────────────────────────────────
    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        user, err = _get_current_user()
        if err:
            return err
        return jsonify({
            "status": "success",
            "user": _sanitise_user(user),
        })

    # ── PATCH /api/auth/me ────────────────────────────────────────────
    @app.route("/api/auth/me", methods=["PATCH"])
    def auth_update_me():
        """Update current user profile fields (group_id, settings, etc.)."""
        user, err = _get_current_user()
        if err:
            return err

        data = request.get_json(silent=True) or {}

        # Update group_id inside coreiot_config
        if "group_id" in data:
            group_id = (data["group_id"] or "").strip() or None
            current_config = user.get("coreiot_config") or {}
            current_config["group_id"] = group_id
            user = update_user(user["id"], coreiot_config=current_config)

        # Update other allowed top-level fields
        updatable = {k: v for k in ("full_name", "avatar_url", "settings") if (v := data.get(k)) is not None}
        if updatable:
            user = update_user(user["id"], **updatable)

        logging.info("User %s updated profile", user["username"])
        return jsonify({
            "status": "success",
            "message": "Cập nhật thành công",
            "user": _sanitise_user(user),
        })

    # ── POST /api/auth/send-verification ──────────────────────────────
    @app.route("/api/auth/send-verification", methods=["POST"])
    def auth_send_verification():
        user, err = _get_current_user()
        if err:
            return err
        
        email = user.get("email")
        if not email:
            return jsonify({"status": "error", "message": "Người dùng không có địa chỉ email"}), 400

        # Generate a 6-digit verification code
        code = f"{random.randint(100000, 999999)}"
        expires_at = (datetime.now() + timedelta(minutes=10)).isoformat()

        # Save to database
        update_user(
            user["id"],
            verification_code=code,
            verification_code_expires_at=expires_at
        )

        # Send email
        html_content = get_verification_email_html(user.get("full_name") or user["username"], code)
        sent = send_email(email, "Mã xác thực tài khoản Smart Home", html_content)
        
        if not sent:
            return jsonify({"status": "error", "message": "Không thể gửi email xác thực"}), 500

        return jsonify({
            "status": "success",
            "message": f"Mã xác thực đã được gửi tới email {email}"
        })

    # ── POST /api/auth/verify-email ───────────────────────────────────
    @app.route("/api/auth/verify-email", methods=["POST"])
    def auth_verify_email():
        user, err = _get_current_user()
        if err:
            return err
        
        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip()

        if not code:
            return jsonify({"status": "error", "message": "Vui lòng nhập mã xác thực"}), 400

        db_code = user.get("verification_code")
        expires_at = user.get("verification_code_expires_at")
        now = datetime.now().isoformat()

        if not db_code or not expires_at:
            return jsonify({"status": "error", "message": "Yêu cầu mã xác thực mới trước"}), 400

        if db_code != code:
            return jsonify({"status": "error", "message": "Mã xác thực không chính xác"}), 400

        if expires_at < now:
            return jsonify({"status": "error", "message": "Mã xác thực đã hết hạn"}), 400

        # Mark verified and clear code
        user = update_user(
            user["id"],
            email_verified=True,
            verification_code=None,
            verification_code_expires_at=None
        )

        return jsonify({
            "status": "success",
            "message": "Xác thực email thành công",
            "user": _sanitise_user(user)
        })

    # ── POST /api/auth/forgot-password ───────────────────────────────
    @app.route("/api/auth/forgot-password", methods=["POST"])
    def auth_forgot_password():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()

        if not email or not _EMAIL_RE.match(email):
            return jsonify({"status": "error", "message": "Email không hợp lệ"}), 400

        user = find_user_by_email(email)
        if not user:
            return jsonify({"status": "error", "message": "Không tìm thấy tài khoản với email này"}), 404

        # Generate a 6-digit password reset code
        code = f"{random.randint(100000, 999999)}"
        expires_at = (datetime.now() + timedelta(minutes=10)).isoformat()

        # Save to database
        update_user(
            user["id"],
            reset_code=code,
            reset_code_expires_at=expires_at
        )

        # Send email
        html_content = get_reset_password_email_html(user.get("full_name") or user["username"], code)
        sent = send_email(email, "Mã khôi phục mật khẩu Smart Home", html_content)

        if not sent:
            return jsonify({"status": "error", "message": "Không thể gửi email khôi phục mật khẩu"}), 500

        return jsonify({
            "status": "success",
            "message": f"Mã khôi phục đã được gửi tới email {email}"
        })

    # ── POST /api/auth/reset-password ────────────────────────────────
    @app.route("/api/auth/reset-password", methods=["POST"])
    def auth_reset_password():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()
        new_password = data.get("new_password") or ""

        if not email or not code or not new_password:
            return jsonify({"status": "error", "message": "Vui lòng nhập đầy đủ thông tin"}), 400

        if len(new_password) < 6:
            return jsonify({"status": "error", "message": "Mật khẩu mới phải có ít nhất 6 ký tự"}), 400

        user = find_user_by_email(email)
        if not user:
            return jsonify({"status": "error", "message": "Không tìm thấy tài khoản với email này"}), 404

        db_code = user.get("reset_code")
        expires_at = user.get("reset_code_expires_at")
        now = datetime.now().isoformat()

        if not db_code or not expires_at:
            return jsonify({"status": "error", "message": "Yêu cầu mã khôi phục mới trước"}), 400

        if db_code != code:
            return jsonify({"status": "error", "message": "Mã khôi phục không chính xác"}), 400

        if expires_at < now:
            return jsonify({"status": "error", "message": "Mã khôi phục đã hết hạn"}), 400

        # Update password and clear reset code
        password_hash = generate_password_hash(new_password)
        update_user(
            user["id"],
            password_hash=password_hash,
            reset_code=None,
            reset_code_expires_at=None
        )

        return jsonify({
            "status": "success",
            "message": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại."
        })
