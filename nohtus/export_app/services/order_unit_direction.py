"""Translate the user-facing conversion direction into the existing stock ratio."""
import math
FORWARD = '주문 1단위당 실물수량'
REVERSE = '실물 1개당 주문수량'


def stored_factor(quantity, direction=FORWARD):
    value = float(quantity)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('환산수량은 0보다 커야 합니다.')
    if direction not in (FORWARD, REVERSE):
        raise ValueError('환산 방향을 선택하세요.')
    factor = 1 / value if direction == REVERSE else value
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('환산수량을 확인하세요.')
    return factor


def editor_values(factor):
    factor = float(factor or 1)
    return (REVERSE, 1 / factor) if 0 < factor < 1 else (FORWARD, factor)
