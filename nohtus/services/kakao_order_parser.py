from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedOrderItem:
    product_keyword: str
    qty: int
    unit: str
    raw_line: str


@dataclass(frozen=True)
class ParsedKakaoOrder:
    customer_keyword: str
    items: list[ParsedOrderItem]
    note: str


_IGNORE_ONLY_PATTERNS = [
    r"^부탁\s*드려요[.!~\s]*$",
    r"^부탁\s*드립니다[.!~\s]*$",
    r"^감사\s*합니다[.!~\s]*$",
    r"^감사\s*해요[.!~\s]*$",
    r"^보내\s*주세요[.!~\s]*$",
    r"^출고\s*부탁.*$",
]

_ITEM_RE = re.compile(
    r"^(?P<product>.+?)\s*(?P<qty>\d+)\s*(?P<unit>통|개|박스|box|BOX|ea|EA|v|V|바이알|세트|set|SET)?\s*(?:부탁.*|보내.*|출고.*|주세요.*)?$"
)

_ONE_LINE_RE = re.compile(
    r"^(?P<customer>\S+)\s+(?P<product>.+?)\s*(?P<qty>\d+)\s*(?P<unit>통|개|박스|box|BOX|ea|EA|v|V|바이알|세트|set|SET)?$"
)

_TRAILING_REQUEST_RE = re.compile(r"\s*(?:부탁.*|보내.*|출고.*|주세요.*|전달.*)$")


def _clean_line(value: str) -> str:
    value = str(value or "").replace("\u200b", " ").strip()
    value = re.sub(r"[\t ]+", " ", value)
    return value.strip(" ,./~!\u3000")


def _is_ignore_only(line: str) -> bool:
    return any(re.match(pattern, line) for pattern in _IGNORE_ONLY_PATTERNS)


def _parse_item_line(line: str) -> ParsedOrderItem | None:
    cleaned = _clean_line(_TRAILING_REQUEST_RE.sub("", line))
    match = _ITEM_RE.match(cleaned)
    if not match:
        return None

    product = _clean_line(match.group("product"))
    qty_text = match.group("qty")
    unit = _clean_line(match.group("unit") or "")
    if not product or not qty_text:
        return None

    return ParsedOrderItem(
        product_keyword=product,
        qty=max(int(qty_text), 1),
        unit=unit,
        raw_line=line,
    )


def _parse_single_line_order(line: str) -> ParsedKakaoOrder | None:
    compact = _clean_line(_TRAILING_REQUEST_RE.sub("", line))
    match = _ONE_LINE_RE.match(compact)
    if not match:
        return None
    customer = _clean_line(match.group("customer"))
    product = _clean_line(match.group("product"))
    qty = max(int(match.group("qty")), 1)
    unit = _clean_line(match.group("unit") or "")
    if not customer or not product:
        return None
    return ParsedKakaoOrder(
        customer_keyword=customer,
        items=[ParsedOrderItem(product_keyword=product, qty=qty, unit=unit, raw_line=line)],
        note="",
    )


def parse_kakao_order(text: str) -> ParsedKakaoOrder:
    """카카오톡 주문 문장을 출고지시 입력용 키워드로 가볍게 분해한다.

    첫 버전은 API 호출 없이 규칙 기반으로 처리한다.
    - 첫 번째 품목 줄 이전의 첫 일반 줄은 매출처 키워드로 본다.
    - 숫자가 붙은 줄은 품목/수량/단위로 본다.
    - 부탁/감사 같은 문장은 메모로만 남긴다.
    """
    lines = [_clean_line(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]

    if len(lines) == 1:
        single = _parse_single_line_order(lines[0])
        if single:
            return single

    customer = ""
    items: list[ParsedOrderItem] = []
    note_lines: list[str] = []

    for line in lines:
        if _is_ignore_only(line):
            note_lines.append(line)
            continue

        item = _parse_item_line(line)
        if item:
            items.append(item)
            continue

        if not customer and not items:
            customer = line
        else:
            note_lines.append(line)

    return ParsedKakaoOrder(customer_keyword=customer, items=items, note=" / ".join(note_lines))
