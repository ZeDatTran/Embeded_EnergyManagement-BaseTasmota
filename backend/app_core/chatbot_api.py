# chatbot_api.py — Gemini-powered AI Chatbot for Smart Energy Dashboard.

# Tools available (8 total):
#   • list_devices        – list all CB devices + power state
#   • control_device      – toggle any device on/off
#   • get_energy_summary  – daily or monthly kWh + bill
#   • get_device_telemetry – live V / A / W snapshot
#   • compare_energy      – day vs yesterday | 7-day rolling | month vs last month | between devices | weekend comparison
#   • get_device_ranking  – rank devices by consumption (highest/lowest/all)
#   • get_energy_advice   – full data snapshot for AI-generated saving tips
#   • get_peak_hours      – hourly breakdown for any date, top peak/off-peak hours
# 

from __future__ import annotations

import json
import logging
import os
import time as _time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import Blueprint, jsonify, request
from dotenv import load_dotenv

load_dotenv()

# Lazy import shared to avoid circular deps
def _shared():
    from app_core import shared as _s
    return _s

# Gemini SDK
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-genai not installed. Run: pip install google-genai")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# System Prompt  — critical: force tool usage, never answer from prior knowledge
SYSTEM_PROMPT = """Bạn là **Energy AI** — trợ lý thông minh tích hợp trong hệ thống Smart Home giám sát điện năng.

## Nhiệm vụ:
1. **Điều khiển thiết bị** – bật/tắt theo yêu cầu qua `control_device`.
2. **Phân tích tiêu thụ điện** – kWh và tiền điện VNĐ theo ngày/tháng qua `get_energy_summary`.
3. **Thông số thời gian thực** – điện áp/dòng/công suất qua `get_device_telemetry`.
4. **So sánh năng lượng** – qua `compare_energy` (hôm nay/hôm qua, tháng/tháng trước, giữa thiết bị).
5. **Xếp hạng thiết bị** – thiết bị tiêu thụ nhiều/ít nhất qua `get_device_ranking`.
6. **Lời khuyên tiết kiệm** – phân tích tổng hợp qua `get_energy_advice`.

## LUẬT BẮT BUỘC — TUÂN THỦ TUYỆT ĐỐI:
- ❌ **KHÔNG BAO GIỜ** tự trả lời câu hỏi về dữ liệu điện, thiết bị, hay tiêu thụ từ kiến thức nội tại.
- ✅ **LUÔN LUÔN** gọi tool phù hợp trước, rồi mới trả lời dựa trên kết quả tool trả về.
- Khi người dùng hỏi so sánh ("hôm nay vs hôm qua", "7 ngày qua", "tuần này so tuần trước", "tháng này so tháng trước", "thiết bị nào dùng nhiều", "cuối tuần"): GỌI `compare_energy` hoặc `get_device_ranking` NGAY.
- Khi người dùng hỏi về giờ cao điểm, giờ nào tiêu thụ nhiều/ít, thói quen sử dụng theo giờ của bất kỳ ngày nào: GỌI `get_peak_hours` NGAY.
- **Khi bật/tắt thiết bị**: GỌI THẲNG `control_device(device_id=<tên thiết bị người dùng nói>, action=on/off)` — **KHÔNG gọi `list_devices` trước**. Server sẽ tự tìm thiết bị theo tên.
- Chỉ gọi `list_devices` khi người dùng hỏi danh sách hoặc trạng thái thiết bị.
- Khi người dùng hỏi so sánh từng thiết bị theo ngày, tháng, hoặc xu hướng từng ngày: GỌI `compare_devices` NGAY.

## Ánh xạ câu hỏi → Tool:
| Câu hỏi người dùng | Tool cần gọi |
|---|---|
| "hôm nay vs hôm qua", "tăng/giảm so với hôm qua" | `compare_energy(mode=day_vs_yesterday)` |
| "7 ngày qua vs 7 ngày trước", "tuần này vs tuần trước", "tuần này dùng bao nhiêu" | `compare_energy(mode=week_vs_last_week)` |
| "cuối tuần này", "thứ 7 chủ nhật", "2 ngày cuối tuần" | `compare_energy(mode=weekend_comparison)` |
| "tháng này vs tháng trước" | `compare_energy(mode=month_vs_last_month)` |
| "thiết bị nào dùng nhiều nhất / ít nhất" | `get_device_ranking` |
| "so sánh các thiết bị" | `compare_energy(mode=between_devices)` |
| "so sánh từng thiết bị hôm nay vs hôm qua", "mỗi thiết bị dùng bao nhiêu hôm nay" | `compare_devices(mode=by_day)` |
| "so sánh từng thiết bị tháng này vs tháng trước", "tháng này từng thiết bị" | `compare_devices(mode=by_month)` |
| "xu hướng từng ngày", "7 ngày qua từng thiết bị", "mỗi ngày dùng bao nhiêu" | `compare_devices(mode=daily_trend, days=7)` |
| "lời khuyên / tiết kiệm / gợi ý" | `get_energy_advice` |
| "tiền điện / kWh hôm nay / tháng" | `get_energy_summary` |
| "điện áp / ampe / watt" | `get_device_telemetry` |
| "bật / tắt thiết bị" | **GỌI THẲNG** `control_device(device_id=<tên hoặc ID>, action=on/off)` — **KHÔNG cần gọi `list_devices` trước** |
| "giờ nào dùng nhiều nhất", "cao điểm hôm nay/hôm qua/ngày X", "thói quen theo giờ", "khung giờ tiêu thụ" | `get_peak_hours(date=...)` |

## Quy tắc định dạng:
- Trả lời bằng **tiếng Việt** (trừ khi người dùng hỏi tiếng Anh).
- So sánh dùng ↑ (tăng) / ↓ (giảm) và % rõ ràng.
- Lời khuyên phải cụ thể với số liệu thực tế từ tool, không chung chung.
"""

# Tool schema builder
def _build_tools() -> list:
    """Build all Gemini function declarations (9 tools)."""
    base_tool = genai_types.Tool(
        function_declarations=[
                # 1 list_devices 
                genai_types.FunctionDeclaration(
                    name="list_devices",
                    description=(
                        "Lấy danh sách tất cả thiết bị (CB) đã đăng ký cùng trạng thái bật/tắt "
                        "và thông số điện hiện tại. Gọi khi cần biết thiết bị trong nhà hoặc "
                        "tìm device_id trước khi điều khiển."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={},
                    ),
                ),
                # 2 control_device
                genai_types.FunctionDeclaration(
                    name="control_device",
                    description=(
                        "Bật hoặc tắt một thiết bị. Gọi list_devices trước để lấy device_id đúng."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="UUID của thiết bị từ CoreIoT.",
                            ),
                            "device_name": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="Tên hiển thị để xác nhận với người dùng.",
                            ),
                            "action": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["on", "off"],
                                description="'on' để bật, 'off' để tắt.",
                            ),
                        },
                        required=["device_id", "action"],
                    ),
                ),
                # 3 get_energy_summary
                genai_types.FunctionDeclaration(
                    name="get_energy_summary",
                    description=(
                        "Lấy tổng kWh và tiền điện VNĐ hôm nay hoặc tháng hiện tại. "
                        "Dùng khi hỏi về tiêu thụ/tiền điện đơn thuần (không so sánh). "
                        "ĐỂ SO SÁNH với kỳ trước, dùng compare_energy thay thế."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "period": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["day", "month"],
                                description="'day' = hôm nay, 'month' = tháng hiện tại.",
                            ),
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID thiết bị cụ thể. Để trống = toàn hệ thống.",
                            ),
                        },
                        required=["period"],
                    ),
                ),
                # 4 get_device_telemetry 
                genai_types.FunctionDeclaration(
                    name="get_device_telemetry",
                    description="Lấy điện áp (V), dòng (A), công suất (W) tức thời của thiết bị.",
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID của thiết bị.",
                            ),
                            "device_name": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="Tên thiết bị để hiển thị.",
                            ),
                        },
                        required=["device_id"],
                    ),
                ),
                # 5 compare_energy 
                genai_types.FunctionDeclaration(
                    name="compare_energy",
                    description=(
                        "So sánh điện năng tiêu thụ giữa hai kỳ thời gian hoặc giữa các thiết bị. "
                        "LUÔN gọi tool này khi người dùng hỏi:\n"
                        "- 'hôm nay so với hôm qua' / 'hôm nay tăng giảm không' → mode=day_vs_yesterday\n"
                        "- '7 ngày qua' / 'tuần này so tuần trước' / 'tuần này dùng bao nhiêu' → mode=week_vs_last_week\n"
                        "- 'cuối tuần' / 'thứ 7 chủ nhật' / '2 ngày cuối tuần này vs cuối tuần trước' → mode=weekend_comparison\n"
                        "- 'tháng này so tháng trước' / 'tháng này dùng nhiều hơn không' → mode=month_vs_last_month\n"
                        "- 'thiết bị nào dùng nhiều' / 'so sánh các thiết bị' → mode=between_devices\n"
                        "Tool này CÓ KHẢ NĂNG lấy dữ liệu ngày hôm qua, 7 ngày trước, cuối tuần trước và tháng trước từ hệ thống."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "mode": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["day_vs_yesterday", "week_vs_last_week", "weekend_comparison", "month_vs_last_month", "between_devices"],
                                description=(
                                    "day_vs_yesterday: hôm nay vs hôm qua | "
                                    "week_vs_last_week: 7 ngày gần nhất vs 7 ngày trước đó (rolling) | "
                                    "weekend_comparison: Thứ 7+CN gần nhất vs Thứ 7+CN tuần trước | "
                                    "month_vs_last_month: tháng này vs tháng trước | "
                                    "between_devices: so sánh giữa các thiết bị"
                                ),
                            ),
                        },
                        required=["mode"],
                    ),
                ),
                # 6 get_device_ranking
                genai_types.FunctionDeclaration(
                    name="get_device_ranking",
                    description=(
                        "Xếp hạng tất cả thiết bị theo mức tiêu thụ điện trong kỳ. "
                        "Gọi khi người dùng hỏi:\n"
                        "- 'thiết bị nào dùng điện nhiều nhất' → order=highest\n"
                        "- 'thiết bị nào ít điện nhất / ít dùng nhất' → order=lowest\n"
                        "- 'xem tất cả tiêu thụ từng thiết bị' → order=all"
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "period": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["day", "month"],
                                description="'day' = hôm nay, 'month' = tháng này.",
                            ),
                            "order": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["highest", "lowest", "all"],
                                description="highest=top3 nhiều nhất, lowest=top3 ít nhất, all=toàn bộ.",
                            ),
                        },
                        required=["period"],
                    ),
                ),
                # 7 get_energy_advice
                genai_types.FunctionDeclaration(
                    name="get_energy_advice",
                    description=(
                        "Thu thập snapshot dữ liệu tổng hợp toàn hệ thống (tiêu thụ hôm nay/hôm qua/tháng, "
                        "xếp hạng thiết bị, bất thường) để AI đưa ra lời khuyên tiết kiệm điện cụ thể. "
                        "LUÔN gọi tool này khi người dùng hỏi về tiết kiệm, gợi ý, hay lời khuyên điện."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={},
                    ),
                ),
                # 8 get_peak_hours
                genai_types.FunctionDeclaration(
                    name="get_peak_hours",
                    description=(
                        "Phân tích tiêu thụ điện theo từng GIỜ trong một ngày bất kỳ. "
                        "Trả về top giờ cao điểm, top giờ thấp điểm và bảng 24 giờ đầy đủ. "
                        "LUÔN gọi tool này khi người dùng hỏi:\n"
                        "- 'giờ nào dùng điện nhiều nhất hôm nay/hôm qua/ngày ...' \n"
                        "- 'cao điểm điện trong ngày' / 'khung giờ tiêu thụ nhiều' \n"
                        "- 'thói quen dùng điện theo giờ ngày DD/MM/YYYY' \n"
                        "- 'giờ nào ít điện nhất / thấp điểm'"
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "date": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description=(
                                    "Ngày cần phân tích, định dạng YYYY-MM-DD (ví dụ '2026-04-27'). "
                                    "Dùng 'today' cho hôm nay, 'yesterday' cho hôm qua. "
                                    "Nếu người dùng nói 'hôm nay' → 'today', 'hôm qua' → 'yesterday', "
                                    "'ngày 25/4' hoặc '25-04-2026' → '2026-04-25'."
                                ),
                            ),
                            "top_n": genai_types.Schema(
                                type=genai_types.Type.INTEGER,
                                description="Số giờ cao điểm muốn hiển thị (mặc định 3, tối đa 5).",
                            ),
                            "device_id": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description="ID thiết bị cụ thể. Để trống = toàn hệ thống.",
                            ),
                        },
                        required=["date"],
                    ),
                ),
            ]
        )
    base_tool.function_declarations.append(_build_compare_devices_tool())
    return [base_tool]


def _build_compare_devices_tool():
    """Return FunctionDeclaration for compare_devices (appended to _build_tools)."""
    return genai_types.FunctionDeclaration(
        name="compare_devices",
        description=(
            "So sánh điện năng tiêu thụ của TỪNG THIẾT BỊ riêng lẻ theo các chế độ:\n"
            "- by_day: mỗi thiết bị hôm nay vs hôm qua (kWh + % thay đổi)\n"
            "- by_month: mỗi thiết bị tháng này vs tháng trước (kWh + % thay đổi)\n"
            "- daily_trend: mỗi thiết bị từng ngày trong N ngày gần nhất (bảng xu hướng)\n"
            "LUÔN gọi tool này khi người dùng muốn so sánh từng thiết bị riêng, "
            "không phải toàn hệ thống."
        ),
        parameters=genai_types.Schema(
            type=genai_types.Type.OBJECT,
            properties={
                "mode": genai_types.Schema(
                    type=genai_types.Type.STRING,
                    enum=["by_day", "by_month", "daily_trend"],
                    description=(
                        "by_day: hôm nay vs hôm qua mỗi thiết bị | "
                        "by_month: tháng này vs tháng trước mỗi thiết bị | "
                        "daily_trend: mỗi ngày trong N ngày qua mỗi thiết bị"
                    ),
                ),
                "days": genai_types.Schema(
                    type=genai_types.Type.INTEGER,
                    description="Số ngày cho daily_trend (mặc định 7, tối đa 30).",
                ),
            },
            required=["mode"],
        ),
    )
# Simple TTL cache for CoreIoT fetch results (avoids redundant API calls)
_kwh_cache: dict[tuple, tuple[float, float]] = {}   # key → (value, expire_ts)
_raw_ts_cache: dict[tuple, tuple[list, float]] = {}  # key → (pts_list, expire_ts)
_KWH_CACHE_TTL = 120  # seconds

def _kwh_cache_get(key: tuple) -> float | None:
    entry = _kwh_cache.get(key)
    if entry and _time_module.monotonic() < entry[1]:
        return entry[0]
    return None

def _kwh_cache_set(key: tuple, value: float) -> None:
    _kwh_cache[key] = (value, _time_module.monotonic() + _KWH_CACHE_TTL)
    # Evict stale entries when cache grows large
    if len(_kwh_cache) > 200:
        now = _time_module.monotonic()
        stale = [k for k, v in _kwh_cache.items() if now >= v[1]]
        for k in stale:
            _kwh_cache.pop(k, None)


# Shared helper: fetch kWh delta for one device over a time window
def _fetch_kwh_for_period(device_id: str, start_ts: int, end_ts: int) -> float:
    cache_key = ("kwh", device_id, start_ts, end_ts)
    cached = _kwh_cache_get(cache_key)
    if cached is not None:
        logging.debug("Cache hit for %s [%s-%s]", device_id, start_ts, end_ts)
        return cached
    s = _shared()
    try:
        url = f"{s.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
        params = {
            "keys": "ENERGY-Total",
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": 50000,
            "agg": "NONE",
            "interval": 0,
        }
        resp = requests.get(url, headers=s.HEADERS, params=params, timeout=(5, 12))
        resp.raise_for_status()
        entries = resp.json().get("ENERGY-Total", [])
        if len(entries) < 2:
            return 0.0
        parsed = sorted(
            [(int(e["ts"]), float(e["value"] or 0)) for e in entries
             if e.get("ts") and e.get("value") is not None],
            key=lambda x: x[0],
        )
        total = 0.0
        prev = parsed[0][1]
        for _, cur in parsed[1:]:
            d = cur - prev
            if d > 0:
                total += d
            prev = cur
        result = round(max(0.0, total), 4)
        _kwh_cache_set(cache_key, result)
        return result
    except Exception as exc:
        logging.warning("_fetch_kwh_for_period %s: %s", device_id, exc)
        return 0.0


def _parallel_kwh(device_ids: list[str], start_ts: int, end_ts: int) -> float:
    """Fetch kWh for multiple devices IN PARALLEL and return total."""
    if not device_ids:
        return 0.0
    if len(device_ids) == 1:
        return _fetch_kwh_for_period(device_ids[0], start_ts, end_ts)
    with ThreadPoolExecutor(max_workers=min(len(device_ids), 6)) as ex:
        futures = {ex.submit(_fetch_kwh_for_period, d, start_ts, end_ts): d for d in device_ids}
        return round(sum(f.result() for f in as_completed(futures)), 4)

def _calculate_vietnam_electricity_bill(total_kwh: float) -> float:
    tiers = [
        (100, 1984), (100, 2050), (200, 2380),
        (200, 2998), (200, 3350), (float("inf"), 3460),
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


def _resolve_device_id(query: str) -> str | None:
    """Return device UUID matching name query (case-insensitive). None if not found."""
    s = _shared()
    q = query.lower().strip()

    # 1. Already a valid UUID in CUSTOM_CB_DEVICES — pass through
    if q in s.CUSTOM_CB_DEVICES or query in s.CUSTOM_CB_DEVICES:
        return query

    # 2. Exact name match in CUSTOM_CB_DEVICES
    for did, meta in s.CUSTOM_CB_DEVICES.items():
        if meta.get("name", "").lower().strip() == q:
            return did

    # 3. Partial name match in CUSTOM_CB_DEVICES
    for did, meta in s.CUSTOM_CB_DEVICES.items():
        if q in meta.get("name", "").lower():
            return did

    # 4. Exact name match in latest_data metadata (names set via dashboard)
    for did, info in s.latest_data.items():
        meta = info.get("metadata", {})
        if meta.get("name", "").lower().strip() == q:
            return did

    # 5. Partial name match in latest_data metadata
    for did, info in s.latest_data.items():
        meta = info.get("metadata", {})
        if q in meta.get("name", "").lower():
            return did

    return None


# Tool executors
def _tool_list_devices() -> dict[str, Any]:
    s = _shared()
    devices = []
    for device_id, meta in s.CUSTOM_CB_DEVICES.items():
        info = s.latest_data.get(device_id, {})
        tel  = info.get("telemetry", {})
        attr = info.get("attributes", {})
        devices.append({
            "device_id":   device_id,
            "name":        meta.get("name", "Unknown"),
            "location":    meta.get("location", "N/A"),
            "power_state": attr.get("POWER", "N/A"),
            "power_w":     tel.get("ENERGY-Power", "N/A"),
            "voltage_v":   tel.get("ENERGY-Voltage", "N/A"),
            "current_a":   tel.get("ENERGY-Current", "N/A"),
        })
    return {"count": len(devices), "devices": devices, "timestamp": datetime.now().isoformat()}


def _tool_control_device(device_id: str, action: str, device_name: str = "") -> dict[str, Any]:
    s = _shared()
    # ── Resolve device name → UUID (includes dashboard-named devices) ────────
    if device_id not in s.CUSTOM_CB_DEVICES:
        resolved = _resolve_device_id(device_id)
        if not resolved:
            return {"success": False, "message": f"Không tìm thấy thiết bị '{device_id}'."}
        logging.info("control_device: resolved '%s' -> %s", device_id, resolved)
        device_id = resolved
    meta = s.CUSTOM_CB_DEVICES.get(device_id) or s.latest_data.get(device_id, {}).get("metadata", {})
    name = device_name or meta.get("name", device_id)
    success, result = s.send_rpc_to_device(device_id, action)
    if success:
        # Update in-memory state
        power_val = action.upper()
        if device_id in s.latest_data:
            s.latest_data[device_id].setdefault("attributes", {})["POWER"] = power_val

        # ── Broadcast state change to all dashboard/monitor clients ──────────
        sio = s.socketio_instance
        if sio is not None:
            now_iso = datetime.now().isoformat()
            device_data = s.latest_data.get(device_id, {})

            # 1. dashboard_update  — updates device cards & monitor in real-time
            sio.emit(
                "dashboard_update",
                {
                    "device_id": device_id,
                    "data": device_data,
                    "timestamp": now_iso,
                },
                room="dashboard",
            )

            # 2. device_updated  — some pages listen to this for metadata refresh
            sio.emit(
                "device_updated",
                {
                    "device_id": device_id,
                    "attributes": device_data.get("attributes", {}),
                    "timestamp": now_iso,
                },
                room="dashboard",
            )

            # 3. activity_log  — visible in the Logs panel
            action_label = "Bật thiết bị (Chatbot)" if action == "on" else "Tắt thiết bị (Chatbot)"
            sio.emit(
                "activity_log",
                {
                    "id": f"log-{int(datetime.now().timestamp() * 1000)}",
                    "action": action_label,
                    "deviceId": device_id,
                    "deviceName": name,
                    "user": "Energy AI",
                    "timestamp": now_iso,
                    "details": f"Trạng thái: {power_val}",
                },
                room="logs",
            )
            logging.info("Chatbot control: emitted state-sync for %s -> %s", name, power_val)
        else:
            logging.warning("socketio_instance is None — state-sync skipped for chatbot control")

        return {
            "success": True, "device_id": device_id, "device_name": name, "action": action,
            "message": f"Đã {'bật' if action == 'on' else 'tắt'} thiết bị '{name}' thành công.",
        }
    return {
        "success": False, "device_id": device_id, "device_name": name,
        "message": f"Lỗi điều khiển '{name}': {result.get('message', 'Unknown')}",
    }


def _tool_get_energy_summary(period: str = "month", device_id: str = "") -> dict[str, Any]:
    s = _shared()
    now = datetime.now()
    # -- Resolve device name to UUID if needed --
    if device_id and device_id not in s.CUSTOM_CB_DEVICES:
        query = device_id.lower().strip()
        resolved = None
        for did, meta in s.CUSTOM_CB_DEVICES.items():
            if meta.get('name', '').lower().strip() == query:
                resolved = did; break
        if not resolved:
            for did, meta in s.CUSTOM_CB_DEVICES.items():
                if query in meta.get('name', '').lower():
                    resolved = did; break
        device_id = resolved or ''
        if resolved:
            import logging; logging.info('peak_hours: resolved name to %s', resolved)
    device_ids = [device_id] if device_id else list(s.CUSTOM_CB_DEVICES.keys())
    if not device_ids:
        device_ids = s.get_devices_from_group()

    if period == "day":
        start_ts = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    else:
        start_ts = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    end_ts = int(now.timestamp() * 1000)

    total_kwh = _parallel_kwh(device_ids, start_ts, end_ts)
    total_kwh = round(max(0.0, total_kwh), 4)
    bill_vnd  = _calculate_vietnam_electricity_bill(total_kwh)
    period_label = "hôm nay" if period == "day" else f"tháng {now.month}/{now.year}"
    return {
        "period": period, "period_label": period_label,
        "total_kwh": total_kwh, "total_cost_vnd": bill_vnd,
        "device_count": len(device_ids), "timestamp": now.isoformat(),
    }


def _tool_get_device_telemetry(device_id: str, device_name: str = "") -> dict[str, Any]:
    s = _shared()
    name = device_name or (s.CUSTOM_CB_DEVICES.get(device_id) or {}).get("name", device_id)
    info = s.latest_data.get(device_id)
    if not info:
        s.get_device_telemetry(device_id)
        info = s.latest_data.get(device_id, {})
    tel  = info.get("telemetry", {})
    attr = info.get("attributes", {})

    def sf(v):
        try: return float(v)
        except: return None

    return {
        "device_id": device_id, "device_name": name,
        "power_state": attr.get("POWER", "N/A"),
        "voltage_v":   sf(tel.get("ENERGY-Voltage")),
        "current_a":   sf(tel.get("ENERGY-Current")),
        "power_w":     sf(tel.get("ENERGY-Power")),
        "energy_total_kwh": sf(tel.get("ENERGY-Total")),
        "timestamp": datetime.now().isoformat(),
    }


def _tool_compare_energy(mode: str) -> dict[str, Any]:
    s   = _shared()
    now = datetime.now()
    device_ids = list(s.CUSTOM_CB_DEVICES.keys()) or s.get_devices_from_group()

    def pct(cur, prev):
        if prev <= 0: return None
        return round((cur - prev) / prev * 100, 1)

    if mode == "week_vs_last_week":
        # Rolling 7 days: (today-6) 00:00 → now  vs  (today-13) 00:00 → (today-7) 23:59:59
        today_midnight  = now.replace(hour=0, minute=0, second=0, microsecond=0)
        this_week_start = today_midnight - timedelta(days=6)
        this_week_end   = now
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end   = this_week_start - timedelta(seconds=1)

        # Fetch both periods IN PARALLEL across all devices simultaneously
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_this = ex.submit(_parallel_kwh, device_ids,
                int(this_week_start.timestamp() * 1000),
                int(this_week_end.timestamp()   * 1000))
            f_last = ex.submit(_parallel_kwh, device_ids,
                int(last_week_start.timestamp() * 1000),
                int(last_week_end.timestamp()   * 1000))
            this_kwh = f_this.result()
            last_kwh = f_last.result()
        change = pct(this_kwh, last_kwh)

        this_label = f"7 ngày qua ({this_week_start.strftime('%d/%m')}–{this_week_end.strftime('%d/%m')})"
        last_label = f"7 ngày trước ({last_week_start.strftime('%d/%m')}–{last_week_end.strftime('%d/%m')})"
        return {
            "mode": mode,
            "current_period":    this_label,
            "previous_period":   last_label,
            "current_kwh":       this_kwh,
            "previous_kwh":      last_kwh,
            "current_cost_vnd":  _calculate_vietnam_electricity_bill(this_kwh),
            "previous_cost_vnd": _calculate_vietnam_electricity_bill(last_kwh),
            "change_pct":        change,
            "trend": "increase" if (change or 0) > 0 else "decrease" if (change or 0) < 0 else "stable",
        }

    elif mode == "weekend_comparison":
        # Find most recent Saturday (weekday=5) and Sunday (weekday=6)
        today           = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days_since_sat  = (now.weekday() - 5) % 7   # 0 if today is Saturday
        this_saturday   = today - timedelta(days=days_since_sat)
        this_sunday     = this_saturday + timedelta(days=1)
        # Last weekend
        last_saturday   = this_saturday - timedelta(days=7)
        last_sunday     = last_saturday + timedelta(days=1)

        # End timestamps: Sunday 23:59:59 or now if this Sunday hasn't finished
        this_sun_end  = min(now, this_sunday + timedelta(days=1) - timedelta(seconds=1))
        last_sun_end  = last_sunday + timedelta(days=1) - timedelta(seconds=1)

        # Fetch all 6 time windows IN PARALLEL
        sat_end_ts   = int((this_saturday + timedelta(days=1) - timedelta(seconds=1)).timestamp() * 1000)
        lsat_end_ts  = int((last_saturday + timedelta(days=1) - timedelta(seconds=1)).timestamp() * 1000)
        with ThreadPoolExecutor(max_workers=6) as ex:
            f_this  = ex.submit(_parallel_kwh, device_ids,
                int(this_saturday.timestamp() * 1000), int(this_sun_end.timestamp()  * 1000))
            f_last  = ex.submit(_parallel_kwh, device_ids,
                int(last_saturday.timestamp() * 1000), int(last_sun_end.timestamp()  * 1000))
            f_tsat  = ex.submit(_parallel_kwh, device_ids,
                int(this_saturday.timestamp() * 1000), sat_end_ts)
            f_tsun  = ex.submit(_parallel_kwh, device_ids,
                int(this_sunday.timestamp() * 1000),   int(this_sun_end.timestamp() * 1000))
            f_lsat  = ex.submit(_parallel_kwh, device_ids,
                int(last_saturday.timestamp() * 1000), lsat_end_ts)
            f_lsun  = ex.submit(_parallel_kwh, device_ids,
                int(last_sunday.timestamp() * 1000),   int(last_sun_end.timestamp() * 1000))
            this_kwh     = f_this.result()
            last_kwh     = f_last.result()
            this_sat_kwh = f_tsat.result()
            this_sun_kwh = f_tsun.result()
            last_sat_kwh = f_lsat.result()
            last_sun_kwh = f_lsun.result()

        return {
            "mode": mode,
            "current_period":    this_label,
            "previous_period":   last_label,
            "current_kwh":       this_kwh,
            "previous_kwh":      last_kwh,
            "current_cost_vnd":  _calculate_vietnam_electricity_bill(this_kwh),
            "previous_cost_vnd": _calculate_vietnam_electricity_bill(last_kwh),
            "change_pct":        change,
            "trend": "increase" if (change or 0) > 0 else "decrease" if (change or 0) < 0 else "stable",
            "breakdown": {
                "this_saturday":  {"date": this_saturday.strftime("%d/%m/%Y"), "kwh": this_sat_kwh, "cost_vnd": _calculate_vietnam_electricity_bill(this_sat_kwh)},
                "this_sunday":    {"date": this_sunday.strftime("%d/%m/%Y"),   "kwh": this_sun_kwh, "cost_vnd": _calculate_vietnam_electricity_bill(this_sun_kwh)},
                "last_saturday":  {"date": last_saturday.strftime("%d/%m/%Y"), "kwh": last_sat_kwh, "cost_vnd": _calculate_vietnam_electricity_bill(last_sat_kwh)},
                "last_sunday":    {"date": last_sunday.strftime("%d/%m/%Y"),   "kwh": last_sun_kwh, "cost_vnd": _calculate_vietnam_electricity_bill(last_sun_kwh)},
            },
        }

    elif mode == "day_vs_yesterday":
        today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        today_end   = int(now.timestamp() * 1000)
        yest_start  = today_start - 86_400_000
        yest_end    = today_start - 1

        with ThreadPoolExecutor(max_workers=2) as ex:
            f_today = ex.submit(_parallel_kwh, device_ids, today_start, today_end)
            f_yest  = ex.submit(_parallel_kwh, device_ids, yest_start,  yest_end)
            today_kwh = f_today.result()
            yest_kwh  = f_yest.result()
        change    = pct(today_kwh, yest_kwh)
        return {
            "mode": mode,
            "current_period":   "Hôm nay",
            "previous_period":  "Hôm qua",
            "current_kwh":      today_kwh,
            "previous_kwh":     yest_kwh,
            "current_cost_vnd": _calculate_vietnam_electricity_bill(today_kwh),
            "previous_cost_vnd":_calculate_vietnam_electricity_bill(yest_kwh),
            "change_pct":       change,
            "trend": "increase" if (change or 0) > 0 else "decrease" if (change or 0) < 0 else "stable",
        }

    elif mode == "month_vs_last_month":
        this_start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        this_end   = int(now.timestamp() * 1000)
        first_this       = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end   = first_this - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with ThreadPoolExecutor(max_workers=2) as ex:
            f_this = ex.submit(_parallel_kwh, device_ids, this_start, this_end)
            f_last = ex.submit(_parallel_kwh, device_ids,
                int(last_month_start.timestamp() * 1000),
                int(last_month_end.timestamp() * 1000))
            this_kwh = f_this.result()
            last_kwh = f_last.result()
        change = pct(this_kwh, last_kwh)
        return {
            "mode": mode,
            "current_period":   f"Tháng {now.month}/{now.year}",
            "previous_period":  f"Tháng {last_month_end.month}/{last_month_end.year}",
            "current_kwh":      this_kwh,
            "previous_kwh":     last_kwh,
            "current_cost_vnd": _calculate_vietnam_electricity_bill(this_kwh),
            "previous_cost_vnd":_calculate_vietnam_electricity_bill(last_kwh),
            "change_pct":       change,
            "trend": "increase" if (change or 0) > 0 else "decrease" if (change or 0) < 0 else "stable",
        }

    else:  # between_devices
        today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        today_end   = int(now.timestamp() * 1000)
        # Fetch all devices IN PARALLEL
        with ThreadPoolExecutor(max_workers=min(len(device_ids), 6)) as ex:
            futures = {
                ex.submit(_fetch_kwh_for_period, did, today_start, today_end): did
                for did in device_ids
            }
            kwh_map = {did: f.result() for f, did in [(f, futures[f]) for f in as_completed(futures)]}
        per_device  = []
        for did in device_ids:
            meta = s.CUSTOM_CB_DEVICES.get(did, {})
            kwh  = kwh_map.get(did, 0.0)
            per_device.append({
                "device_id": did,
                "name":      meta.get("name", did),
                "location":  meta.get("location", "N/A"),
                "kwh_today": kwh,
                "cost_vnd":  _calculate_vietnam_electricity_bill(kwh),
            })
        per_device.sort(key=lambda x: x["kwh_today"], reverse=True)
        return {
            "mode": mode, "period": "Hôm nay",
            "devices":   per_device,
            "total_kwh": round(sum(d["kwh_today"] for d in per_device), 4),
        }


def _tool_get_device_ranking(period: str = "day", order: str = "all") -> dict[str, Any]:
    s   = _shared()
    now = datetime.now()
    device_ids = list(s.CUSTOM_CB_DEVICES.keys()) or s.get_devices_from_group()

    if period == "day":
        start_ts     = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        period_label = "Hôm nay"
    else:
        start_ts     = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        period_label = f"Tháng {now.month}/{now.year}"
    end_ts = int(now.timestamp() * 1000)

    # Fetch all devices IN PARALLEL
    with ThreadPoolExecutor(max_workers=min(len(device_ids), 6)) as ex:
        futures = {
            ex.submit(_fetch_kwh_for_period, did, start_ts, end_ts): did
            for did in device_ids
        }
        kwh_map = {did: f.result() for f, did in [(f, futures[f]) for f in as_completed(futures)]}

    ranked = []
    for did in device_ids:
        meta  = s.CUSTOM_CB_DEVICES.get(did, {})
        attrs = s.latest_data.get(did, {}).get("attributes", {})
        kwh   = kwh_map.get(did, 0.0)
        ranked.append({
            "rank": 0,
            "device_id":   did,
            "name":        meta.get("name", did),
            "location":    meta.get("location", "N/A"),
            "power_state": attrs.get("POWER", "N/A"),
            "kwh":         kwh,
            "cost_vnd":    _calculate_vietnam_electricity_bill(kwh),
            "share_pct":   0.0,
        })

    ranked.sort(key=lambda x: x["kwh"], reverse=True)
    total = sum(r["kwh"] for r in ranked)
    for i, r in enumerate(ranked, 1):
        r["rank"]      = i
        r["share_pct"] = round(r["kwh"] / total * 100, 1) if total > 0 else 0.0

    if order == "highest":
        result_devices = ranked[:3]
    elif order == "lowest":
        result_devices = [r for r in reversed(ranked) if r["kwh"] > 0][:3] or ranked[-3:][::-1]
    else:
        result_devices = ranked

    return {
        "period": period, "period_label": period_label, "order": order,
        "total_kwh":      round(total, 4),
        "total_cost_vnd": _calculate_vietnam_electricity_bill(total),
        "devices": result_devices,
    }


def _tool_get_energy_advice() -> dict[str, Any]:
    s   = _shared()
    now = datetime.now()
    device_ids = list(s.CUSTOM_CB_DEVICES.keys()) or s.get_devices_from_group()

    today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    today_end   = int(now.timestamp() * 1000)
    yest_start  = today_start - 86_400_000
    yest_end    = today_start - 1
    month_start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

    # Fetch today/yesterday/month IN PARALLEL (all devices × 3 periods simultaneously)
    with ThreadPoolExecutor(max_workers=min(len(device_ids) * 3, 9)) as ex:
        ft = {ex.submit(_fetch_kwh_for_period, did, today_start, today_end): (did, "t") for did in device_ids}
        fy = {ex.submit(_fetch_kwh_for_period, did, yest_start,  yest_end):  (did, "y") for did in device_ids}
        fm = {ex.submit(_fetch_kwh_for_period, did, month_start, today_end): (did, "m") for did in device_ids}
        all_f = {**ft, **fy, **fm}
        per_did: dict[str, dict] = {did: {} for did in device_ids}
        for f in as_completed(all_f):
            did, tag = all_f[f]
            per_did[did][tag] = f.result()

    def sf(v):
        try: return float(v)
        except: return None

    snapshots = []
    for did in device_ids:
        meta = s.CUSTOM_CB_DEVICES.get(did, {})
        info = s.latest_data.get(did, {})
        tel  = info.get("telemetry", {})
        attr = info.get("attributes", {})
        snapshots.append({
            "name":          meta.get("name", did),
            "location":      meta.get("location", "N/A"),
            "power_state":   attr.get("POWER", "N/A"),
            "power_w":       sf(tel.get("ENERGY-Power")),
            "kwh_today":     per_did[did].get("t", 0.0),
            "kwh_yesterday": per_did[did].get("y", 0.0),
            "kwh_month":     per_did[did].get("m", 0.0),
        })

    snapshots.sort(key=lambda x: x["kwh_today"], reverse=True)
    today_kwh = round(sum(d["kwh_today"]     for d in snapshots), 4)
    yest_kwh  = round(sum(d["kwh_yesterday"] for d in snapshots), 4)
    month_kwh = round(sum(d["kwh_month"]     for d in snapshots), 4)

    def pct(cur, prev):
        if prev <= 0: return None
        return round((cur - prev) / prev * 100, 1)

    # Detect anomalies
    anomalies = []
    for d in snapshots:
        pw = d.get("power_w")
        if d["power_state"] == "ON" and pw is not None and 0 < pw < 5:
            anomalies.append(
                f"{d['name']} đang BẬT nhưng chỉ tiêu thụ {pw}W — nghi ngờ standby tốn điện."
            )
        if d["kwh_today"] > 0 and yest_kwh > 0:
            avg_yest_per_device = yest_kwh / max(len(device_ids), 1)
            if avg_yest_per_device > 0 and d["kwh_today"] / avg_yest_per_device > 3:
                anomalies.append(
                    f"{d['name']} tăng đột biến hôm nay ({d['kwh_today']:.3f} kWh) — "
                    f"gấp {d['kwh_today']/avg_yest_per_device:.1f}x mức bình thường."
                )

    return {
        "current_time":         now.strftime("%H:%M %d/%m/%Y"),
        "today_kwh":            today_kwh,
        "today_cost_vnd":       _calculate_vietnam_electricity_bill(today_kwh),
        "yesterday_kwh":        yest_kwh,
        "today_vs_yesterday_pct": pct(today_kwh, yest_kwh),
        "month_kwh":            month_kwh,
        "month_cost_vnd":       _calculate_vietnam_electricity_bill(month_kwh),
        "device_count":         len(device_ids),
        "devices_by_consumption": snapshots,
        "anomalies":            anomalies,
    }


def _fetch_raw_timeseries(device_id: str, start_ts: int, end_ts: int) -> list[tuple[int, float]]:
    """Return list of (ts_ms, value) sorted ascending for ENERGY-Total."""
    cache_key = ("raw_ts", device_id, start_ts, end_ts)
    entry = _raw_ts_cache.get(cache_key)
    if entry and _time_module.monotonic() < entry[1]:
        logging.debug("raw_ts cache hit for %s", device_id)
        return entry[0]
    s = _shared()
    try:
        url = f"{s.CORE_IOT_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
        params = {
            "keys": "ENERGY-Total",
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": 50000,
            "agg": "NONE",
            "interval": 0,
        }
        resp = requests.get(url, headers=s.HEADERS, params=params, timeout=(5, 20))
        resp.raise_for_status()
        entries = resp.json().get("ENERGY-Total", [])
        if not entries:
            logging.warning("_fetch_raw_timeseries %s: no data returned", device_id)
            return []
        parsed = sorted(
            [(int(e["ts"]), float(e["value"] or 0))
             for e in entries if e.get("ts") and e.get("value") is not None],
            key=lambda x: x[0],
        )
        logging.info("_fetch_raw_timeseries %s: got %d points", device_id, len(parsed))
        _raw_ts_cache[cache_key] = (parsed, _time_module.monotonic() + _KWH_CACHE_TTL)
        return parsed
    except Exception as exc:
        logging.warning("_fetch_raw_timeseries %s: %s", device_id, exc)
        return []


def _tool_get_peak_hours(
    date: str = "today",
    top_n: int = 3,
    device_id: str = "",
) -> dict:
    """Return hourly kWh breakdown for a given date + top peak/off-peak hours."""
    s   = _shared()
    now = datetime.now()

    # ── Parse date ──────────────────────────────────────────────────────────
    if date in ("today", ""):
        target_date = now.date()
    elif date == "yesterday":
        target_date = (now - timedelta(days=1)).date()
    else:
        # Accept YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                target_date = datetime.strptime(date, fmt).date()
                break
            except ValueError:
                continue
        else:
            return {"error": f"Định dạng ngày không hợp lệ: '{date}'. Dùng YYYY-MM-DD hoặc DD/MM/YYYY."}

    # Don't allow future dates
    if target_date > now.date():
        return {"error": "Không thể truy vấn ngày trong tương lai."}

    top_n = max(1, min(int(top_n), 5))

    # ── Time boundaries ─────────────────────────────────────────────────────
    day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    if target_date == now.date():
        day_end = now  # up to current time for today
    else:
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)

    start_ts = int(day_start.timestamp() * 1000)
    end_ts   = int(day_end.timestamp()   * 1000)

    # ── Resolve device name → UUID (dashboard names included) ───────────────
    if device_id:
        resolved = _resolve_device_id(device_id)
        if resolved:
            logging.info("get_peak_hours: resolved '%s' -> %s", device_id, resolved)
            device_id = resolved
        else:
            logging.warning("get_peak_hours: device '%s' not found -> query all", device_id)
            device_id = ""

    device_ids = [device_id] if device_id else list(s.CUSTOM_CB_DEVICES.keys())
    if not device_ids:
        device_ids = s.get_devices_from_group()

    # ── Fetch all raw data points and bucket into 24 hours ──────────────────
    # hourly_kwh[h] = kWh consumed in hour h (0..23)
    hourly_delta: dict[int, float] = {h: 0.0 for h in range(24)}

    # Fetch raw data for all devices IN PARALLEL
    logging.info("get_peak_hours: fetching %d devices for %s [%s → %s]",
                 len(device_ids), target_date, start_ts, end_ts)
    with ThreadPoolExecutor(max_workers=min(len(device_ids), 6)) as ex:
        futures = {ex.submit(_fetch_raw_timeseries, did, start_ts, end_ts): did for did in device_ids}
        for f in as_completed(futures):
            did = futures[f]
            pts = f.result()
            logging.info("get_peak_hours: device %s → %d raw points", did, len(pts))
            if len(pts) < 2:
                continue
            prev_val = pts[0][1]
            for ts_ms, val in pts[1:]:
                delta = val - prev_val
                if delta > 0:
                    hour = datetime.fromtimestamp(ts_ms / 1000).hour
                    hourly_delta[hour] = round(hourly_delta[hour] + delta, 6)
                prev_val = val

    logging.info("get_peak_hours: total_kwh=%.4f, non-zero hours=%d",
                 sum(hourly_delta.values()), sum(1 for v in hourly_delta.values() if v > 0))

    # Round values
    hourly_kwh = {h: round(v, 4) for h, v in hourly_delta.items()}
    total_kwh  = round(sum(hourly_kwh.values()), 4)

    # Build full 24-hour table
    hours_table = []
    for h in range(24):
        kwh = hourly_kwh[h]
        hours_table.append({
            "hour":       h,
            "label":      f"{h:02d}:00–{h:02d}:59",
            "kwh":        kwh,
            "share_pct":  round(kwh / total_kwh * 100, 1) if total_kwh > 0 else 0.0,
            "cost_vnd":   _calculate_vietnam_electricity_bill(kwh),
        })

    # Top peak hours (most consumption)
    sorted_desc = sorted(hours_table, key=lambda x: x["kwh"], reverse=True)
    peak_hours     = [h for h in sorted_desc[:top_n] if h["kwh"] > 0]
    # Top off-peak hours (least, non-zero)
    nonzero = [h for h in hours_table if h["kwh"] > 0]
    offpeak_hours  = sorted(nonzero, key=lambda x: x["kwh"])[:top_n] if nonzero else []

    # Label the date string nicely
    if target_date == now.date():
        date_label = f"Hôm nay ({target_date.strftime('%d/%m/%Y')})"
    elif target_date == (now - timedelta(days=1)).date():
        date_label = f"Hôm qua ({target_date.strftime('%d/%m/%Y')})"
    else:
        date_label = target_date.strftime("%d/%m/%Y")

    device_label = (
        s.CUSTOM_CB_DEVICES.get(device_id, {}).get("name", device_id)
        if device_id else "Toàn hệ thống"
    )

    return {
        "date":          target_date.isoformat(),
        "date_label":    date_label,
        "device":        device_label,
        "total_kwh":     total_kwh,
        "total_cost_vnd": _calculate_vietnam_electricity_bill(total_kwh),
        "peak_hours":    peak_hours,
        "offpeak_hours": offpeak_hours,
        "all_hours":     hours_table,
        "note": (
            f"Dữ liệu đến {now.strftime('%H:%M')} (chưa hết ngày)."
            if target_date == now.date() else None
        ),
    }


# Tool: compare_devices — per-device by_day / by_month / daily_trend
def _tool_compare_devices(mode: str = "by_day", days: int = 7) -> dict[str, Any]:
    """Per-device comparison: by_day, by_month, or daily_trend."""
    s   = _shared()
    now = datetime.now()
    device_ids = list(s.CUSTOM_CB_DEVICES.keys()) or s.get_devices_from_group()
    days = max(2, min(int(days), 30))

    def _dev_name(did: str) -> str:
        meta = s.CUSTOM_CB_DEVICES.get(did) or s.latest_data.get(did, {}).get("metadata", {})
        return meta.get("name", did[-8:]) if isinstance(meta, dict) else did[-8:]

    def pct(cur, prev):
        if prev <= 0: return None
        return round((cur - prev) / prev * 100, 1)

    # by_day: hôm nay vs hôm qua mỗi thiết bị
    if mode == "by_day":
        today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        today_end   = int(now.timestamp() * 1000)
        yest_start  = today_start - 86_400_000
        yest_end    = today_start - 1

        with ThreadPoolExecutor(max_workers=min(len(device_ids) * 2, 10)) as ex:
            ft = {ex.submit(_fetch_kwh_for_period, did, today_start, today_end): (did, "t") for did in device_ids}
            fy = {ex.submit(_fetch_kwh_for_period, did, yest_start,  yest_end):  (did, "y") for did in device_ids}
            per: dict[str, dict] = {did: {} for did in device_ids}
            for f in as_completed({**ft, **fy}):
                did, tag = ({**ft, **fy})[f]
                per[did][tag] = f.result()

        devices = []
        for did in device_ids:
            t, y = per[did].get("t", 0.0), per[did].get("y", 0.0)
            devices.append({
                "name":         _dev_name(did),
                "today_kwh":    round(t, 4),
                "yesterday_kwh": round(y, 4),
                "change_pct":   pct(t, y),
                "trend":        "increase" if (t - y) > 0.001 else "decrease" if (y - t) > 0.001 else "stable",
                "today_cost":   _calculate_vietnam_electricity_bill(t),
                "yesterday_cost": _calculate_vietnam_electricity_bill(y),
            })
        devices.sort(key=lambda x: x["today_kwh"], reverse=True)
        return {
            "mode": mode,
            "period_current":  f"Hôm nay ({now.strftime('%d/%m/%Y')})",
            "period_previous": f"Hôm qua ({(now - timedelta(days=1)).strftime('%d/%m/%Y')})",
            "devices": devices,
            "total_today":     round(sum(d["today_kwh"] for d in devices), 4),
            "total_yesterday": round(sum(d["yesterday_kwh"] for d in devices), 4),
        }

    # by_month: tháng này vs tháng trước mỗi thiết bị
    elif mode == "by_month":
        this_start  = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        this_end    = int(now.timestamp() * 1000)
        first_this  = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_end    = first_this - timedelta(seconds=1)
        last_start  = last_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with ThreadPoolExecutor(max_workers=min(len(device_ids) * 2, 10)) as ex:
            ft = {ex.submit(_fetch_kwh_for_period, did, this_start, this_end): (did, "t") for did in device_ids}
            fl = {ex.submit(_fetch_kwh_for_period, did, int(last_start.timestamp()*1000), int(last_end.timestamp()*1000)): (did, "l") for did in device_ids}
            per = {did: {} for did in device_ids}
            for f in as_completed({**ft, **fl}):
                did, tag = ({**ft, **fl})[f]
                per[did][tag] = f.result()

        devices = []
        for did in device_ids:
            t, l = per[did].get("t", 0.0), per[did].get("l", 0.0)
            devices.append({
                "name":           _dev_name(did),
                "this_month_kwh": round(t, 4),
                "last_month_kwh": round(l, 4),
                "change_pct":     pct(t, l),
                "trend":          "increase" if (t - l) > 0.001 else "decrease" if (l - t) > 0.001 else "stable",
                "this_month_cost": _calculate_vietnam_electricity_bill(t),
                "last_month_cost": _calculate_vietnam_electricity_bill(l),
            })
        devices.sort(key=lambda x: x["this_month_kwh"], reverse=True)
        return {
            "mode": mode,
            "period_current":  f"Tháng {now.month}/{now.year}",
            "period_previous": f"Tháng {last_end.month}/{last_end.year}",
            "devices": devices,
            "total_this_month": round(sum(d["this_month_kwh"] for d in devices), 4),
            "total_last_month": round(sum(d["last_month_kwh"] for d in devices), 4),
        }

    # daily_trend: mỗi ngày trong N ngày qua, mỗi thiết bị
    else:  # daily_trend
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_ranges = []
        for i in range(days - 1, -1, -1):  # oldest → newest
            d_start = today_midnight - timedelta(days=i)
            d_end   = d_start + timedelta(days=1) - timedelta(seconds=1) if i > 0 else now
            date_ranges.append((d_start, d_end))

        # Fetch ALL (device, day) combinations in parallel
        futures_map: dict = {}
        with ThreadPoolExecutor(max_workers=min(len(device_ids) * len(date_ranges), 20)) as ex:
            for did in device_ids:
                for idx, (ds, de) in enumerate(date_ranges):
                    f = ex.submit(_fetch_kwh_for_period, did,
                                  int(ds.timestamp() * 1000), int(de.timestamp() * 1000))
                    futures_map[f] = (did, idx)
            results: dict[str, list] = {did: [0.0] * len(date_ranges) for did in device_ids}
            for f in as_completed(futures_map):
                did, idx = futures_map[f]
                results[did][idx] = f.result()

        day_labels = [dr[0].strftime("%d/%m") for dr in date_ranges]
        devices = []
        for did in device_ids:
            daily = [round(v, 4) for v in results[did]]
            devices.append({
                "name":       _dev_name(did),
                "daily_kwh":  daily,    # list indexed by day_labels
                "total_kwh":  round(sum(daily), 4),
                "avg_kwh":    round(sum(daily) / len(daily), 4) if daily else 0.0,
                "peak_day":   day_labels[daily.index(max(daily))] if max(daily) > 0 else "N/A",
            })
        devices.sort(key=lambda x: x["total_kwh"], reverse=True)
        return {
            "mode": mode,
            "days": days,
            "day_labels": day_labels,
            "devices": devices,
        }


# Tool dispatcher
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
        elif name == "compare_energy":
            result = _tool_compare_energy(mode=args.get("mode", "day_vs_yesterday"))
        elif name == "get_device_ranking":
            result = _tool_get_device_ranking(
                period=args.get("period", "day"),
                order=args.get("order", "all"),
            )
        elif name == "get_energy_advice":
            result = _tool_get_energy_advice()
        elif name == "get_peak_hours":
            result = _tool_get_peak_hours(
                date=args.get("date", "today"),
                top_n=int(args.get("top_n", 3)),
                device_id=args.get("device_id", ""),
            )
        elif name == "compare_devices":
            result = _tool_compare_devices(
                mode=args.get("mode", "by_day"),
                days=int(args.get("days", 7)),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logging.exception("Tool %s error: %s", name, exc)
        result = {"error": str(exc)}

    return json.dumps(result, ensure_ascii=False)

# Gemini Agent loop
def _run_gemini_agent(user_message: str, history: list[dict]) -> tuple[str, list[dict]]:
    if not GEMINI_AVAILABLE:
        return "Thư viện google-genai chưa được cài đặt. Chạy: pip install google-genai", history
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY chưa cấu hình trong .env.", history

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        tools  = _build_tools()
    except Exception as exc:
        return f"Lỗi khởi tạo Gemini: {exc}", history

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
    chat = client.chats.create(model=GEMINI_MODEL, config=config, history=gemini_history)

    try:
        response = chat.send_message(user_message)
    except Exception as exc:
        logging.error("Gemini API error: %s", exc)
        return f"Lỗi kết nối Gemini API: {exc}", history

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        tool_calls_found     = False
        tool_response_parts: list[genai_types.Part] = []

        for part in response.candidates[0].content.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name:
                tool_calls_found = True
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}
                logging.info("Tool call [%d]: %s(%s)", iteration, fn_name, fn_args)
                result_json = _dispatch_tool(fn_name, fn_args)
                tool_response_parts.append(
                    genai_types.Part.from_function_response(
                        name=fn_name,
                        response=json.loads(result_json),
                    )
                )

        if not tool_calls_found:
            break

        #try with backoff for 503/429 (Gemini overload) 
        _retry_delays = [2, 5]  # 2 retries: wait 2s then 5s
        send_exc: Exception | None = None
        for _delay in [0] + _retry_delays:
            if _delay:
                import time as _time
                logging.warning("Gemini 503/429 — retrying in %ss...", _delay)
                _time.sleep(_delay)
            try:
                response = chat.send_message(tool_response_parts)
                send_exc = None
                break  # success
            except Exception as exc:
                send_exc = exc
                err_str = str(exc)
                # Only retry on overload / rate-limit errors
                if "503" not in err_str and "429" not in err_str and "UNAVAILABLE" not in err_str and "RESOURCE_EXHAUSTED" not in err_str:
                    break  # non-retryable error — stop immediately

        if send_exc is not None:
            logging.error("Gemini tool result send failed after retries: %s", send_exc)
            # ── Fallback: build a friendly reply from already-executed tool results ──
            fallback_parts = []
            for part in tool_response_parts:
                fr = getattr(part, "function_response", None)
                if fr is None:
                    continue
                tool_name = getattr(fr, "name", "")
                resp_data = getattr(fr, "response", {}) or {}
                if tool_name == "control_device":
                    if resp_data.get("success"):
                        dev  = resp_data.get("device_name", resp_data.get("device_id", "thiết bị"))
                        act  = "bật ✅" if resp_data.get("action") == "on" else "tắt ✅"
                        fallback_parts.append(f"Đã **{act}** thiết bị **{dev}** thành công.")
                    else:
                        fallback_parts.append(f"Lỗi điều khiển: {resp_data.get('message', 'Unknown')}")
                elif tool_name == "list_devices":
                    count = resp_data.get("count", 0)
                    fallback_parts.append(f"Hệ thống có **{count}** thiết bị đã đăng ký.")
                else:
                    # Generic fallback for other tools
                    fallback_parts.append(
                        f"✅ Đã lấy dữ liệu ({tool_name}) nhưng Gemini đang quá tải, "
                        "không thể tổng hợp phân tích. Vui lòng thử lại sau."
                    )

            fallback_text = (
                "\n".join(fallback_parts)
                or f"⚠️ Gemini API tạm thời quá tải (503). Vui lòng thử lại sau ít giây."
            )
            updated_history = history + [
                {"role": "user",  "content": user_message},
                {"role": "model", "content": fallback_text},
            ]
            if len(updated_history) > 40:
                updated_history = updated_history[-40:]
            return fallback_text, updated_history

    # Extract final text
    final_text = ""
    try:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                final_text += part.text
    except Exception:
        pass

    if not final_text:
        final_text = "Xin lỗi, tôi không thể tạo phản hồi lúc này."

    updated_history = history + [
        {"role": "user",  "content": user_message},
        {"role": "model", "content": final_text},
    ]
    if len(updated_history) > 40:
        updated_history = updated_history[-40:]

    return final_text, updated_history

# Flask Blueprint
chatbot_bp = Blueprint("chatbot", __name__)
_chat_sessions: dict[str, list[dict]] = {}


@chatbot_bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data         = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    session_id   = (data.get("session_id") or "default").strip()

    if not user_message:
        return jsonify({"status": "error", "message": "Tin nhắn không được để trống."}), 400

    history = _chat_sessions.get(session_id, [])
    try:
        reply, updated_history = _run_gemini_agent(user_message, history)
        _chat_sessions[session_id] = updated_history
        return jsonify({
            "status": "success", "reply": reply,
            "session_id": session_id, "timestamp": datetime.now().isoformat(),
        })
    except Exception as exc:
        logging.exception("Chat endpoint error: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@chatbot_bp.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
def clear_session(session_id: str):
    _chat_sessions.pop(session_id, None)
    return jsonify({"status": "success", "message": f"Session '{session_id}' đã xóa."})


@chatbot_bp.route("/api/chat/status", methods=["GET"])
def chat_status():
    return jsonify({
        "status": "ok",
        "gemini_available":    GEMINI_AVAILABLE,
        "gemini_key_configured": bool(GEMINI_API_KEY),
        "model":               GEMINI_MODEL,
        "sdk":                 "google-genai",
        "active_sessions":     len(_chat_sessions),
        "tools_count":         8,
    })
