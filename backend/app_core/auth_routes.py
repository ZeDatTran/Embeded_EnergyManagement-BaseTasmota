"""Authentication API routes — register, login, current user."""
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

from database import (
    create_user,
    find_user_by_email,
    find_user_by_username,
    find_user_by_id,
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
