"""History page for NOHTUS WMS."""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from nohtus.auth import is_admin
from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only


def _norm(value, fallback="-"):
    text = str(value if value is not None else "").strip()
    return text if text else fallback


def _adjust_inventory_qty(cur, *, company, product_name, warehouse_name, lot, exp_date, location, delta):
    company = _norm(company, "")
    product_name = _norm(product_name, "")
    warehouse_name = _norm(warehouse_name, "")
    lot = _norm(lot)
    exp_date = _norm(exp_date)
    location = _norm(location, "")
    delta = int(delta or 0)
    if not company or not product_name or not location or delta == 0:
        return
    row = cur.execute(
        """
        SELECT id, qty FROM inventory
        WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=? AND lot=? AND exp_date=? AND location=?
        """,
        (company, product_name, warehouse_name, lot, exp_date, location),
    ).fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row:
        inv_id, current_qty = int(row[0]), int(row[1] or 0)
        new_qty = current_qty + delta
        if new_qty < 0:
            raise ValueError(f"재고 원복 후 수량이 음수가 됩니다: {company} / {location} / {product_name} / {lot} / {exp_date}")
        cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (new_qty, now, inv_id))
    else:
        if delta < 0:
            raise ValueError(f"차감할 재고를 찾을 수 없습니다: {company} / {location} / {product_name} / {lot} / {exp_date}")
        cur.execute(
            """
            INSERT INTO inventory(company, product_name, warehouse_name, lot, exp_date, location, qty, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (company, product_name, warehouse_name, lot, exp_date, location, delta, now),
        )


def _reverse_transaction(cur, tx):
    tx_type = _norm(tx["tx_type"], "")
    qty = int(tx["qty"] or 0)
    product_name = _norm(tx["product_name"], "")
    warehouse_name = _norm(tx["warehouse_name"], "")
    lot = _norm(tx["lot"])
    exp_date = _norm(tx["exp_date"])

    if tx_type == "입고":
        _adjust_inventory_qty(
            cur,
            company=tx["to_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["to_location"],
            delta=-qty,
        )
    elif tx_type in ["출고지시", "출고"]:
        _adjust_inventory_qty(
            cur,
            company=tx["from_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["from_location"],
            delta=qty,
        )
    elif tx_type == "출고지시취소":
        _adjust_inventory_qty(
            cur,
            company=tx["to_company"] or tx["from_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["to_location"] or tx["from_location"],
            delta=-qty,
        )
    elif tx_type in ["위치이동", "사업장이동", "사업장+위치이동", "비자료전환", "이동"]:
        _adjust_inventory_qty(
            cur,
            company=tx["to_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["to_location"],
            delta=-qty,
        )
        _adjust_inventory_qty(
            cur,
            company=tx["from_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["from_location"],
            delta=qty,
        )
    elif tx_type in ["재고조정", "재고실사"]:
        _adjust_inventory_qty(
            cur,
            company=tx["to_company"] or tx["from_company"],
            product_name=product_name,
            warehouse_name=warehouse_name,
            lot=lot,
            exp_date=exp_date,
            location=tx["to_location"] or tx["from_location"],
            delta=-qty,
        )


def _delete_transaction_ids(tx_ids):
    tx_ids = [int(x) for x in tx_ids if x]
    if not tx_ids:
        return 0
    placeholders = ",".join(["?"] * len(tx_ids))
    with connect() as con:
        con.row_factory = None
        cur = con.cursor()
        rows = cur.execute(
            f"""
            SELECT id, tx_type, product_name, warehouse_name, lot, exp_date,
                   from_company, from_location, to_company, to_location, qty, final_stock
            FROM transactions
            WHERE id IN ({placeholders})
            ORDER BY id DESC
            """,
            tuple(tx_ids),
        ).fetchall()
        cols = [d[0] for d in cur.description]
        for raw in rows:
            tx = dict(zip(cols, raw))
            _reverse_transaction(cur, tx)
        cur.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", tuple(tx_ids))
        con.commit()
    return len(rows)


def page_history():
    from nohtus.services.closing import _infer_customer_from_title
    st.title("이력 조회")

    today = date.today()
    default_start = today.replace(day=1)

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    with filter_col1:
        company = st.selectbox("사업장", ["전체"] + COMPANIES, index=0, key="history_company")
    with filter_col2:
        tx_label = st.selectbox("이력유형", ["전체", "입고", "출고지시", "출고지시취소", "이동", "재고조정", "재고정보수정", "전산재고"], index=0, key="history_tx_label")
    with filter_col3:
        start_date = st.date_input("시작일", value=default_start, key="history_start_date")
    with filter_col4:
        end_date = st.date_input("종료일", value=today, key="history_end_date")

    if start_date and end_date and start_date > end_date:
        st.error("시작일은 종료일보다 늦을 수 없습니다.")
        return

    search_col, customer_col = st.columns(2)
    with search_col:
        term = st.text_input("제품명/로케이션 검색", placeholder="제품명, LOT, 로케이션 일부 입력", key="history_search_term")
    with customer_col:
        customer_term = st.text_input("매출처 검색", placeholder="매출처명 일부 입력", key="history_customer_term")

    filter_key = f"{company}|{tx_label}|{start_date}|{end_date}|{term.strip()}|{customer_term.strip()}"
    if st.session_state.get("history_filter_key") != filter_key:
        st.session_state["history_filter_key"] = filter_key
        st.session_state["history_page"] = 1

    conditions = []
    params = []
    if start_date:
        conditions.append("date(created_at) >= ?")
        params.append(str(start_date))
    if end_date:
        conditions.append("date(created_at) <= ?")
        params.append(str(end_date))
    if company != "전체":
        conditions.append("(from_company=? OR to_company=?)")
        params.extend([company, company])
    if tx_label != "전체":
        if tx_label == "이동":
            conditions.append("tx_type IN ('위치이동','사업장이동','사업장+위치이동','비자료전환','이동')")
        elif tx_label == "전산재고":
            conditions.append("tx_type IN ('기준재고','전산재고')")
        else:
            conditions.append("tx_type=?")
            params.append(tx_label)
    else:
        conditions.append("tx_type NOT IN ('재고조사불러오기','ERP비교','출고','출고확정')")
    if term.strip():
        like = f"%{term.strip()}%"
        conditions.append("(product_name LIKE ? OR lot LIKE ? OR from_location LIKE ? OR to_location LIKE ? OR memo LIKE ?)")
        params.extend([like, like, like, like, like])
    if customer_term.strip():
        matched_order_ids = []
        try:
            orders_for_customer = q("SELECT id, COALESCE(title, '') AS title, COALESCE(customer_name, '') AS customer_name FROM outbound_orders ORDER BY id DESC")
            customers_for_infer = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
            needle = customer_term.strip().lower()
            for r in orders_for_customer.itertuples(index=False):
                title = str(getattr(r, "title", "") or "")
                saved_customer = str(getattr(r, "customer_name", "") or "")
                inferred_customer, _manager = _infer_customer_from_title(title, customers_for_infer)
                if needle in title.lower() or needle in saved_customer.lower() or needle in str(inferred_customer or "").lower():
                    matched_order_ids.append(int(getattr(r, "id")))
        except Exception:
            matched_order_ids = []
        matched_order_ids = sorted(set(matched_order_ids))
        if matched_order_ids:
            order_clauses = []
            for oid in matched_order_ids:
                order_clauses.append("memo LIKE ?")
                params.append(f"%출고지시서 #{oid}%")
            conditions.append("(" + " OR ".join(order_clauses) + ")")
        else:
            conditions.append("1=0")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total_df = q(f"SELECT COUNT(*) AS cnt FROM transactions {where}", tuple(params))
    total_count = int(total_df.iloc[0]["cnt"] or 0) if not total_df.empty else 0
    if total_count == 0:
        st.info("조회된 이력이 없습니다.")
        return

    page_size = 10
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    current_page = int(st.session_state.get("history_page", 1) or 1)
    current_page = max(1, min(current_page, total_pages))
    st.session_state["history_page"] = current_page
    offset = (current_page - 1) * page_size

    df = q(f"""
        SELECT * FROM transactions
        {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, tuple(params + [page_size, offset]))

    start_no = offset + 1
    end_no = min(offset + len(df), total_count)
    st.caption(f"총 {total_count:,}건 / {current_page:,}페이지/{total_pages:,}페이지 / 현재 {start_no:,}~{end_no:,}건 표시")

    final_values = []
    qty_values = []
    for r in df.itertuples():
        typ = str(getattr(r, "tx_type", "") or "")
        qty = int(getattr(r, "qty", 0) or 0)
        qty_values.append(f"{qty:+d}" if typ in ["재고조정", "재고실사"] else str(qty))
        final_stock_value = getattr(r, "final_stock", None)
        final_values.append(int(final_stock_value) if final_stock_value is not None and not pd.isna(final_stock_value) else "")

    show = df.copy()
    tx_ids = show["id"].astype(int).tolist() if "id" in show.columns else []
    show["수량"] = qty_values
    show["최종재고"] = final_values

    order_customer_map = {}
    try:
        order_ids = []
        if "memo" in show.columns:
            for memo_text in show["memo"].fillna("").astype(str).tolist():
                m = re.search(r"출고지시서\s*#(\d+)", memo_text)
                if m:
                    order_ids.append(int(m.group(1)))
        order_ids = sorted(set(order_ids))
        if order_ids:
            placeholders = ",".join(["?"] * len(order_ids))
            orders_df = q(f"SELECT id, COALESCE(title, '') AS title, COALESCE(customer_name, '') AS customer_name FROM outbound_orders WHERE id IN ({placeholders})", tuple(order_ids))
            customers_df = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
            for r in orders_df.itertuples(index=False):
                saved_customer = str(getattr(r, "customer_name", "") or "")
                customer = saved_customer or _infer_customer_from_title(getattr(r, "title", ""), customers_df)[0]
                order_customer_map[int(getattr(r, "id"))] = customer
    except Exception:
        order_customer_map = {}

    def _history_customer_from_memo(memo_text):
        m = re.search(r"출고지시서\s*#(\d+)", str(memo_text or ""))
        return order_customer_map.get(int(m.group(1)), "") if m else ""

    show["매출처"] = show["memo"].apply(_history_customer_from_memo) if "memo" in show.columns else ""

    if "exp_date" in show.columns:
        show["exp_date"] = show["exp_date"].apply(display_date_only)
    rename_cols = {
        "created_at": "일시",
        "actor": "사용자",
        "tx_type": "이력유형",
        "product_name": "제품명",
        "lot": "LOT",
        "exp_date": "유통기한",
        "from_company": "출발사업장",
        "from_location": "출발위치",
        "to_company": "도착사업장",
        "to_location": "도착위치",
        "memo": "메모",
    }
    show = show.rename(columns=rename_cols)
    wanted = ["일시", "사용자", "이력유형", "매출처", "제품명", "LOT", "유통기한", "출발사업장", "출발위치", "도착사업장", "도착위치", "수량", "최종재고", "메모"]
    show = show[[c for c in wanted if c in show.columns]]

    if is_admin():
        admin_show = show.copy()
        admin_show.insert(0, "선택", False)
        edited = st.data_editor(
            admin_show,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in admin_show.columns if c != "선택"],
            column_config={"선택": st.column_config.CheckboxColumn("선택")},
            key="history_admin_delete_editor",
        )
        selected_ids = [tx_ids[i] for i, checked in enumerate(edited["선택"].tolist()) if checked and i < len(tx_ids)]
        if selected_ids:
            st.warning(f"선택한 이력 {len(selected_ids)}건은 삭제 시 재고 수량도 함께 원복됩니다.")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("선택 삭제", type="primary", use_container_width=True):
                    st.session_state["history_delete_pending_ids"] = selected_ids
                    st.rerun()
            with c2:
                st.caption("삭제 대상 이력의 재고 변동을 반대로 적용합니다.")
        pending_ids = st.session_state.get("history_delete_pending_ids") or []
        if pending_ids:
            st.error(f"정말 삭제하시겠습니까? 대상: {len(pending_ids)}건")
            d1, d2 = st.columns([1, 1])
            with d1:
                if st.button("취소", use_container_width=True, key="history_delete_cancel"):
                    st.session_state.pop("history_delete_pending_ids", None)
                    st.rerun()
            with d2:
                if st.button("예, 삭제하고 재고를 원복합니다", type="primary", use_container_width=True, key="history_delete_confirm"):
                    try:
                        deleted = _delete_transaction_ids(pending_ids)
                        st.session_state.pop("history_delete_pending_ids", None)
                        st.success(f"이력 {deleted}건을 삭제하고 재고를 원복했습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    else:
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown(
        """
        <style>
        div[data-testid="stNumberInput"]{
            width:100px!important;
            margin:10px auto 0 auto!important;
        }
        div[data-testid="stNumberInput"] input{
            height:68px!important;
            min-height:68px!important;
            text-align:center!important;
            font-size:16px!important;
        }
        div[data-testid="stNumberInput"] button{
            min-height:34px!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    page_left, page_mid, page_right = st.columns([1, 0.2, 1])
    with page_mid:
        selected_page = st.number_input("페이지", min_value=1, max_value=total_pages, value=current_page, step=1, key="history_page_input", label_visibility="collapsed")
        if int(selected_page) != current_page:
            st.session_state["history_page"] = int(selected_page)
            st.rerun()
