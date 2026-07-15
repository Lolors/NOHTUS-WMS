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
    "erp_compare_v2_erp_rows",
    "erp_compare_v2_file_signature",
    "erp_compare_v2_compared_at",
    "erp_compare_v2_source_rows",
]

COMPANY_ERP_COLUMNS = {
    "노투스팜": "erp_nohtuspharm_name",
    "NOH": "erp_noh_name",
    "노투스": "erp_nohtus_name",
}


def _clean(value) -> str:
    return closing_service.clean_excel_text(value)


def _normal_key(value) -> str:
    text = unicodedata.normalize("NFKC", _clean(value)).lower()
    return re.sub(r"[\s\-_./\\,()[\]{}]+", "", text)


def _file_signature(uploaded_files) -> str:
    parts = []
    for company in closing_service.ERP_COMPARE_COMPANIES:
        uploaded = uploaded_files.get(company)
        if uploaded is None:
            parts.append(f"{company}:none")
            continue
        try:
            payload = uploaded.getvalue()
            parts.append(
                f"{company}:{getattr(uploaded, 'name', '')}:{len(payload)}:{hashlib.sha1(payload).hexdigest()}"
            )
        except Exception:
            parts.append(f"{company}:{getattr(uploaded, 'name', '')}:{getattr(uploaded, 'size', '')}")
    return "|".join(parts)


def _clear_result() -> None:
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)


def _inventory_rows() -> pd.DataFrame:
    """전체 조회와 동일한 inventory 원본을 현재 시점에 다시 읽는다."""
    return q(
        """
        SELECT company AS 사업장,
               product_name AS 표준제품명,
               COALESCE(warehouse_name, '') AS 재고ERP명,
               SUM(qty) AS WMS수량
        FROM inventory
        WHERE qty <> 0
          AND company IN ('노투스팜', 'NOH', '노투스')
        GROUP BY company, product_name, COALESCE(warehouse_name, '')
        ORDER BY company, product_name, COALESCE(warehouse_name, '')
        """
    )


def _product_master_rows() -> pd.DataFrame:
    return q(
        """
        SELECT standard_name,
               erp_nohtuspharm_name,
               erp_noh_name,
               erp_nohtus_name
        FROM products
        WHERE TRIM(COALESCE(standard_name, '')) <> ''
        ORDER BY id
        """
    )


def _build_reverse_map(inventory: pd.DataFrame, products: pd.DataFrame):
    """사업장 ERP명 -> 표준제품명 후보를 만든다.

    현재 inventory.warehouse_name을 우선하며, 현재 재고가 없는 ERP 제품을 위해서만
    제품매칭표의 해당 사업장 전용 컬럼을 보조 후보로 추가한다.
    """
    candidates: dict[tuple[str, str], dict[str, set[str]]] = {}

    if inventory is not None and not inventory.empty:
        for row in inventory.itertuples(index=False):
            company = _clean(getattr(row, "사업장", ""))
            standard = _clean(getattr(row, "표준제품명", ""))
            erp_name = _clean(getattr(row, "재고ERP명", ""))
            key = _normal_key(erp_name)
            if not company or not standard or not key:
                continue
            info = candidates.setdefault((company, key), {"standards": set(), "names": set(), "sources": set()})
            info["standards"].add(standard)
            info["names"].add(erp_name)
            info["sources"].add("현재재고")

    if products is not None and not products.empty:
        for company, column in COMPANY_ERP_COLUMNS.items():
            for row in products.itertuples(index=False):
                standard = _clean(getattr(row, "standard_name", ""))
                erp_name = _clean(getattr(row, column, ""))
                key = _normal_key(erp_name)
                if not standard or not key:
                    continue
                info = candidates.setdefault((company, key), {"standards": set(), "names": set(), "sources": set()})
                info["standards"].add(standard)
                info["names"].add(erp_name)
                info["sources"].add("제품매칭표")

    resolved = {}
    ambiguous = []
    for (company, key), info in candidates.items():
        standards = sorted(info["standards"])
        names = sorted(info["names"])
        if len(standards) == 1:
            resolved[(company, key)] = standards[0]
        else:
            ambiguous.append(
                {
                    "사업장": company,
                    "ERP명": " / ".join(names),
                    "연결된 표준제품명": " / ".join(standards),
                    "근거": " / ".join(sorted(info["sources"])),
                    "사유": "같은 사업장 ERP명이 여러 표준제품명에 연결됨",
                }
            )
    return resolved, ambiguous


def _live_wms_summary(inventory: pd.DataFrame) -> pd.DataFrame:
    """현재 inventory를 표준제품명 단위로 집계한다.

    ERP명이 같더라도 서로 다른 표준제품명은 절대 합치지 않는다.
    """
    if inventory is None or inventory.empty:
        return pd.DataFrame(columns=["사업장", "표준제품명", "WMS ERP명", "WMS수량"])

    work = inventory.copy()
    work["사업장"] = work["사업장"].map(_clean)
    work["표준제품명"] = work["표준제품명"].map(_clean)
    work["재고ERP명"] = work["재고ERP명"].map(_clean)
    work["WMS수량"] = pd.to_numeric(work["WMS수량"], errors="coerce").fillna(0).astype(int)

    return (
        work.groupby(["사업장", "표준제품명"], as_index=False)
        .agg(
            {
                "재고ERP명": lambda values: " / ".join(sorted({v for v in values if v})),
                "WMS수량": "sum",
            }
        )
        .rename(columns={"재고ERP명": "WMS ERP명"})
        .sort_values(["사업장", "표준제품명"])
    )


def _prepare_erp_rows(erp_sum: pd.DataFrame, reverse_map) -> pd.DataFrame:
    if erp_sum is None or erp_sum.empty:
        return pd.DataFrame(
            columns=["사업장", "ERP원본제품명", "표준제품명", "ERP수량", "ERP매칭상태"]
        )

    rows = []
    for row in erp_sum.itertuples(index=False):
        company = _clean(getattr(row, "사업장", ""))
        erp_name = _clean(getattr(row, "ERP제품명", ""))
        quantity = int(getattr(row, "ERP수량", 0) or 0)
        key = _normal_key(erp_name)
        standard = reverse_map.get((company, key), "")
        rows.append(
            {
                "사업장": company,
                "ERP원본제품명": erp_name,
                "표준제품명": standard,
                "ERP수량": quantity,
                "ERP매칭상태": "매칭" if standard else "매칭 불가",
            }
        )

    frame = pd.DataFrame(rows)
    matched = frame[frame["표준제품명"] != ""].copy()
    unmatched = frame[frame["표준제품명"] == ""].copy()

    parts = []
    if not matched.empty:
        matched = (
            matched.groupby(["사업장", "표준제품명", "ERP매칭상태"], as_index=False)
            .agg(
                {
                    "ERP원본제품명": lambda values: " / ".join(sorted({str(v) for v in values if str(v).strip()})),
                    "ERP수량": "sum",
                }
            )
        )
        parts.append(matched)

    if not unmatched.empty:
        unmatched["미매칭키"] = unmatched["ERP원본제품명"].map(_normal_key)
        unmatched = (
            unmatched.groupby(["사업장", "미매칭키", "ERP매칭상태"], as_index=False)
            .agg(
                {
                    "ERP원본제품명": lambda values: " / ".join(sorted({str(v) for v in values if str(v).strip()})),
                    "ERP수량": "sum",
                }
            )
        )
        unmatched["표준제품명"] = ""
        unmatched = unmatched[["사업장", "ERP원본제품명", "표준제품명", "ERP수량", "ERP매칭상태"]]
        parts.append(unmatched)

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _compare(erp_rows: pd.DataFrame, wms_rows: pd.DataFrame) -> pd.DataFrame:
    matched_erp = erp_rows[erp_rows["표준제품명"] != ""].copy() if not erp_rows.empty else pd.DataFrame()
    unmatched_erp = erp_rows[erp_rows["표준제품명"] == ""].copy() if not erp_rows.empty else pd.DataFrame()

    if matched_erp.empty:
        result = wms_rows.copy()
        result["ERP원본제품명"] = ""
        result["ERP수량"] = 0
        result["ERP매칭상태"] = "ERP에 없음"
    else:
        result = pd.merge(
            matched_erp,
            wms_rows,
            how="outer",
            on=["사업장", "표준제품명"],
        )

    for column in ["ERP원본제품명", "ERP매칭상태", "WMS ERP명"]:
        if column not in result.columns:
            result[column] = ""
        result[column] = result[column].fillna("")
    for column in ["ERP수량", "WMS수량"]:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)

    result["차이"] = result["WMS수량"] - result["ERP수량"]
    result["매칭상태"] = "매칭"
    result.loc[result["ERP원본제품명"] == "", "매칭상태"] = "ERP에 없음"
    result.loc[result["WMS ERP명"] == "", "매칭상태"] = "WMS에 없음"

    if not unmatched_erp.empty:
        extra = unmatched_erp.copy()
        extra["WMS ERP명"] = ""
        extra["WMS수량"] = 0
        extra["차이"] = -extra["ERP수량"].astype(int)
        extra["매칭상태"] = "ERP 제품명 매칭 불가"
        extra = extra[["사업장", "ERP원본제품명", "표준제품명", "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태"]]
        result = pd.concat([result, extra], ignore_index=True)

    return result[
        ["사업장", "ERP원본제품명", "표준제품명", "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태"]
    ].sort_values(["사업장", "표준제품명", "ERP원본제품명"])


def page_erp_stock_compare():
    st.title("ERP 재고 비교")
    st.caption(
        "WMS는 전체 조회와 같은 현재 inventory 행을 사용합니다. ERP 원본명은 같은 사업장의 "
        "현재 재고 ERP명으로 먼저 매칭하고, 현재 재고가 없는 제품만 제품매칭표를 보조로 사용합니다."
    )

    uploaded_files = {}
    columns = st.columns(3, gap="large")
    for column, company in zip(columns, closing_service.ERP_COMPARE_COMPANIES):
        spec = closing_service.ERP_COMPARE_COLUMNS[company]
        with column:
            st.markdown(f"### {company}")
            caption = f"제품명: {spec['name']} · 수량: {spec['qty']}"
            if company == "노투스":
                caption = "8행 헤더 · " + caption
            st.caption(caption)
            uploaded_files[company] = st.file_uploader(
                f"{company} ERP 현재고 엑셀",
                type=["xlsx", "xls"],
                key=f"erp_compare_upload_{company}",
            )

    signature = _file_signature(uploaded_files)
    old_signature = st.session_state.get("erp_compare_v2_file_signature")
    if old_signature is not None and old_signature != signature:
        _clear_result()
        st.info("ERP 파일이 변경되어 이전 비교 결과를 초기화했습니다.")

    if not any(uploaded_files.values()):
        _clear_result()
        st.info("노투스팜 / NOH / 노투스 ERP 현재고 엑셀을 업로드하세요.")
        return

    _, run_column, _ = st.columns([3, 2, 3])
    with run_column:
        run_compare = st.button("ERP 재고 비교 실행", type="primary", use_container_width=True)

    inventory = _inventory_rows()
    products = _product_master_rows()
    reverse_map, ambiguous = _build_reverse_map(inventory, products)
    wms_live = _live_wms_summary(inventory)

    if run_compare:
        erp_sum, source_rows = closing_service.read_and_sum_erp_current_stock(uploaded_files)
        prepared = _prepare_erp_rows(erp_sum, reverse_map)
        st.session_state["erp_compare_v2_erp_rows"] = prepared.to_dict("records")
        st.session_state["erp_compare_v2_file_signature"] = signature
        st.session_state["erp_compare_v2_compared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["erp_compare_v2_source_rows"] = int(source_rows)

    stored = st.session_state.get("erp_compare_v2_erp_rows")
    if stored is None:
        return

    erp_rows = pd.DataFrame(stored)
    result = _compare(erp_rows, wms_live)

    st.caption(
        f"ERP 파일 처리: {st.session_state.get('erp_compare_v2_compared_at', '-')} · "
        f"WMS inventory 재조회: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    file_names = [
        f"{company}: {getattr(uploaded, 'name', '-')}"
        for company, uploaded in uploaded_files.items()
        if uploaded is not None
    ]
    if file_names:
        st.caption("ERP 원본 파일 · " + " | ".join(file_names))

    if ambiguous:
        st.error(
            f"같은 사업장의 ERP명이 여러 표준제품명에 연결된 항목이 {len(ambiguous)}건 있습니다. "
            "이 항목은 자동으로 합치지 않았습니다."
        )
        with st.expander("모호한 매칭 목록"):
            st.dataframe(pd.DataFrame(ambiguous), use_container_width=True, hide_index=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ERP 원본 행", f"{int(st.session_state.get('erp_compare_v2_source_rows', 0)):,}건")
    m2.metric("ERP 매칭 결과", f"{len(erp_rows):,}건")
    m3.metric("WMS 현재 표준제품", f"{len(wms_live):,}건")
    m4.metric("차이 항목", f"{int((result['차이'] != 0).sum()) if not result.empty else 0:,}건")

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
