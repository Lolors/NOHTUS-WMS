from __future__ import annotations

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import connect, q
from nohtus.pages.outbound_business import page_outbound as _page_outbound
from nohtus.services.export_waiting import TRANSPORT_METHODS, ensure_export_waiting_tables, save_export_waiting_order

_ALL_COMPANY_SELECTION_KEYS = ("out_all_company_manual_pick", "out_ignore_company", "out_manual_pick")
_P_MATCH_REQUEST_KEY = "_export_p_match_request"
_P_MATCH_SAVE_KEY = "_export_p_match_pending_save"


def _export_title():
    country = str(st.session_state.get("export_waiting_country") or "").strip()
    buyer = str(st.session_state.get("export_waiting_buyer") or "").strip() or "미지정"
    transport_method = str(st.session_state.get("export_waiting_transport_method") or "").strip() or "미지정"
    return "-".join([part for part in (country, buyer, transport_method) if part]) or "수출대기"


def _load_editing_order():
    order_id = st.session_state.get("export_editing_order_id")
    if not order_id or st.session_state.get("_export_edit_loaded") == int(order_id):
        return
    ensure_export_waiting_tables()
    order = q("SELECT country,buyer,transport_method,export_no,title,status FROM export_waiting_orders WHERE id=?", (int(order_id),))
    if order.empty or str(order.iloc[0]["status"]) != "waiting":
        st.session_state.pop("export_editing_order_id", None)
        return
    items = q("""SELECT source_inventory_id AS id,source_location AS 로케이션,company AS 사업장,
                   product_name AS 제품명,lot AS LOT,exp_date AS 유통기한,qty AS 요청수량
            FROM export_waiting_items WHERE order_id=? ORDER BY id""", (int(order_id),))
    st.session_state["export_waiting_country"] = str(order.iloc[0]["country"] or "")
    st.session_state["export_waiting_buyer"] = str(order.iloc[0].get("buyer") or "") or "미지정"
    method = str(order.iloc[0].get("transport_method") or "").strip()
    st.session_state["export_waiting_transport_method"] = method if method in TRANSPORT_METHODS else "미지정"
    st.session_state["export_waiting_number"] = str(order.iloc[0]["export_no"] or "")
    st.session_state["outbound_cart"] = items.to_dict("records") if not items.empty else []
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
    st.session_state["_export_edit_loaded"] = int(order_id)


def _find_unmatched_p_item(order_id):
    if not order_id:
        return None
    df = q(
        """SELECT i.id,i.company,i.product_name,i.warehouse_name,i.lot,i.exp_date,i.qty,i.source_location,
                  COALESCE(SUM(inv.qty),0) AS p_qty
           FROM export_waiting_items i
           LEFT JOIN inventory inv
             ON inv.company=i.company
            AND inv.product_name=i.product_name
            AND IFNULL(inv.warehouse_name,'')=IFNULL(i.warehouse_name,'')
            AND IFNULL(inv.lot,'-')=IFNULL(i.lot,'-')
            AND IFNULL(inv.exp_date,'-')=IFNULL(i.exp_date,'-')
            AND inv.location='P'
           WHERE i.order_id=? AND COALESCE(i.confirmed,0)=0
           GROUP BY i.id
           HAVING COALESCE(SUM(inv.qty),0) < i.qty
           ORDER BY i.id
           LIMIT 1""",
        (int(order_id),),
    )
    return None if df.empty else df.iloc[0].to_dict()


def _p_inventory_candidates(term=""):
    term = str(term or "").strip()
    params = []
    where = ["location='P'", "COALESCE(qty,0)>0"]
    if term:
        where.append("product_name LIKE ?")
        params.append(f"%{term}%")
    return q(
        f"""SELECT id,company AS 사업장,product_name AS 제품명,
                   IFNULL(warehouse_name,'') AS 창고명,IFNULL(lot,'-') AS LOT,
                   IFNULL(exp_date,'-') AS 유통기한,qty AS P재고
            FROM inventory
            WHERE {' AND '.join(where)}
            ORDER BY product_name,company,lot,exp_date
            LIMIT 200""",
        tuple(params),
    )


def _apply_p_inventory_match(waiting_item_id, inventory_id):
    with connect() as con:
        con.row_factory = None
        row = con.execute(
            """SELECT company,product_name,IFNULL(warehouse_name,''),IFNULL(lot,'-'),
                      IFNULL(exp_date,'-'),qty
               FROM inventory WHERE id=? AND location='P'""",
            (int(inventory_id),),
        ).fetchone()
        if not row:
            raise ValueError("선택한 P 재고를 찾을 수 없습니다.")
        company, product_name, warehouse_name, lot, exp_date, qty = row
        waiting = con.execute("SELECT qty FROM export_waiting_items WHERE id=?", (int(waiting_item_id),)).fetchone()
        if not waiting:
            raise ValueError("연결할 수출대기 품목을 찾을 수 없습니다.")
        if int(qty or 0) < int(waiting[0] or 0):
            raise ValueError(f"선택한 P 재고가 부족합니다. 필요 {int(waiting[0] or 0)}EA / 현재 {int(qty or 0)}EA")
        con.execute(
            """UPDATE export_waiting_items
               SET company=?,product_name=?,warehouse_name=?,lot=?,exp_date=?
               WHERE id=?""",
            (company, product_name, warehouse_name, lot, exp_date, int(waiting_item_id)),
        )
        con.commit()


def _finish_export_save(result):
    st.session_state["_outbound_last_success"] = (
        f"수출대기 등록 완료: {result['title']} / 총 {result['total_qty']}EA → 로케이션 P"
    )
    for key in [
        "export_waiting_number", "export_waiting_country", "export_waiting_buyer",
        "export_waiting_transport_method", "export_waiting_auto_title",
        "export_editing_order_id", "_export_edit_loaded", _P_MATCH_REQUEST_KEY, _P_MATCH_SAVE_KEY,
    ]:
        st.session_state.pop(key, None)


def _render_p_match_dialog():
    request = st.session_state.get(_P_MATCH_REQUEST_KEY)
    pending = st.session_state.get(_P_MATCH_SAVE_KEY)
    if not request or not pending:
        return

    dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

    def body():
        old_name = str(request.get("product_name") or "")
        st.warning(
            f"P 로케이션에서 기존 제품명 ‘{old_name}’과 정확히 일치하는 재고를 찾지 못했습니다. "
            "제품 이름이 변경된 경우 아래에서 현재 제품명을 검색해 연결하세요."
        )
        st.caption(
            f"기존 정보: {request.get('company','-')} / LOT {request.get('lot','-')} / "
            f"유통기한 {request.get('exp_date','-')} / 필요 {int(request.get('qty') or 0)}EA"
        )
        term = st.text_input(
            "P 로케이션 제품 검색",
            value=old_name,
            placeholder="현재 제품명 일부를 입력하세요",
            key=f"export_p_match_term_{request.get('id')}",
        )
        candidates = _p_inventory_candidates(term)
        if candidates.empty:
            st.info("검색 결과가 없습니다. 제품명의 다른 일부를 입력해 보세요.")
            return
        labels = [
            f"{r['제품명']} | {r['사업장']} | LOT {r['LOT']} | {r['유통기한']} | P재고 {int(r['P재고'] or 0)}EA"
            for _, r in candidates.iterrows()
        ]
        selected_label = st.selectbox("연결할 P 재고", labels, key=f"export_p_match_select_{request.get('id')}")
        selected_index = labels.index(selected_label)
        selected = candidates.iloc[selected_index]

        c1, c2 = st.columns(2)
        with c1:
            if st.button("닫기", use_container_width=True, key=f"export_p_match_close_{request.get('id')}"):
                st.session_state.pop(_P_MATCH_REQUEST_KEY, None)
                st.session_state.pop(_P_MATCH_SAVE_KEY, None)
                st.rerun()
        with c2:
            if st.button("이 재고로 연결하고 저장", type="primary", use_container_width=True, key=f"export_p_match_apply_{request.get('id')}"):
                try:
                    _apply_p_inventory_match(int(request["id"]), int(selected["id"]))
                    st.session_state.pop(_P_MATCH_REQUEST_KEY, None)
                    result = save_export_waiting_order(
                        pending["cart"],
                        country=pending["country"],
                        buyer=pending["buyer"],
                        transport_method=pending["transport_method"],
                        export_no=pending["export_no"],
                        editing_order_id=pending["editing_order_id"],
                    )
                    _finish_export_save(result)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if dialog_api:
        @dialog_api("P 로케이션 제품 연결")
        def _dialog():
            body()
        _dialog()
    else:
        st.markdown("### P 로케이션 제품 연결")
        body()


def page_export_waiting():
    ensure_export_waiting_tables()
    _load_editing_order()
    for key in _ALL_COMPANY_SELECTION_KEYS:
        st.session_state[key] = True

    original_save = outbound_page.save_outbound_order
    original_update = outbound_page.update_outbound_order
    original_q = outbound_page.q
    original_renderer = outbound_page._render_last_sale_importer
    original_title, original_caption, original_markdown = st.title, st.caption, st.markdown
    original_button, original_success, original_rerun = st.button, st.success, st.rerun
    original_text_input, original_checkbox, original_info = st.text_input, st.checkbox, st.info

    st.session_state.pop("editing_order_id", None)
    st.session_state.pop("editing_order_title", None)
    st.session_state["_outbound_screen_mode"] = "export_waiting"
    completed = {"done": False, "message": ""}
    fields_rendered = {"done": False}

    def patched_save(cart, title="", memo=""):
        country = str(st.session_state.get("export_waiting_country") or "").strip()
        export_no = str(st.session_state.get("export_waiting_number") or "").strip()
        buyer = str(st.session_state.get("export_waiting_buyer") or "").strip() or "미지정"
        transport_method = str(st.session_state.get("export_waiting_transport_method") or "").strip() or "미지정"
        if not country:
            raise ValueError("국가는 필수 입력값입니다.")
        if not export_no:
            raise ValueError("수출번호는 필수 입력값입니다.")

        editing_order_id = st.session_state.get("export_editing_order_id")
        unmatched = _find_unmatched_p_item(editing_order_id)
        if unmatched:
            st.session_state[_P_MATCH_REQUEST_KEY] = unmatched
            st.session_state[_P_MATCH_SAVE_KEY] = {
                "cart": [dict(x) for x in (cart or [])],
                "country": country,
                "buyer": buyer,
                "transport_method": transport_method,
                "export_no": export_no,
                "editing_order_id": editing_order_id,
            }
            raise ValueError("제품명이 변경된 P 재고를 직접 연결해 주세요. 아래 검색창이 열렸습니다.")
        result = save_export_waiting_order(
            cart,
            country=country,
            buyer=buyer,
            transport_method=transport_method,
            export_no=export_no,
            editing_order_id=editing_order_id,
        )
        completed["done"] = True
        completed["message"] = f"수출대기 등록 완료: {result['title']} / 총 {result['total_qty']}EA → 로케이션 P"
        return 0

    def patched_q(sql, params=()):
        normalized = " ".join(str(sql or "").lower().split())
        if " from customers " in f" {normalized} ":
            return pd.DataFrame()
        return original_q(sql, params)

    def patched_title(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "출고지시":
            body = "수출대기 수정" if st.session_state.get("export_editing_order_id") else "수출대기 등록"
        return original_title(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        if isinstance(body, str):
            if "출고지시 저장 시" in body:
                body = "등록 완료 시 선택 재고는 같은 사업장의 P로 이동합니다. 국가는 필수이고 바이어와 운송방식은 미지정으로 둘 수 있습니다."
            else:
                body = body.replace("출고지시", "수출대기")
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "### 매출처":
            result = original_markdown("### 주문 정보", *args, **kwargs)
            if not fields_rendered["done"]:
                fields_rendered["done"] = True
                if "export_waiting_buyer" not in st.session_state:
                    st.session_state["export_waiting_buyer"] = "미지정"
                if "export_waiting_transport_method" not in st.session_state:
                    st.session_state["export_waiting_transport_method"] = "미지정"
                c1, c2, c3, c4 = st.columns(4, gap="medium")
                with c1:
                    original_text_input("국가 *", placeholder="필수 입력", key="export_waiting_country")
                with c2:
                    original_text_input("바이어", placeholder="미지정", key="export_waiting_buyer")
                with c3:
                    st.selectbox("운송방식", TRANSPORT_METHODS, key="export_waiting_transport_method")
                with c4:
                    original_text_input("수출번호 *", placeholder="필수 입력", key="export_waiting_number")
            return result
        if isinstance(body, str):
            body = body.replace("### 출고지시 장바구니", "### 수출대기 장바구니")
        return original_markdown(body, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        key = kwargs.get("key")
        if key in {"out_customer_term", "out_customer_manual_name"}:
            return ""
        if label == "출고지시서 제목":
            st.session_state["export_waiting_auto_title"] = _export_title()
            return original_text_input("수출대기 제목", disabled=True, key="export_waiting_auto_title")
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "out_customer_direct":
            return False
        if key in _ALL_COMPANY_SELECTION_KEYS or label == "사업장 구분 없이 특정 재고 선택":
            if key:
                st.session_state[key] = True
            return True
        return original_checkbox(label, *args, **kwargs)

    def patched_info(body, *args, **kwargs):
        text = str(body or "")
        if any(x in text for x in ["거래처를 검색", "매출처를 선택", "직접입력 매출처", "저장된 매출처"]):
            return None
        return original_info(body, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        label = {
            "지시완료 저장": "수출대기 수정 완료" if st.session_state.get("export_editing_order_id") else "수출대기 등록 완료",
            "선택 재고 장바구니에 담기": "선택 재고 수출대기 장바구니에 담기",
        }.get(label, label)
        return original_button(label, *args, **kwargs)

    def patched_rerun(*args, **kwargs):
        if completed["done"]:
            st.session_state["_outbound_last_success"] = completed["message"]
            completed["done"] = False
            for key in ["export_waiting_number", "export_waiting_country", "export_waiting_buyer", "export_waiting_transport_method", "export_waiting_auto_title", "export_editing_order_id", "_export_edit_loaded"]:
                st.session_state.pop(key, None)
        return original_rerun(*args, **kwargs)

    outbound_page.save_outbound_order = patched_save
    outbound_page.update_outbound_order = lambda order_id, title, cart: patched_save(cart, title)
    outbound_page.q = patched_q
    outbound_page._render_last_sale_importer = lambda: None
    st.title, st.caption, st.markdown = patched_title, patched_caption, patched_markdown
    st.text_input, st.checkbox, st.info = patched_text_input, patched_checkbox, patched_info
    st.button, st.success, st.rerun = patched_button, lambda body, *a, **k: original_success(str(body).replace("출고지시", "수출대기"), *a, **k), patched_rerun
    try:
        result = _page_outbound()
        _render_p_match_dialog()
        return result
    finally:
        outbound_page.save_outbound_order, outbound_page.update_outbound_order, outbound_page.q = original_save, original_update, original_q
        outbound_page._render_last_sale_importer = original_renderer
        st.title, st.caption, st.markdown = original_title, original_caption, original_markdown
        st.text_input, st.checkbox, st.info = original_text_input, original_checkbox, original_info
        st.button, st.success, st.rerun = original_button, original_success, original_rerun
