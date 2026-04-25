# chatbot_api.py — Gemini-powered AI Chatbot for Smart Energy Dashboard.

# Tools available (7 total):
#   • list_devices        – list all CB devices + power state
#   • control_device      – toggle any device on/off
#   • get_energy_summary  – daily or monthly kWh + bill
#   • get_device_telemetry – live V / A / W snapshot
#   • compare_energy      – day vs yesterday | month vs last month | between devices
#   • get_device_ranking  – rank devices by consumption (highest/lowest/all)
#   • get_energy_advice   – full data snapshot for AI-generated saving tips
# 

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
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

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
- Khi người dùng hỏi so sánh ("hôm nay vs hôm qua", "tuần này so tuần trước", "tháng này so tháng trước", "thiết bị nào dùng nhiều"): GỌI `compare_energy` hoặc `get_device_ranking` NGAY.
- Khi người dùng hỏi mà bạn không chắc cần tool nào: gọi `list_devices` trước để có context.

## Ánh xạ câu hỏi → Tool:
| Câu hỏi người dùng | Tool cần gọi |
|---|---|
| "hôm nay vs hôm qua", "tăng/giảm so với hôm qua" | `compare_energy(mode=day_vs_yesterday)` |
| "tuần này vs tuần trước", "tuần này dùng bao nhiêu" | `compare_energy(mode=week_vs_last_week)` |
| "tháng này vs tháng trước" | `compare_energy(mode=month_vs_last_month)` |
| "thiết bị nào dùng nhiều nhất / ít nhất" | `get_device_ranking` |
| "so sánh các thiết bị" | `compare_energy(mode=between_devices)` |
| "lời khuyên / tiết kiệm / gợi ý" | `get_energy_advice` |
| "tiền điện / kWh hôm nay / tháng" | `get_energy_summary` |
| "điện áp / ampe / watt" | `get_device_telemetry` |
| "bật / tắt thiết bị" | `list_devices` rồi `control_device` |

## Quy tắc định dạng:
- Trả lời bằng **tiếng Việt** (trừ khi người dùng hỏi tiếng Anh).
- So sánh dùng ↑ (tăng) / ↓ (giảm) và % rõ ràng.
- Lời khuyên phải cụ thể với số liệu thực tế từ tool, không chung chung.
- Dùng emoji ✅ ⚡ 💡 🔌 📈 📉 🏆 cho sinh động, súc tích.
"""

# Tool schema builder
def _build_tools() -> list:
    """Build all 7 Gemini function declarations."""
    return [
        genai_types.Tool(
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
                        "- 'tuần này so tuần trước' / 'tuần này dùng bao nhiêu' → mode=week_vs_last_week\n"
                        "- 'tháng này so tháng trước' / 'tháng này dùng nhiều hơn không' → mode=month_vs_last_month\n"
                        "- 'thiết bị nào dùng nhiều' / 'so sánh các thiết bị' → mode=between_devices\n"
                        "Tool này CÓ KHẢ NĂNG lấy dữ liệu ngày hôm qua, tuần trước và tháng trước từ hệ thống."
                    ),
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            "mode": genai_types.Schema(
                                type=genai_types.Type.STRING,
                                enum=["day_vs_yesterday", "week_vs_last_week", "month_vs_last_month", "between_devices"],
                                description=(
                                    "day_vs_yesterday: hôm nay vs hôm qua | "
                                    "week_vs_last_week: tuần này (T2-CN) vs tuần trước | "
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
            ]
        )
    ]


# Shared helper: fetch kWh delta for one device over a time window
def _fetch_kwh_for_period(device_id: str, start_ts: int, end_ts: int) -> float:
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
        resp = requests.get(url, headers=s.HEADERS, params=params, timeout=20)
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
        return round(max(0.0, total), 4)
    except Exception as exc:
        logging.warning("_fetch_kwh_for_period %s: %s", device_id, exc)
        return 0.0


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
    if device_id not in s.CUSTOM_CB_DEVICES:
        return {"success": False, "message": f"Không tìm thấy thiết bị ID '{device_id}'."}
    name = device_name or s.CUSTOM_CB_DEVICES[device_id].get("name", device_id)
    success, result = s.send_rpc_to_device(device_id, action)
    if success:
        if device_id in s.latest_data:
            s.latest_data[device_id].setdefault("attributes", {})["POWER"] = action.upper()
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
    device_ids = [device_id] if device_id else list(s.CUSTOM_CB_DEVICES.keys())
    if not device_ids:
        device_ids = s.get_devices_from_group()

    if period == "day":
        start_ts = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    else:
        start_ts = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    end_ts = int(now.timestamp() * 1000)

    total_kwh = sum(_fetch_kwh_for_period(did, start_ts, end_ts) for did in device_ids)
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
        # Current week: Monday 00:00 → now
        days_since_monday = now.weekday()  # 0=Mon, 6=Sun
        this_week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        this_week_end   = now
        last_week_start = this_week_start - timedelta(weeks=1)
        last_week_end   = this_week_start - timedelta(seconds=1)

        this_kwh = round(sum(_fetch_kwh_for_period(d,
            int(this_week_start.timestamp() * 1000),
            int(this_week_end.timestamp()   * 1000)) for d in device_ids), 4)
        last_kwh = round(sum(_fetch_kwh_for_period(d,
            int(last_week_start.timestamp() * 1000),
            int(last_week_end.timestamp()   * 1000)) for d in device_ids), 4)
        change = pct(this_kwh, last_kwh)

        # Week label: "Tuần 16/4 – 18/4"
        this_label = f"Tuần này ({this_week_start.strftime('%d/%m')}–{this_week_end.strftime('%d/%m')})"
        last_label = f"Tuần trước ({last_week_start.strftime('%d/%m')}–{last_week_end.strftime('%d/%m')})"
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

    elif mode == "day_vs_yesterday":
        today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        today_end   = int(now.timestamp() * 1000)
        yest_start  = today_start - 86_400_000
        yest_end    = today_start - 1

        today_kwh = round(sum(_fetch_kwh_for_period(d, today_start, today_end) for d in device_ids), 4)
        yest_kwh  = round(sum(_fetch_kwh_for_period(d, yest_start,  yest_end)  for d in device_ids), 4)
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

        this_kwh = round(sum(_fetch_kwh_for_period(d, this_start, this_end) for d in device_ids), 4)
        last_kwh = round(sum(_fetch_kwh_for_period(d,
            int(last_month_start.timestamp() * 1000),
            int(last_month_end.timestamp() * 1000)) for d in device_ids), 4)
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
        per_device  = []
        for did in device_ids:
            meta = s.CUSTOM_CB_DEVICES.get(did, {})
            kwh  = _fetch_kwh_for_period(did, today_start, today_end)
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

    ranked = []
    for did in device_ids:
        meta  = s.CUSTOM_CB_DEVICES.get(did, {})
        attrs = s.latest_data.get(did, {}).get("attributes", {})
        kwh   = _fetch_kwh_for_period(did, start_ts, end_ts)
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

    today_kwh = 0.0
    yest_kwh  = 0.0
    month_kwh = 0.0
    snapshots = []

    for did in device_ids:
        meta = s.CUSTOM_CB_DEVICES.get(did, {})
        info = s.latest_data.get(did, {})
        tel  = info.get("telemetry", {})
        attr = info.get("attributes", {})

        def sf(v):
            try: return float(v)
            except: return None

        d_today = _fetch_kwh_for_period(did, today_start, today_end)
        d_yest  = _fetch_kwh_for_period(did, yest_start,  yest_end)
        d_month = _fetch_kwh_for_period(did, month_start,  today_end)
        today_kwh += d_today
        yest_kwh  += d_yest
        month_kwh += d_month

        snapshots.append({
            "name":           meta.get("name", did),
            "location":       meta.get("location", "N/A"),
            "power_state":    attr.get("POWER", "N/A"),
            "power_w":        sf(tel.get("ENERGY-Power")),
            "kwh_today":      d_today,
            "kwh_yesterday":  d_yest,
            "kwh_month":      d_month,
        })

    snapshots.sort(key=lambda x: x["kwh_today"], reverse=True)
    today_kwh = round(today_kwh, 4)
    yest_kwh  = round(yest_kwh,  4)
    month_kwh = round(month_kwh, 4)

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

    max_iterations = 8
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

        try:
            response = chat.send_message(tool_response_parts)
        except Exception as exc:
            logging.error("Gemini tool result send error: %s", exc)
            return f"Lỗi gửi kết quả tool: {exc}", history

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
        "tools_count":         7,
    })
