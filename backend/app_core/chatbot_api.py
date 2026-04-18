"""
chatbot_api.py — Gemini-powered AI Chatbot for Smart Energy Dashboard.

Architecture:
  POST /api/chat  →  Flask route  →  GeminiEnergyAgent  →  Tool calls  →  CoreIoT API / local data
  
The agent is equipped with four tools that map to the existing API surface:
  • list_devices       – list all registered CB devices and their power state
  • control_device     – toggle any device on/off by name/id
  • get_energy_summary – daily or monthly kWh + bill in VND
  • get_device_telemetry – live Voltage / Current / Power for a specific device
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import Blueprint, jsonify, request
from dotenv import load_dotenv

load_dotenv()

def _shared():
    from app_core import shared as _s
    return _s

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-genai not installed. Chat endpoint will return 503. Run: pip install google-genai")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM_PROMPT = """Bạn là **Energy AI** — trợ lý thông minh tích hợp sẵn trong hệ thống giám sát điện năng Smart Home.
Nhiệm vụ của bạn:
1. **Điều khiển thiết bị**: Hiểu câu nói tự nhiên của người dùng để bật/tắt thiết bị qua hàm `control_device`.
2. **Phân tích tiêu thụ điện**: Cung cấp số kWh và chi phí tiền điện VNĐ theo ngày/tháng.
3. **Tra cứu thông số thời gian thực**: Hiển thị điện áp, dòng điện, công suất tức thời.
4. **Tư vấn tiết kiệm điện**: Đưa ra gợi ý thực tế dựa trên dữ liệu hiện tại.

Quy tắc:
- Luôn trả lời bằng **tiếng Việt** trừ khi người dùng hỏi bằng tiếng Anh.
- Khi điều khiển thiết bị, hãy xác nhận rõ tên thiết bị và hành động đã thực hiện.
- Số liệu tiền điện dùng biểu giá lũy tiến của EVN Việt Nam (đã bao gồm VAT 8%).
- Nếu không tìm thấy thiết bị, hãy liệt kê danh sách thiết bị hiện có và hỏi lại.
- Giữ câu trả lời súc tích, rõ ràng. Dùng emoji ✅ ⚡ 💡 🔌 cho sinh động.
"""

def _build_tools() -> list:
    """Build tool list using google.genai types (called lazily after import check)."""
    return [
        genai_types.Tool(
            function_declarations=[
                genai_types.FunctionDeclaration(
                    name="list_devices",
                    description=(
                        "Lấy danh sách tất cả các thiết bị (CB) đã đăng ký trong hệ thống cùng trạng thái "
                        "bật/tắt (POWER) và thông số điện hiện tại. Gọi tool này khi cần biết thiết bị nào "
                        "đang có trong nhà, trạng thái của chúng, hoặc khi cần tìm device_id để điều khiển."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={},
                    ),
                ),
                genai_types.FunctionDeclaration(
                    name="control_device",
                    description=(
                        "Bật hoặc tắt một thiết bị cụ thể. Dùng khi người dùng yêu cầu 'bật', 'tắt', "
                        "'mở', 'đóng' một thiết bị theo tên hoặc vị trí. "
                        "Ưu tiên gọi list_devices trước để xác định đúng device_id."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID của thiết bị (UUID từ CoreIoT).",
                            ),
                            "device_name": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="Tên hiển thị của thiết bị (để xác nhận với người dùng).",
                            ),
                            "action": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["on", "off"],
                                description="'on' để bật, 'off' để tắt thiết bị.",
                            ),
                        },
                        required=["device_id", "action"],
                    ),
                ),
                genai_types.FunctionDeclaration(
                    name="get_energy_summary",
                    description=(
                        "Lấy tổng điện năng tiêu thụ (kWh) và chi phí tiền điện (VNĐ) theo chu kỳ. "
                        "Dùng khi người dùng hỏi về tiền điện, mức tiêu thụ hôm nay/tháng này."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "period": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["day", "month"],
                                description="'day' cho hôm nay, 'month' cho tháng hiện tại.",
                            ),
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID của thiết bị cụ thể. Để trống để lấy tổng toàn hệ thống.",
                            ),
                        },
                        required=["period"],
                    ),
                ),
                genai_types.FunctionDeclaration(
                    name="get_device_telemetry",
                    description=(
                        "Lấy thông số điện tức thời (điện áp V, dòng điện A, công suất W) của một thiết bị. "
                        "Dùng khi người dùng hỏi về điện áp, ampe, watt hiện tại của một thiết bị."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID của thiết bị cần xem thông số.",
                            ),
                            "device_name": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="Tên thiết bị (để hiển thị).",
                            ),
                        },
                        required=["device_id"],
                    ),
                ),
            ]
        )
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Tool executor functions
# ──────────────────────────────────────────────────────────────────────────────

def _tool_list_devices() -> dict[str, Any]:
    """Return all registered CB devices with power state and latest telemetry."""
    s = _shared()
    devices = []
    for device_id, meta in s.CUSTOM_CB_DEVICES.items():
        info = s.latest_data.get(device_id, {})
        telemetry = info.get("telemetry", {})
        attributes = info.get("attributes", {})
        devices.append({
            "device_id": device_id,
            "name": meta.get("name", "Unknown"),
            "location": meta.get("location", "N/A"),
            "power_state": attributes.get("POWER", "N/A"),
            "power_w": telemetry.get("ENERGY-Power", "N/A"),
            "voltage_v": telemetry.get("ENERGY-Voltage", "N/A"),
            "current_a": telemetry.get("ENERGY-Current", "N/A"),
        })
    return {
        "count": len(devices),
        "devices": devices,
        "timestamp": datetime.now().isoformat(),
    }


def _tool_control_device(device_id: str, action: str, device_name: str = "") -> dict[str, Any]:
    """Send RPC on/off command to a device."""
    s = _shared()
    if device_id not in s.CUSTOM_CB_DEVICES:
        return {
            "success": False,
            "message": f"Không tìm thấy thiết bị với ID '{device_id}'. Vui lòng kiểm tra lại.",
        }

    name = device_name or s.CUSTOM_CB_DEVICES[device_id].get("name", device_id)
    success, result = s.send_rpc_to_device(device_id, action)
    if success:
        # Update local cache immediately so subsequent list_devices is consistent.
        if device_id in s.latest_data:
            s.latest_data[device_id].setdefault("attributes", {})["POWER"] = action.upper()
        return {
            "success": True,
            "device_id": device_id,
            "device_name": name,
            "action": action,
            "message": f"Đã {'bật' if action == 'on' else 'tắt'} thiết bị '{name}' thành công.",
        }
    return {
        "success": False,
        "device_id": device_id,
        "device_name": name,
        "message": f"Lỗi khi điều khiển '{name}': {result.get('message', 'Unknown error')}",
    }


def _calculate_vietnam_electricity_bill(total_kwh: float) -> float:
    """Tính tiền điện theo biểu giá lũy tiến EVN (có VAT 8%)."""
    tiers = [
        (100, 1984),
        (100, 2050),
        (200, 2380),
        (200, 2998),
        (200, 3350),
        (float("inf"), 3460),
    ]
    bill = 0.0
    remaining = total_kwh
    for limit, price in tiers:
        if remaining <= 0:
            break
        kwh_in_tier = min(remaining, limit)
        bill += kwh_in_tier * price
        remaining -= kwh_in_tier
    return round(bill * 1.08, 0)


def _tool_get_energy_summary(period: str = "month", device_id: str = "") -> dict[str, Any]:
    """Fetch kWh and VND cost for today or this month."""
    s = _shared()
    base_url = f"{s.CORE_IOT_URL}/api/plugins/telemetry/DEVICE"
    now = datetime.now()

    device_ids = [device_id] if device_id else list(s.CUSTOM_CB_DEVICES.keys())
    if not device_ids:
        device_ids = s.get_devices_from_group()

    total_kwh = 0.0

    if period == "day":
        start_ts = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        end_ts = int(now.timestamp() * 1000)
    else:
        start_ts = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        end_ts = int(now.timestamp() * 1000)

    for did in device_ids:
        try:
            url = f"{base_url}/{did}/values/timeseries"
            params = {
                "keys": "ENERGY-Total",
                "startTs": start_ts,
                "endTs": end_ts,
                "limit": 50000,
                "agg": "NONE",
                "interval": 0,
            }
            resp = requests.get(url, headers=s.HEADERS, params=params, timeout=20)
            resp.raise_for_status()
            entries = resp.json().get("ENERGY-Total", [])
            if len(entries) < 2:
                continue
            parsed = sorted(
                [(int(e["ts"]), float(e["value"] or 0)) for e in entries if e.get("ts") and e.get("value")],
                key=lambda x: x[0],
            )
            prev = parsed[0][1]
            for _, cur in parsed[1:]:
                d = cur - prev
                if d > 0:
                    total_kwh += d
                prev = cur
        except Exception as exc:
            logging.warning("Energy summary skipped device %s: %s", did, exc)

    total_kwh = round(max(0.0, total_kwh), 4)
    bill_vnd = _calculate_vietnam_electricity_bill(total_kwh)

    period_label = "hôm nay" if period == "day" else f"tháng {now.month}/{now.year}"
    return {
        "period": period,
        "period_label": period_label,
        "total_kwh": total_kwh,
        "total_cost_vnd": bill_vnd,
        "device_count": len(device_ids),
        "timestamp": now.isoformat(),
    }


def _tool_get_device_telemetry(device_id: str, device_name: str = "") -> dict[str, Any]:
    """Return latest cached telemetry snapshot for a device."""
    s = _shared()
    name = device_name or (s.CUSTOM_CB_DEVICES.get(device_id) or {}).get("name", device_id)
    info = s.latest_data.get(device_id)
    if not info:
        # Try fetching fresh
        s.get_device_telemetry(device_id)
        info = s.latest_data.get(device_id, {})

    telemetry = info.get("telemetry", {})
    attributes = info.get("attributes", {})

    def safe_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "device_id": device_id,
        "device_name": name,
        "power_state": attributes.get("POWER", "N/A"),
        "voltage_v": safe_float(telemetry.get("ENERGY-Voltage")),
        "current_a": safe_float(telemetry.get("ENERGY-Current")),
        "power_w": safe_float(telemetry.get("ENERGY-Power")),
        "energy_total_kwh": safe_float(telemetry.get("ENERGY-Total")),
        "timestamp": datetime.now().isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict) -> str:
    try:
        if name == "list_devices":
            result = _tool_list_devices()
        elif name == "control_device":
            result = _tool_control_device(
                device_id=args["device_id"],
                action=args["action"],
                device_name=args.get("device_name", ""),
            )
        elif name == "get_energy_summary":
            result = _tool_get_energy_summary(
                period=args.get("period", "month"),
                device_id=args.get("device_id", ""),
            )
        elif name == "get_device_telemetry":
            result = _tool_get_device_telemetry(
                device_id=args["device_id"],
                device_name=args.get("device_name", ""),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logging.exception("Tool %s raised an exception: %s", name, exc)
        result = {"error": str(exc)}

    return json.dumps(result, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# Gemini Agent loop (single-turn with multi-step tool use)
# ──────────────────────────────────────────────────────────────────────────────

def _run_gemini_agent(user_message: str, history: list[dict]) -> tuple[str, list[dict]]:
    """
    Run the Gemini agent with agentic tool-use loop.
    Returns (final_text_response, updated_history).
    Uses the new google.genai SDK (replaces deprecated google.generativeai).
    """
    if not GEMINI_AVAILABLE:
        return "Thư viện google-genai chưa được cài đặt. Vui lòng chạy: pip install google-genai", history

    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY chưa được cấu hình trong file .env. Vui lòng thêm key vào file .env.", history

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        tools = _build_tools()
    except Exception as exc:
        logging.error("Failed to init Gemini client: %s", exc)
        return f"Lỗi khởi tạo mô hình AI: {exc}", history

    # Convert persisted history to google.genai Content objects
    gemini_history = [
        genai_types.Content(
            role=msg.get("role", "user"),
            parts=[genai_types.Part.from_text(text=msg.get("content", ""))],
        )
        for msg in history
    ]

    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
    )

    chat = client.chats.create(
        model=GEMINI_MODEL,
        config=config,
        history=gemini_history,
    )

    # Agentic loop
    max_iterations = 6
    iteration = 0
    response = None

    try:
        response = chat.send_message(user_message)
    except Exception as exc:
        logging.error("Gemini API error: %s", exc)
        return f"Lỗi kết nối Gemini API: {exc}", history

    while iteration < max_iterations:
        iteration += 1

        # Check for tool calls in all parts
        tool_calls_found = False
        tool_response_parts: list[genai_types.Part] = []

        for part in response.candidates[0].content.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name:
                tool_calls_found = True
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}
                logging.info("Tool call: %s(%s)", fn_name, fn_args)

                tool_result_json = _dispatch_tool(fn_name, fn_args)
                tool_response_parts.append(
                    genai_types.Part.from_function_response(
                        name=fn_name,
                        response=json.loads(tool_result_json),
                    )
                )

        if not tool_calls_found:
            break

        # Send all tool results back to model in one message
        try:
            response = chat.send_message(tool_response_parts)
        except Exception as exc:
            logging.error("Gemini tool result send error: %s", exc)
            return f"Lỗi xử lý kết quả tool: {exc}", history

    # Extract final text
    final_text = ""
    try:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                final_text += part.text
    except Exception:
        final_text = "Xin lỗi, tôi không thể tạo phản hồi lúc này."

    if not final_text:
        final_text = "Xin lỗi, tôi không thể tạo phản hồi lúc này."

    # Update persistent history (keep last 20 turns to avoid token bloat)
    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "model", "content": final_text},
    ]
    if len(updated_history) > 40:  # 20 turns × 2
        updated_history = updated_history[-40:]

    return final_text, updated_history


# ──────────────────────────────────────────────────────────────────────────────
# Flask Blueprint
# ──────────────────────────────────────────────────────────────────────────────

chatbot_bp = Blueprint("chatbot", __name__)

# In-memory session store: { session_id: [{"role", "content"}, ...] }
_chat_sessions: dict[str, list[dict]] = {}


@chatbot_bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """
    POST /api/chat
    Body: { "message": "...", "session_id": "optional-uuid" }
    Response: { "status": "success", "reply": "...", "session_id": "..." }
    """
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "default").strip()

    if not user_message:
        return jsonify({"status": "error", "message": "Tin nhắn không được để trống."}), 400

    # Retrieve or create session history
    history = _chat_sessions.get(session_id, [])

    try:
        reply, updated_history = _run_gemini_agent(user_message, history)
        _chat_sessions[session_id] = updated_history
        return jsonify({
            "status": "success",
            "reply": reply,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as exc:
        logging.exception("Chat endpoint unhandled error: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@chatbot_bp.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
def clear_session(session_id: str):
    """Clear conversation history for a session."""
    _chat_sessions.pop(session_id, None)
    return jsonify({"status": "success", "message": f"Session '{session_id}' đã được xóa."})


@chatbot_bp.route("/api/chat/status", methods=["GET"])
def chat_status():
    """Health check: confirm Gemini integration is configured."""
    return jsonify({
        "status": "ok",
        "gemini_available": GEMINI_AVAILABLE,
        "gemini_key_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
        "sdk": "google-genai",
        "active_sessions": len(_chat_sessions),
    })
