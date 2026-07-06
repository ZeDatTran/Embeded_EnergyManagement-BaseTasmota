#Utility: tính tiền điện theo bậc thang Việt Nam (có VAT 8%).


def calculate_vietnam_electricity_bill(total_kwh: float) -> float:
    tiers = [
        (100, 1984),          # Bậc 1: 0-100 kWh  → 1,984đ/kWh
        (100, 2050),          # Bậc 2: 101-200     → 2,050đ/kWh
        (200, 2380),          # Bậc 3: 201-300     → 2,380đ/kWh
        (200, 2998),          # Bậc 4: 301-400     → 2,998đ/kWh
        (200, 3350),          # Bậc 5: 401-600     → 3,350đ/kWh
        (float('inf'), 3460), # Bậc 6: >600        → 3,460đ/kWh
    ]

    bill = 0.0
    kwh_remaining = total_kwh

    for tier_limit, price in tiers:
        if kwh_remaining <= 0:
            break
        kwh_in_tier = min(kwh_remaining, tier_limit)
        bill += kwh_in_tier * price
        kwh_remaining -= kwh_in_tier

    return round(bill * 1.08, 0)  # VAT 8%, làm tròn về VND
