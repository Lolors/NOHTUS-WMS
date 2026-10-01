"""겹치는 기간의 매입 파일을 거래 행 수를 보존하며 누적 반영한다."""
from collections import defaultdict, deque
from decimal import Decimal
import json
import unicodedata


FIELDS = ("purchase_date", "supplier_name", "erp_product_name", "specification", "quantity", "unit_price", "note")
ERP_FIELDS = ("번호", "명세서일자", "명세서번호", "거래처코드", "제품코드", "매입구분", "재고위치", "제조번호", "유효기한", "등록일자")


def text(value):
    return unicodedata.normalize("NFC", str(value or "").strip())


def fingerprint(row):
    values = []
    for key in FIELDS:
        value = row.get(key)
        if key in ("quantity", "unit_price"):
            value = str(Decimal(str(value)).normalize()) if value is not None else ""
        values.append(text(value))
    return tuple(values)


def source_identity(item, clean, normalize_date):
    values = []
    for field in ERP_FIELDS:
        value = clean(item.get(field))
        if field in ("명세서일자", "유효기한") and value:
            value = normalize_date(item.get(field)) or value
        elif field in ("번호", "명세서번호", "거래처코드", "제품코드") and value.endswith(".0"):
            value = value[:-2]
        values.append(text(value))
    return json.dumps(values, ensure_ascii=False) if any(values) else ""


class ExistingRows:
    """한 파일에 같은 내용이 두 행이면 실제 거래 두 행으로 보존한다."""
    def __init__(self, cursor, company):
        fields = ("id", *FIELDS, "source_identity")
        rows = cursor.execute(f"SELECT {','.join(fields)} FROM purchase_history WHERE business_name=? ORDER BY id", (company,)).fetchall()
        self.exact = defaultdict(deque)
        self.legacy = defaultdict(deque)
        self.all = defaultdict(deque)
        self.used = set()
        for values in rows:
            row = dict(zip(fields, values)); key = fingerprint(row)
            self.all[key].append(row["id"])
            if row["source_identity"]:
                self.exact[(key, row["source_identity"])].append(row["id"])
            else:
                self.legacy[key].append(row["id"])

    def take(self, row, identity):
        key = fingerprint(row)
        pools = [self.exact[(key, identity)], self.legacy[key]] if identity else [self.all[key]]
        for pool in pools:
            while pool:
                id = pool.popleft()
                if id not in self.used:
                    self.used.add(id)
                    return id
        return None
