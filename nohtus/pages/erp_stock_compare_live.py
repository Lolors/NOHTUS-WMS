from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.db import q
from nohtus.services import closing as closing_service


SESSION_KEYS = [
    "erp_compare_live_erp_rows",
    "erp_compare_live_file_signature",
    "erp_compare_live_compared_at",
    "erp_compare_live_source_rows",
]


def _normalize_match_key(value):
    text = closing_service.clean_excel_text(value)
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\s\-_./\\,()[\]{}]+", "", text)
    return text


def _file_signature(uploaded_files):
    parts = []
    for company in closing_service.ERP_COMPARE_COMPANIES:
        uploaded = uploaded_files.get(company)
        if uploaded is None:
            parts.append(f"{company}:none")
            continue
        try:
            payload = uploaded.getvalue()
            digest = hashlib.sha1(payload).hexdigest()
            parts.append(f"{company}:{uploaded.name}:{len(payload)}:{digest}")
        except Exception:
            parts.append(f"{company}:{getattr(uploaded, 'name', '')}:{getattr(uploaded, 'size', '')}")
    return "|".join(parts)


def _clear_previous_result():
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)


def _load_live_wms_stock():
    raw = q(
        """
        SELECT company AS 사업장,
               product_name AS WMS표준제품명,
               SUM(qty) AS WMS수량
        FROM inventory
        WHERE qty <> 0
          AND company IN ('노투스팜', 'NOH', '노투스')
        GROUP BY company, product_name
        """
    )
    if raw.empty:
        return pd.DataFrame(columns=["사업장", "매칭키", "WMS표준제품명", "WMS ERP명", "WMS수량"])

    product_map = closing_service.load_product_erp_name_map()
    rows = []
    for row in raw.itertuples(index=False):
        company = closing_service.clean_excel_text(getattr(row, "사업장", ""))
        standard_name = closing_service.clean_excel_text(getattr(row, "WMS표준제품명", ""))
        erp_name = closing_service.clean_excel_text(product_map.get((company, standard_name)) or standard_name)
        if closing_service.is_ignored_erp_product_name(erp_name):
            continue
        rows.append(
            {
                "사업장": company,
                "매칭키": _normalize_match_key(erp_name),
                "WMS표준제품명": standard_name,
                "WMS ERP명": erp_name,
                "WMS수량": int(getattr(row, "WMS수량", 0) or 0),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["사업장", "매칭키", "WMS표준제품명", "WMS ERP명", "WMS수량"])

    frame = pd.DataFrame(rows)
    return (
        frame.groupby(["사업장", "매칭키"], as_index=False)
        .agg(
            {
                "WMS표준제품명": lambda values: " / ".join(sorted(set(str(v) for v in values if str(v).strip()))),
                "WMS ERP명": lambda values: " / ".join(sorted(set(str(v) for v in values if str(v).strip()))),
                "WMS수량": "sum",
            }
        )
    )


def _prepare_erp_snapshot(erp_sum):
    if erp_sum is None or erp_sum.empty:
        return pd.DataFrame(columns=["사업장", "매칭키", "ERP원본제품명", "ERP수량"])

    work = erp_sum.copy()
    work["ERP원본제품명"] = work["ERP제품명"].apply(closing_service.clean_excel_text)
    work["매칭키"] = work["ERP원본제품명"].apply(_normalize_match_key)
    work = work[work["매칭키"] != ""]
    return (
        work.groupby(["사업장", "매칭키"], as_index=False)
        .agg(
            {
                "ERP원본제품명": lambda values: " / ".join(sorted(set(str(v) for v in values if str(v).strip()))),
                "ERP수량": "sum",
            }
        )
    )


def _compare(erp_snapshot, wms_live):
    result = pd.merge(erp_snapshot, wms_live, how="outer", on=["사업장", "매칭키"])
    if result.empty:
        return pd.DataFrame(
            columns=["사업장", "ERP원본제품명", "WMS표준제품명", "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태"]
        )

    for column in ["ERP원본제품명", "WMS표준제품명", "WMS ERP명"]:
        result[column] = result[column].fillna("")
    result["ERP수량"] = pd.to_numeric(result["ERP수량"], errors="coerce").fillna(0).astype(int)
    result["WMS수량"] = pd.to_numeric(result["WMS수량"], errors="coerce").fillna(0).astype(int)
    result["차이"] = result["WMS수량"] - result["ERP수량"]
    result["매칭상태"] = "매칭"
    result.loc[result["ERP원본제품명"] == "", "매칭상태"] = "ERP에 없음"
    result.loc[result["WMS표준제품명"] == "", "매칭상태"] = "WMS에 없음"
    return result[
        ["사업장", "ERP원본제품명", "WMS표준제품명", "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태"]
    ].sort_values(["사업장", "ERP원본제품명", "WMS표준제품명"])


def page_erp_stock_compare():
    st.title("ERP 재고 비교")
    st.caption(
        "ERP 업로드 파일의 현재고와 화면을 열 때마다 다시 집계한 WMS 실시간 재고를 비교합니다. "
        "제품명은 공백·괄호·일반 구분기호를 정규화해 매칭합니다."
    )

    uploaded_files = {}
    columns = st.columns(3, gap="large")
    for column, company in zip(columns, closing_service.ERP_COMPARE_COMPANIES):
        spec = closing_service.ERP_COMPARE_COLUMNS[company]
        with column:
            st.markdown(f"### {company}")
            if company == "노투스":
                st.caption(f"8행 헤더 · 제품명: {spec['name']} · 수량: {spec['qty']}")
            else:
                st.caption(f"제품명: {spec['name']} · 수량: {spec['qty']}")
            uploaded_files[company] = st.file_uploader(
                f"{company} ERP 현재고 엑셀",
                type=["xlsx", "xls"],
                key=f"erp_compare_upload_{company}",
            )

    signature = _file_signature(uploaded_files)
    previous_signature = st.session_state.get("erp_compare_live_file_signature")
    if previous_signature is not None and previous_signature != signature:
        _clear_previous_result()
        st.info("ERP 파일 선택이 변경되어 이전 비교 결과를 초기화했습니다.")

    if not any(uploaded_files.values()):
        _clear_previous_result()
        st.info("노투스팜 / NOH / 노투스 ERP 현재고 엑셀을 업로드하세요.")
        return

    _, run_column, _ = st.columns([3, 2, 3], gap="large")
    with run_column:
        run_compare = st.button("ERP 재고 비교 실행", type="primary", use_container_width=True)

    if run_compare:
        erp_sum, source_rows = closing_service.read_and_sum_erp_current_stock(uploaded_files)
        snapshot = _prepare_erp_snapshot(erp_sum)
        st.session_state["erp_compare_live_erp_rows"] = snapshot.to_dict("records")
        st.session_state["erp_compare_live_file_signature"] = signature
        st.session_state["erp_compare_live_compared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["erp_compare_live_source_rows"] = int(source_rows)

    stored_rows = st.session_state.get("erp_compare_live_erp_rows")
    if stored_rows is None:
        return

    erp_snapshot = pd.DataFrame(stored_rows)
    wms_live = _load_live_wms_stock()
    result = _compare(erp_snapshot, wms_live)

    compared_at = st.session_state.get("erp_compare_live_compared_at", "-")
    wms_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_names = [
        f"{company}: {getattr(uploaded, 'name', '-')}"
        for company, uploaded in uploaded_files.items()
        if uploaded is not None
    ]
    st.caption(f"ERP 스냅샷 생성: {compared_at} · WMS 재조회: {wms_checked_at}")
    if file_names:
        st.caption("ERP 원본 파일 · " + " | ".join(file_names))

    source_rows = int(st.session_state.get("erp_compare_live_source_rows", 0) or 0)
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("ERP 원본 행", f"{source_rows:,}건")
    metric2.metric("ERP 제품 합산", f"{len(erp_snapshot):,}건")
    metric3.metric("WMS 실시간 제품 합산", f"{len(wms_live):,}건")
    metric4.metric("차이 항목", f"{int((result['차이'] != 0).sum()) if not result.empty else 0:,}건")

    if result.empty:
        st.info("비교할 재고가 없습니다.")
        return

    st.markdown("### 재고 비교 결과")
    only_diff = st.checkbox("차이 있는 항목만 보기", value=True, key="erp_compare_only_diff")
    shown = result[result["차이"] != 0] if only_diff else result
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.download_button(
        "비교 결과 엑셀 다운로드",
        data=closing_service.dataframe_to_excel_bytes(result, "ERP_WMS_비교"),
        file_name=f"NOHTUS_ERP_WMS_비교_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
