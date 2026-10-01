"""합산 명세서의 연결 발주 및 품목별 입고 귀속 규칙."""
import json
import pandas as pd


def linked_order_ids(statement):
    raw = str(statement.get("연결발주ID", "") or "").strip()
    if raw:
        try:
            values = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("연결 발주 정보가 올바르지 않습니다.") from exc
        if not isinstance(values, list):
            raise ValueError("연결 발주 정보가 올바르지 않습니다.")
    else:
        values = [statement.get("발주ID", "")]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def encode_order_ids(values):
    return json.dumps(list(dict.fromkeys(str(value) for value in values)), ensure_ascii=False)


def item_order_id(row, statement_order):
    return str(row.get("입고발주ID", "") or statement_order.get(str(row.get("명세서ID", "")), ""))


def receipts_for_order(statements, statement_items, order_id):
    if statement_items.empty:
        return statement_items.copy()
    primary = dict(zip(statements["명세서ID"].astype(str), statements["발주ID"].astype(str)))
    return statement_items.loc[statement_items.apply(lambda row: item_order_id(row, primary) == str(order_id), axis=1)].copy()


def validate_links(order_ids, orders, vendor_name, items):
    ids = list(dict.fromkeys(str(oid) for oid in order_ids))
    if not ids:
        raise ValueError("연결할 발주서를 한 개 이상 선택하세요.")
    lookup = orders.set_index("발주ID")["거래처명"].astype(str).to_dict()
    if any(oid not in lookup or lookup[oid] != str(vendor_name) for oid in ids):
        raise ValueError("같은 거래처의 발주서만 연결할 수 있습니다.")
    if any(str(row.get("입고발주ID", "") or "") not in ids for _, row in items.iterrows()):
        raise ValueError("모든 품목의 입고 발주를 연결 발주서 중에서 선택하세요.")
    return ids


def save_statement_bundle(purchase_module, statements, items, prices):
    writer = getattr(purchase_module, "save_statement_bundle", None)
    if callable(writer):
        writer(statements, items, prices)
        return
    # CSV 기반 구버전 실행 환경 호환.
    for path, frame, columns in [
        (purchase_module.STATEMENTS_FILE, statements, purchase_module.STATEMENT_COLUMNS),
        (purchase_module.STATEMENT_ITEMS_FILE, items, purchase_module.STATEMENT_ITEM_COLUMNS),
        (purchase_module.PRICE_HISTORY_FILE, prices, purchase_module.PRICE_HISTORY_COLUMNS),
    ]:
        purchase_module.save_table(path, frame, columns)


def assert_order_not_shared(conn, order_id):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(statements)")}
    if "linked_order_ids" not in columns:
        return
    for primary, encoded in conn.execute("SELECT order_id, linked_order_ids FROM statements"):
        ids = linked_order_ids({"발주ID": primary, "연결발주ID": encoded})
        if str(order_id) in ids and len(ids) > 1:
            raise ValueError("여러 발주와 연결된 명세서가 있습니다. 거래명세서 내역에서 연결과 품목 배분을 먼저 수정하세요.")


def reassign_receipt_source(row, order_items):
    """발주 변경 시 해당 발주의 원품목으로 입고 귀속 정보를 맞춘다."""
    row = dict(row)
    source = str(row.get("입고발주ID", ""))
    if source == row.get("_original_order_id", source):
        return row
    candidates = order_items[order_items["발주ID"].astype(str) == source]
    match = pd.DataFrame()
    for code, name in [(row.get("원발주제품코드", ""), row.get("원발주제품명", "")),
                       (row.get("제품코드", ""), row.get("정식제품명", ""))]:
        if str(code or "").strip():
            match = candidates[candidates["제품코드"].astype(str) == str(code)]
        else:
            match = candidates[candidates["정식제품명"].astype(str) == str(name)]
            for key, original in [("규격", "원발주규격"), ("단위", "원발주단위")]:
                match = match[match[key].astype(str) == str(row.get(original, ""))]
        if not match.empty:
            break
    if match.empty:
        raise ValueError(f"{row.get('정식제품명', '')}: 선택한 발주 {source}에서 일치하는 품목을 찾을 수 없습니다.")
    identity = ["제품코드", "정식제품명", "규격", "단위"]
    if len(match[identity].drop_duplicates()) != 1:
        raise ValueError("선택한 발주에 규격이 다른 동일 제품이 있습니다. 원발주 품목을 확인하세요.")
    original = match.iloc[0]
    for target, field in [("원발주제품코드", "제품코드"), ("원발주제품명", "정식제품명"),
                          ("원발주규격", "규격"), ("원발주단위", "단위")]:
        row[target] = original.get(field, "")
    row["발주수량"] = pd.to_numeric(match["수량"], errors="coerce").fillna(0).sum()
    row["입고유형"] = "대체입고" if str(row.get("제품코드", "")) != str(original["제품코드"]) or str(row.get("정식제품명", "")) != str(original["정식제품명"]) else "정상입고"
    return row
