from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only
from nohtus.services.export_waiting import (
    TRANSPORT_METHODS,
    cancel_export_waiting_order,
    confirm_export_waiting_items,
    ensure_export_waiting_tables,
    merge_export_waiting_orders,
)
from nohtus.services.export_waiting_excel import (
    build_export_waiting_erp_sales_rows,
    export_waiting_erp_sales_excel_bytes,
    safe_export_no_for_filename,
)

STATUS_LABELS = {"waiting": "수출대기", "partial": "일부 확정", "confirmed": "수출확정", "cancelled": "취소됨"}
_SELECTED_ORDER_KEY = "saved_export_waiting_selected_order_id"
_EDITABLE_ORDER_FIELDS = {
    "country": ("국가", "country"),
    "buyer": ("바이어", "buyer"),
    "transport_method": ("운송방식", "transport_method"),
    "export_no": ("수출번호", "export_no"),
}


def _fit_summary_metric_values():
    st.markdown("""
    <style>
    div[data-testid="stMetricValue"]{overflow:visible!important}
    div[data-testid="stMetricValue"]>div{max-width:100%!important;overflow:visible!important;text-overflow:clip!important;white-space:nowrap!important;line-height:1.15!important}
    </style>
    """, unsafe_allow_html=True)
    components.html("""
    <script>(function(){function fit(){try{const d=window.parent.document;d.querySelectorAll('[data-testid="stMetricValue"] > div').forEach(v=>{const b=v.parentElement;if(!b||!v.textContent.trim())return;v.style.fontSize='';let s=parseFloat(window.parent.getComputedStyle(v).fontSize)||32;const a=Math.max(0,b.clientWidth-2);while(s>13&&v.scrollWidth>a){s-=1;v.style.fontSize=s+'px';}})}catch(e){}}fit();setTimeout(fit,80);setTimeout(fit,250);setTimeout(fit,700);window.parent.addEventListener('resize',fit)})();</script>
    """, height=0, scrolling=False)


def _customer_options(company, term):
    with connect() as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info(customers)").fetchall()}
    if "customer_name" not in columns:
        return pd.DataFrame(columns=["customer_code", "customer_name", "company"])
    code_col = next((c for c in ["customer_code", "erp_code", "code"] if c in columns), None)
    company_col = "company" if "company" in columns else None
    select_code = f"COALESCE({code_col},'')" if code_col else "''"
    select_company = company_col if company_col else "''"
    clauses, params = ["TRIM(COALESCE(customer_name,''))<>''"], []
    if company_col and company:
        clauses.append("company=?")
        params.append(company)
    if str(term or "").strip():
        clauses.append("customer_name LIKE ?")
        params.append(f"%{str(term).strip()}%")
    return q(
        f"SELECT {select_code} AS customer_code, customer_name, {select_company} AS company "
        f"FROM customers WHERE {' AND '.join(clauses)} ORDER BY customer_name LIMIT 100",
        tuple(params),
    )


def _order_items(order_id):
    df = q(
        """SELECT id,company AS 사업장,source_location AS 원래로케이션,
                    CASE WHEN COALESCE(confirmed,0)=1 THEN '-' ELSE waiting_location END AS 현재로케이션,
                    product_name AS 제품명,lot AS LOT,exp_date AS 유통기한,qty AS 수량,
                    COALESCE(confirmed,0) AS confirmed,confirmed_company AS 확정사업장,
                    confirmed_customer_name AS 확정매출처,confirmed_at AS 확정일시
             FROM export_waiting_items WHERE order_id=?
             ORDER BY COALESCE(confirmed,0),company,product_name,lot,exp_date,source_location""",
        (int(order_id),),
    )
    if not df.empty:
        df["유통기한"] = df["유통기한"].apply(display_date_only)
        df["확정상태"] = df["confirmed"].apply(lambda v: "확정완료" if int(v or 0) else "수출대기")
        for col in ["확정사업장", "확정매출처", "확정일시"]:
            df[col] = df[col].fillna("").astype(str).replace("", "-")
    return df


def _order_row_style(row):
    status = str(row.get("__status", ""))
    if status == "confirmed":
        return ["background-color:#dcfce7;color:#166534" for _ in row]
    if status == "cancelled":
        return ["background-color:#f1f3f5;color:#6b7280" for _ in row]
    return ["" for _ in row]


def _normalize_date_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.strftime("%Y-%m-%d")


def _date_value(value):
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return date.today()
    return parsed.date()


def _ensure_order_date_column():
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(export_waiting_orders)").fetchall()}
        if "order_date" not in cols:
            cur.execute("ALTER TABLE export_waiting_orders ADD COLUMN order_date TEXT")
        cur.execute("UPDATE export_waiting_orders SET order_date=NULL WHERE status NOT IN ('partial','confirmed')")
        cur.execute("UPDATE export_waiting_orders SET order_date=DATE(confirmed_at) WHERE status='confirmed' AND TRIM(COALESCE(order_date,''))='' AND TRIM(COALESCE(confirmed_at,''))<>''")
        con.commit()


def _update_export_order_date(order_id, new_date):
    date_text = _normalize_date_text(new_date)
    if not date_text:
        raise ValueError("출고일자를 선택하세요.")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        row = con.execute("SELECT status FROM export_waiting_orders WHERE id=?", (int(order_id),)).fetchone()
        if not row or str(row[0]) != "confirmed":
            raise ValueError("수출확정된 건만 출고일자를 수정할 수 있습니다.")
        con.execute(
            "UPDATE export_waiting_orders SET order_date=?,updated_at=? WHERE id=?",
            (date_text, now, int(order_id)),
        )
        con.commit()


def _update_export_order_metadata(order_id, field, new_value):
    if field not in _EDITABLE_ORDER_FIELDS:
        raise ValueError("수정할 수 없는 수출대기 정보입니다.")

    value = str(new_value or "").strip()
    with connect() as con:
        row = con.execute(
            """SELECT country,buyer,transport_method,export_no
               FROM export_waiting_orders WHERE id=?""",
            (int(order_id),),
        ).fetchone()
        if not row:
            raise ValueError("수정할 수출대기 건을 찾을 수 없습니다.")

        values = {
            "country": str(row[0] or "").strip(),
            "buyer": str(row[1] or "").strip(),
            "transport_method": str(row[2] or "").strip() or "미지정",
            "export_no": str(row[3] or "").strip(),
        }
        values[field] = value

        if not values["country"]:
            raise ValueError("국가를 입력하세요.")
        if not values["export_no"]:
            raise ValueError("수출번호를 입력하세요.")
        if values["transport_method"] not in TRANSPORT_METHODS:
            raise ValueError("운송방식을 항공, 해상, 핸드캐리, 미지정 중에서 선택하세요.")

        buyer_title = values["buyer"] or "미지정"
        title = f"{values['country']}-{buyer_title}-{values['transport_method']}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            """UPDATE export_waiting_orders
               SET country=?,buyer=?,transport_method=?,export_no=?,title=?,updated_at=?
               WHERE id=?""",
            (
                values["country"],
                values["buyer"],
                values["transport_method"],
                values["export_no"],
                title,
                now,
                int(order_id),
            ),
        )
        con.commit()
    return values[field]


@st.dialog("수출대기 정보 수정")
def _edit_export_order_dialog(order_id, field, current_value, order_title):
    if field not in _EDITABLE_ORDER_FIELDS:
        st.error("수정할 수 없는 수출대기 정보입니다.")
        return

    edit_label, _ = _EDITABLE_ORDER_FIELDS[field]
    input_key = f"edit_export_order_dialog_value_{field}_{int(order_id)}"
    current_value = str(current_value or "").strip()

    if field == "transport_method":
        current_transport = current_value or "미지정"
        transport_index = (
            TRANSPORT_METHODS.index(current_transport)
            if current_transport in TRANSPORT_METHODS
            else 0
        )
        edited_value = st.selectbox(
            edit_label,
            TRANSPORT_METHODS,
            index=transport_index,
            key=input_key,
        )
    else:
        edited_value = st.text_input(
            edit_label,
            value=current_value,
            key=input_key,
            placeholder=(
                "비워두면 미지정으로 표시됩니다."
                if field == "buyer"
                else None
            ),
        )

    save_col, cancel_col = st.columns(2)
    with save_col:
        if st.button(
            "저장",
            type="primary",
            use_container_width=True,
            key=f"save_export_order_dialog_{field}_{int(order_id)}",
        ):
            try:
                saved_value = _update_export_order_metadata(order_id, field, edited_value)
                display_value = saved_value or "미지정"
                st.session_state["_export_waiting_message"] = (
                    f"{order_title}의 {edit_label}을(를) {display_value}(으)로 변경했습니다."
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with cancel_col:
        if st.button(
            "취소",
            use_container_width=True,
            key=f"cancel_export_order_dialog_{field}_{int(order_id)}",
        ):
            st.rerun()


def page_saved_export_waiting():
    ensure_export_waiting_tables()
    _ensure_order_date_column()
    st.title("저장된 수출대기")
    st.caption("기간, 국가, 바이어, 제품명으로 검색할 수 있습니다. 취소 건은 기본적으로 숨겨집니다.")
    msg = st.session_state.pop("_export_waiting_message", None)
    if msg:
        st.success(msg)

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    with filter_col1:
        period = st.date_input(
            "기간",
            value=(),
            key="saved_export_waiting_period",
            help="시작일과 종료일을 선택하세요.",
        )
    with filter_col2:
        country_term = st.text_input("국가", placeholder="국가명 일부", key="saved_export_waiting_country")
    with filter_col3:
        buyer_term = st.text_input("바이어", placeholder="바이어명 일부", key="saved_export_waiting_buyer")
    with filter_col4:
        product_search_col, cancelled_col = st.columns([3, 1])
        with product_search_col:
            product_term = st.text_input("제품명", placeholder="제품명 일부", key="saved_export_waiting_product")
        with cancelled_col:
            st.markdown("<div style='height:1.78rem'></div>", unsafe_allow_html=True)
            include_cancelled = st.checkbox("취소 건도 포함", key="saved_export_waiting_include_cancelled")

    clauses = []
    params = []
    if not include_cancelled:
        clauses.append("COALESCE(o.status,'') <> 'cancelled'")
    if country_term.strip():
        clauses.append("COALESCE(o.country,'') LIKE ?")
        params.append(f"%{country_term.strip()}%")
    if buyer_term.strip():
        clauses.append("COALESCE(o.buyer,'') LIKE ?")
        params.append(f"%{buyer_term.strip()}%")
    if product_term.strip():
        clauses.append("EXISTS (SELECT 1 FROM export_waiting_items si WHERE si.order_id=o.id AND COALESCE(si.product_name,'') LIKE ?)")
        params.append(f"%{product_term.strip()}%")

    if isinstance(period, (list, tuple)) and len(period) == 2:
        start_date = _normalize_date_text(period[0])
        end_date = _normalize_date_text(period[1])
        if start_date and end_date:
            clauses.append("DATE(o.order_date) BETWEEN DATE(?) AND DATE(?)")
            params.extend([start_date, end_date])
    elif period:
        selected_date = _normalize_date_text(period[0] if isinstance(period, (list, tuple)) else period)
        if selected_date:
            clauses.append("DATE(o.order_date)=DATE(?)")
            params.append(selected_date)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    orders = q(
        f"""SELECT o.id,o.export_no,o.country,o.buyer,o.transport_method,o.title,o.status,
                    o.erp_company,o.erp_customer_name,o.order_date,o.created_at,o.updated_at,o.confirmed_at,o.cancelled_at,
                    COUNT(i.id) AS total_items,
                    SUM(CASE WHEN COALESCE(i.confirmed,0)=1 THEN 1 ELSE 0 END) AS confirmed_items,
                    GROUP_CONCAT(DISTINCT NULLIF(TRIM(i.product_name),'')) AS product_names
             FROM export_waiting_orders o
             LEFT JOIN export_waiting_items i ON i.order_id=o.id
             {where_sql}
             GROUP BY o.id
             ORDER BY CASE WHEN o.order_date IS NULL OR TRIM(o.order_date)='' THEN 0 ELSE 1 END,
                      o.id DESC,
                      DATE(o.order_date) DESC""",
        tuple(params),
    )
    if orders.empty:
        st.info("검색 조건에 맞는 저장된 수출대기 건이 없습니다.")
        st.session_state.pop(_SELECTED_ORDER_KEY, None)
        return

    orders["total_items"] = pd.to_numeric(orders["total_items"], errors="coerce").fillna(0).astype(int)
    orders["confirmed_items"] = pd.to_numeric(orders["confirmed_items"], errors="coerce").fillna(0).astype(int)
    orders["출고일자"] = orders.apply(
        lambda r: _normalize_date_text(r.get("order_date")) if str(r.get("status")) == "confirmed" else "",
        axis=1,
    )

    def summarize_products(value):
        names = [x.strip() for x in str(value or "").split(",") if x.strip()]
        if not names:
            return "-"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]}, {names[1]}"
        return f"{names[0]}, {names[1]} 외 {len(names) - 2}종"

    view = orders.copy()
    view["상태"] = view["status"].map(STATUS_LABELS).fillna(view["status"])
    view["포함된 품목"] = view["product_names"].apply(summarize_products)
    view = view.rename(
        columns={
            "country": "국가",
            "buyer": "바이어",
            "transport_method": "운송방식",
            "export_no": "수출번호",
            "erp_company": "사업장",
            "erp_customer_name": "ERP 매출처명",
            "created_at": "등록일",
        }
    )
    view["바이어"] = view["바이어"].fillna("").astype(str).replace("", "미지정")
    view["운송방식"] = view["운송방식"].fillna("").astype(str).replace("", "미지정")
    view["__status"] = orders["status"].astype(str).values
    table_columns = ["출고일자", "국가", "바이어", "운송방식", "수출번호", "상태", "포함된 품목", "사업장", "ERP 매출처명", "등록일", "__status"]
    table = view[table_columns].reset_index(drop=True)
    styled = table.style.apply(_order_row_style, axis=1)
    event = st.dataframe(
        styled,
        hide_index=True,
        use_container_width=True,
        key="saved_export_waiting_orders_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={"__status": None},
    )

    selected_rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
    if selected_rows:
        row_index = int(selected_rows[0])
        if 0 <= row_index < len(orders):
            st.session_state[_SELECTED_ORDER_KEY] = int(orders.iloc[row_index]["id"])
    selected_id = int(st.session_state.get(_SELECTED_ORDER_KEY) or orders.iloc[0]["id"])
    matched = orders.index[orders["id"].astype(int) == selected_id].tolist()
    if not matched:
        selected_id = int(orders.iloc[0]["id"])
        st.session_state[_SELECTED_ORDER_KEY] = selected_id
        matched = [orders.index[0]]
    selected = orders.loc[matched[0]]

    order_id, status = int(selected["id"]), str(selected["status"])
    confirmed_count, total_count = int(selected["confirmed_items"] or 0), int(selected["total_items"] or 0)
    st.markdown(f"### {selected['title']}")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    summary_cards = [
        (c1, "status", "상태", STATUS_LABELS.get(status, status), None),
        (c2, "progress", "진행상황", f"{confirmed_count} / {total_count}", None),
        (c3, "country", "국가", str(selected["country"] or "-"), "country"),
        (c4, "buyer", "바이어", str(selected["buyer"] or "미지정"), "buyer"),
        (
            c5,
            "transport_method",
            "운송방식",
            str(selected["transport_method"] or "미지정"),
            "transport_method",
        ),
        (c6, "export_no", "수출번호", str(selected["export_no"] or "-"), "export_no"),
    ]
    for column, card_key, label, value, edit_field in summary_cards:
        with column:
            clicked = st.button(
                f"{label}\n{value}",
                use_container_width=True,
                disabled=edit_field is None,
                key=f"summary_export_order_{card_key}_{order_id}",
                help=f"{label} 수정" if edit_field else None,
            )
            if clicked and edit_field:
                selected_column = _EDITABLE_ORDER_FIELDS[edit_field][1]
                _edit_export_order_dialog(
                    order_id,
                    edit_field,
                    selected[selected_column],
                    str(selected["title"] or ""),
                )

    st.markdown(
        """<style>
        [class*="st-key-summary_export_order_"] button {
            min-height:5.25rem;
            padding:0.65rem 0.75rem;
            align-items:center;
            justify-content:center;
            text-align:center;
        }
        [class*="st-key-summary_export_order_"] button p {
            width:100%;
            margin:0;
            white-space:pre-line;
            line-height:1.2;
            text-align:center;
            font-size:calc(1em + 3pt);
        }
        [class*="st-key-summary_export_order_"] button p::first-line {
            font-size:calc(1em + 2pt);
            font-weight:700;
        }
        [class*="st-key-summary_export_order_"] button:disabled {
            opacity:1;
            color:inherit;
            cursor:default;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    _fit_summary_metric_values()

    if status == "confirmed":
        date_col, save_date_col = st.columns([3, 1])
        with date_col:
            shipment_date = st.date_input(
                "출고일자",
                value=_date_value(selected.get("order_date")),
                key=f"saved_export_waiting_order_date_{order_id}",
            )
        with save_date_col:
            st.markdown("<div style='height:1.78rem'></div>", unsafe_allow_html=True)
            if st.button("출고일자 저장", use_container_width=True, key=f"save_export_order_date_{order_id}"):
                try:
                    _update_export_order_date(order_id, shipment_date)
                    st.session_state["_export_waiting_message"] = f"{selected['title']}의 출고일자를 {_normalize_date_text(shipment_date)}로 변경했습니다."
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if total_count:
        st.progress(confirmed_count / total_count, text=f"{confirmed_count} / {total_count} 품목 확정")

    items = _order_items(order_id)
    total_qty = int(items["수량"].sum()) if not items.empty else 0
    remaining_items = items[items["confirmed"] == 0].copy() if not items.empty else pd.DataFrame()
    remaining_qty = int(remaining_items["수량"].sum()) if not remaining_items.empty else 0
    display_cols = ["확정상태", "사업장", "제품명", "LOT", "유통기한", "수량", "원래로케이션", "현재로케이션", "확정사업장", "확정매출처", "확정일시"]
    st.dataframe(items[display_cols], hide_index=True, use_container_width=True)
    st.caption(f"전체 {len(items)}개 재고행 / {total_qty}EA · 남은 수출대기 {len(remaining_items)}개 / {remaining_qty}EA")

    erp_sales_rows = build_export_waiting_erp_sales_rows(items)
    unmatched_count = (
        int((erp_sales_rows["매칭상태"] == "확인필요").sum())
        if not erp_sales_rows.empty
        else 0
    )

    download_col, edit_col, merge_col, cancel_col = st.columns(4)
    with download_col:
        if not erp_sales_rows.empty:
            st.download_button(
                "ERP 매출입력용 리스트 엑셀 다운로드",
                data=export_waiting_erp_sales_excel_bytes(erp_sales_rows),
                file_name=(
                    f"NOHTUS_ERP_매출입력용_"
                    f"{safe_export_no_for_filename(selected['export_no'])}_"
                    f"{date.today().strftime('%Y%m%d')}.xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"export_waiting_erp_sales_download_{order_id}",
            )
        else:
            st.button(
                "ERP 매출입력용 리스트 엑셀 다운로드",
                disabled=True,
                use_container_width=True,
                key=f"export_waiting_erp_sales_download_empty_{order_id}",
            )
    with edit_col:
        if status == "waiting":
            if st.button("수출대기 수정", type="primary", use_container_width=True):
                st.session_state["export_editing_order_id"] = order_id
                st.session_state.pop("_export_edit_loaded", None)
                st.session_state["page"] = "수출대기 등록"
                st.rerun()
        else:
            st.button("수출대기 수정", disabled=True, use_container_width=True)
    with merge_col:
        if status == "waiting":
            if st.button("수출대기 병합", use_container_width=True):
                st.session_state["confirm_export_merge_source_id"] = order_id
        else:
            st.button("수출대기 병합", disabled=True, use_container_width=True)
    with cancel_col:
        if st.button(
            "주문 취소",
            use_container_width=True,
            disabled=status in {"confirmed", "cancelled"},
        ):
            st.session_state["confirm_export_cancel_id"] = order_id

    if unmatched_count:
        st.warning(
            f"제품매칭표에 해당 사업장 ERP명이 없는 품목이 {unmatched_count}개 있습니다. "
            "엑셀에서 `확인필요`로 표시됩니다."
        )

    if status == "cancelled":
        st.error("취소된 건입니다. 확정되지 않았던 품목은 등록 당시 원래 로케이션으로 복구되었습니다.")
        return
    if status == "confirmed":
        st.success("모든 품목의 수출확정이 완료되었습니다. 출고일자는 위에서 수정할 수 있습니다.")
        return

    if st.session_state.get("confirm_export_merge_source_id") == order_id:
        merge_targets = q(
            """SELECT id,export_no,country,buyer,transport_method,title
               FROM export_waiting_orders
               WHERE id<>? AND status='waiting'
               ORDER BY id DESC""",
            (order_id,),
        )
        if merge_targets.empty:
            st.warning("병합할 수 있는 다른 수출대기 건이 없습니다.")
            if st.button("병합 닫기", use_container_width=True):
                st.session_state.pop("confirm_export_merge_source_id", None)
                st.rerun()
        else:
            target_labels = [
                f"{str(row.export_no or '-')} · {str(row.title or '-')}"
                for row in merge_targets.itertuples()
            ]
            selected_target_label = st.selectbox(
                "합쳐질 대상 수출대기 건",
                target_labels,
                key=f"export_merge_target_{order_id}",
                help="선택한 현재 건의 모든 품목이 이 수출번호로 합쳐집니다.",
            )
            target_index = target_labels.index(selected_target_label)
            target_order = merge_targets.iloc[target_index]
            target_order_id = int(target_order["id"])
            source_export_no = str(selected["export_no"] or "-")
            target_export_no = str(target_order["export_no"] or "-")
            st.warning(
                f"수출번호 {source_export_no}의 모든 품목을 {target_export_no}에 합칩니다. "
                f"병합 후 {source_export_no} 건은 목록에서 삭제되며 되돌릴 수 없습니다."
            )
            no_merge_col, yes_merge_col = st.columns(2)
            with no_merge_col:
                if st.button("병합하지 않기", use_container_width=True):
                    st.session_state.pop("confirm_export_merge_source_id", None)
                    st.rerun()
            with yes_merge_col:
                if st.button(
                    f"{source_export_no} → {target_export_no} 병합",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        result = merge_export_waiting_orders(order_id, target_order_id)
                        st.session_state.pop("confirm_export_merge_source_id", None)
                        st.session_state[_SELECTED_ORDER_KEY] = target_order_id
                        st.session_state["_export_waiting_message"] = (
                            f"수출번호 {result['source_export_no']}의 "
                            f"{result['merged_row_count']}개 재고행 / {result['merged_qty']}EA를 "
                            f"{result['target_export_no']}에 합쳤습니다."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    if st.session_state.get("confirm_export_cancel_id") == order_id:
        st.warning("이미 확정된 품목은 유지되고, 아직 확정되지 않은 품목만 원래 로케이션으로 돌아갑니다.")
        no_col, yes_col = st.columns(2)
        with no_col:
            if st.button("취소하지 않기", use_container_width=True):
                st.session_state.pop("confirm_export_cancel_id", None)
                st.rerun()
        with yes_col:
            if st.button("남은 품목을 원래 위치로 복구하고 취소", type="primary", use_container_width=True):
                try:
                    cancel_export_waiting_order(order_id)
                    st.session_state.pop("confirm_export_cancel_id", None)
                    st.session_state["_export_waiting_message"] = f"{selected['title']}의 남은 수출대기를 취소하고 원래 위치로 복구했습니다."
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.markdown("---")
    st.markdown("### 선택 품목 수출확정")
    st.caption("아직 확정되지 않은 품목을 체크하고, ERP 매출 정보와 출고일자를 설정하세요.")
    selection_source = remaining_items[["id", "사업장", "제품명", "LOT", "유통기한", "수량", "원래로케이션"]].copy()
    selection_source.insert(0, "선택", False)
    edited = st.data_editor(
        selection_source,
        hide_index=True,
        use_container_width=True,
        key=f"export_confirm_items_{order_id}_{confirmed_count}",
        disabled=["id", "사업장", "제품명", "LOT", "유통기한", "수량", "원래로케이션"],
        column_config={"선택": st.column_config.CheckboxColumn("선택", help="이번에 같은 ERP 사업장으로 확정할 품목"), "id": None},
    )
    selected_rows = edited[edited["선택"] == True] if not edited.empty else pd.DataFrame()  # noqa: E712
    selected_ids = selected_rows["id"].astype(int).tolist() if not selected_rows.empty else []
    selected_qty = int(selected_rows["수량"].sum()) if not selected_rows.empty else 0
    st.caption(f"선택: {len(selected_ids)}개 품목 / {selected_qty}EA")

    confirm_info_col, shipment_date_col = st.columns(2)
    with confirm_info_col:
        default_company = str(selected_rows.iloc[0]["사업장"] or "") if not selected_rows.empty else str(remaining_items.iloc[0]["사업장"] or "")
        default_index = COMPANIES.index(default_company) if default_company in COMPANIES else 0
        erp_company = st.selectbox(
            "ERP 매출 사업장",
            COMPANIES,
            index=default_index,
            key=f"export_confirm_company_{order_id}_{confirmed_count}",
        )
        term = st.text_input(
            "ERP 수출 매출처 검색",
            placeholder="매출처명 일부를 입력하세요",
            key=f"export_customer_term_{order_id}_{confirmed_count}",
        )
        customers = _customer_options(erp_company, term)
        if customers.empty:
            st.warning("해당 사업장의 ERP 매출처가 없습니다. 거래처 관리에서 ERP 매출처 목록을 먼저 등록하거나 갱신하세요.")
            return
        labels = [f"{str(r.customer_code or '').strip() or '-'} | {r.customer_name}" for r in customers.itertuples()]
        customer = customers.iloc[
            labels.index(
                st.selectbox(
                    "ERP 수출 매출처",
                    labels,
                    key=f"export_customer_select_{order_id}_{confirmed_count}",
                )
            )
        ]
    with shipment_date_col:
        shipment_date = st.date_input(
            "출고일자",
            value=_date_value(selected.get("order_date")),
            key=f"export_confirm_order_date_{order_id}_{confirmed_count}",
            help="이번에 선택한 품목에 적용할 출고일자를 선택하세요.",
        )

    if st.button("선택 품목 수출확정", type="primary", use_container_width=True, disabled=not selected_ids):
        try:
            confirm_export_waiting_items(
                order_id,
                selected_ids,
                erp_company=erp_company,
                customer_code=customer["customer_code"],
                customer_name=customer["customer_name"],
                shipment_date=shipment_date,
            )
            st.session_state["_export_waiting_message"] = (
                f"{selected['title']}에서 {len(selected_ids)}개 품목 / {selected_qty}EA를 "
                f"{_normalize_date_text(shipment_date)} 출고로 수출확정했습니다."
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
