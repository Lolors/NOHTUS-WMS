"""거래명세서 부분 반품 규칙. 기존 반품 표식과 순입고 저장 형식을 유지한다."""
from datetime import datetime
from decimal import Decimal, InvalidOperation


def return_marker(quantity: int, amount: int) -> str:
    return f"반품:{quantity}:{amount}:{datetime.now():%Y-%m-%d %H:%M:%S}"


def return_info(value) -> tuple[bool, int, int]:
    text = str(value or "").strip()
    if not text.startswith("반품:"):
        return False, 0, 0
    parts = text.split(":", 3)
    try:
        return True, max(0, int(float(parts[1] or 0))), max(0, int(float(parts[2] or 0)))
    except (IndexError, TypeError, ValueError):
        raise ValueError("반품 기록의 수량/금액을 확인할 수 없습니다.")


def quantity_value(value, label="반품수량") -> int:
    try:
        number = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label}은 0 이상의 정수로 입력하세요.")
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"{label}은 0 이상의 정수로 입력하세요.")
    return int(number)


def return_values(total_quantity, total_amount, returned_quantity):
    total = quantity_value(total_quantity, "총 입고수량")
    returned = quantity_value(returned_quantity)
    if returned > total:
        raise ValueError(f"반품수량은 총 입고수량({total:,})을 초과할 수 없습니다.")
    amount = max(0, int(total_amount))
    returned_amount = (amount * returned + total // 2) // total if total else 0
    return total - returned, amount - returned_amount, (return_marker(returned, returned_amount) if returned else "적용")
