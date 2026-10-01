"""입고 단위 환산과 발주 단위 수량 집계."""
from decimal import Decimal, InvalidOperation
from services.statement_returns import return_info


def conversion_factor(row):
    raw = row.get("단위환산계수", 1)
    if raw is None or str(raw).strip() in ("", "None"):
        return 1
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("단위환산계수는 1 이상의 정수여야 합니다.") from exc
    if not value.is_finite() or value < 1 or value != value.to_integral_value():
        raise ValueError("단위환산계수는 1 이상의 정수여야 합니다.")
    return int(value)


def order_quantity(row):
    """반품 전 누적 입고량을 발주 단위로 환산한다. 반품은 미입고가 아니다."""
    _, returned, _ = return_info(row.get("가격적용여부", ""))
    gross = Decimal(str(row.get("입고수량", 0) or 0)) + returned
    return float(gross / conversion_factor(row))


def convert_quantity(quantity, factor):
    factor = conversion_factor({"단위환산계수": factor})
    try:
        result = Decimal(str(quantity)) * factor
    except InvalidOperation as exc:
        raise ValueError("변환할 수량을 확인하세요.") from exc
    if not result.is_finite() or result < 0 or result != result.to_integral_value():
        raise ValueError("변환 후 입고수량은 0 이상의 정수여야 합니다.")
    return int(result)
