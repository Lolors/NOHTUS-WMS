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
    "erp_compare_live_wms_fingerprint",
]

COMPANY_ERP_COLUMNS = {
    "노투스팜": "erp_nohtuspharm_name",
    "NOH": "erp_noh_name",
    "노투스": "erp_nohtus_name",
}


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


def _load_company_product_mappings():
    """사업장별 ERP명과 표준제품명의 역매핑을 만든다.

    각 사업장은 반드시 자기 ERP 컬럼만 사용한다. 같은 ERP명이 서로 다른 표준제품명에
    연결된 경우 자동으로 하나를 선택하지 않고 모호한 매핑으로 표시한다.
    """
    products = q(
        """
        SELECT id, standard_name,
               erp_nohtuspharm_name, erp_noh_name, erp_nohtus_name
        FROM products
        WHERE TRIM(COALESCE(standard_name,''))<>''
        ORDER BY id
        """
    )

    reverse = {}
    forward = {}
    ambiguous = []
    if products.empty:
        return reverse, forward, ambiguous

    for company, erp_column in COMPANY_ERP_COLUMNS.items():
        company_reverse = {}
        company_forward = {}

        for row in products.itertuples(index=False):
            standard_name = closing_service.clean_excel_text(getattr(row, "standard_name", ""))
            erp_name = closing_service.clean_excel_text(getattr(row, erp_column, ""))
            if not standard_name or not erp_name:
                continue

            erp_key = _normalize_match_key(erp_name)
            if not erp_key:
                continue

            company_reverse.setdefault(erp_key, {"erp_names": set(), "standards": set()})
            company_reverse[erp_key]["erp_names"].add(erp_name)
            company_reverse[erp_key]["standards"].add(standard_name)
            company_forward.setdefault(standard_name, set()).add(erp_name)

        for erp_key, info in company_reverse.items():
            standards = sorted(info["standards"])
            erp_names = sorted(info["erp_names"])
            if len(standards) == 1:
                reverse[(company, erp_key)] = {
                    "standard_name": standards[0],
                    "erp_names": erp_names,
                }
            else:
                ambiguous.append(
                    {
                        "사업장": company,
                        "ERP명": " / ".join(erp_names),
                        "표준제품명": " / ".join(standards),
                        "사유": "같은 ERP명이 여러 표준제품명에 연결됨",
                    }
                )

        for standard_name, erp_names in company_forward.items():
            names = sorted(erp_names)
            if len(names) == 1:
                forward[(company, standard_name)] = names[0]
            elif len(names) > 1:
                ambiguous.append(
                    {
                        "사업장": company,
                        "ERP명": " / ".join(names),
                        "표준제품명": standard_name,
                        "사유": "한 표준제품명에 같은 사업장 ERP명이 여러 개 연결됨",
                    }
                )

    return reverse, forward, ambiguous


def _load_live_wms_stock(forward_mapping):
    """현재 inventory 행을 표준제품명 단위로만 집계한다.

    서로 다른 표준제품명은 ERP명이 같더라도 절대 합산하지 않는다.
    """
    raw = q(
        """
        SELECT company AS 사업장,
               product_name AS WMS표준제품명,
               SUM(qty) AS WMS수량
        FROM inventory
        WHERE qty <> 0
          AND company IN ('노투스팜', 'NOH', '노투스')
        GROUP BY company, product_name
        ORDER BY company, product_name
        """
    )
    if raw.empty:
        return pd.DataFrame(
            columns=["사업장", "비교키", "WMS표준제품명", "WMS ERP명", "WMS수량"]
        )

    rows = []
    for row in raw.itertuples(index=False):
        company = closing_service.clean_excel_text(getattr(row, "사업장", ""))
        standard_name = closing_service.clean_excel_text(getattr(row, "WMS표준제품명", ""))
        if not company or not standard_name:
            continue

        erp_name = closing_service.clean_excel_text(
            forward_mapping.get((company, standard_name), "")
        )
        rows.append(
            {
                "사업장": company,
                "비교키": f"STD::{standard_name}",
                "WMS표준제품명": standard_name,
                "WMS ERP명": erp_name,
                "WMS수량": int(getattr(row, "WMS수량", 0) or 0),
            }
        )

    return pd.DataFrame(rows)


def _prepare_erp_snapshot(erp_sum, reverse_mapping):
    """ERP 원본제품명을 해당 사업장의 ERP 컬럼으로만 표준제품명에 역매칭한다."""
    if erp_sum is None or erp_sum.empty:
        return pd.DataFrame(
            columns=["사업장", "비교키", "ERP원본제품명", "ERP매칭표준제품명", "ERP수량", "ERP매칭상태"]
        )

    rows = []
    for row in erp_sum.itertuples(index=False):
        company = closing_service.clean_excel_text(getattr(row, "사업장", ""))
        erp_name = closing_service.clean_excel_text(getattr(row, "ERP제품명", ""))
        erp_key = _normalize_match_key(erp_name)
        mapping = reverse_mapping.get((company, erp_key))

        if mapping:
            standard_name = mapping["standard_name"]
            compare_key = f"STD::{standard_name}"
            status = "매칭"
        else:
            standard_name = ""
            compare_key = f"ERP::{company}::{erp_key}"
            status = "제품매칭표에 없음"

        rows.append(
            {
                "사업장": company,
                "비교키": compare_key,
                "ERP원본제품명": erp_name,
                "ERP매칭표준제품명": standard_name,
                "ERP수량": int(getattr(row, "ERP수량", 0) or 0),
                "ERP매칭상태": status,
            }
        )

    frame = pd.DataFrame(rows)
    return (
        frame.groupby(["사업장", "비교키", "ERP매칭표준제품명", "ERP매칭상태"], as_index=False)
        .agg(
            {
                "ERP원본제품명": lambda values: " / ".join(
                    sorted(set(str(v) for v in values if str(v).strip()))
                ),
                "ERP수량": "sum",
            }
        )
    )


def _wms_fingerprint(wms_live):
    if wms_live is None or wms_live.empty:
        return "empty"
    stable = wms_live.sort_values(["사업장", "비교키"]).fillna("")
    payload = stable.to_csv(index=False).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _compare(erp_snapshot, wms_live):
    result = pd.merge(erp_snapshot, wms_live, how="outer", on=["사업장", "비교키"])
    if result.empty:
        return pd.DataFrame(
            columns=[
                "사업장", "ERP원본제품명", "ERP매칭표준제품명", "WMS표준제품명",
                "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태",
            ]
        )

    text_columns = [
        "ERP원본제품명", "ERP매칭표준제품명", "ERP매칭상태",
        "WMS표준제품명", "WMS ERP명",
    ]
    for column in text_columns:
        if column not in result.columns:
            result[column] = ""
        result[column] = result[column].fillna("")

    result["ERP수량"] = pd.to_numeric(result.get("ERP수량"), errors="coerce").fillna(0).astype(int)
    result["WMS수량"] = pd.to_numeric(result.get("WMS수량"), errors="coerce").fillna(0).astype(int)
    result["차이"] = result["WMS수량"] - result["ERP수량"]
    result["매칭상태"] = "매칭"
    result.loc[result["ERP원본제품명"] == "", "매칭상태"] = "ERP에 없음"
    result.loc[result["WMS표준제품명"] == "", "매칭상태"] = result.loc[
        result["WMS표준제품명"] == "", "ERP매칭상태"
    ].replace("", "WMS에 없음")

    return result[
        [
            "사업장", "ERP원본제품명", "ERP매칭표준제품명", "WMS표준제품명",
            "WMS ERP명", "ERP수량", "WMS수량", "차이", "매칭상태",
        ]
    ].sort_values(["사업장", "ERP매칭표준제품명", "ERP원본제품명", "WMS표준제품명"])


def page_erp_stock_compare():
    st.title("ERP 재고 비교")
    st.caption(
        "ERP 제품명을 사업장별 전용 ERP명 컬럼으로 표준제품명에 역매칭한 뒤, "
        "현재 WMS inventory의 표준제품명별 실시간 재고와 비교합니다."
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

    reverse_mapping, forward_mapping, ambiguous = _load_company_product_mappings()

    _, run_column, _ = st.columns([3, 2, 3], gap="large")
    with run_column:
        run_compare = st.button("ERP 재고 비교 실행", type="primary", use_container_width=True)

    if run_compare:
        erp_sum, source_rows = closing_service.read_and_sum_erp_current_stock(uploaded_files)
        snapshot = _prepare_erp_snapshot(erp_sum, reverse_mapping)
        wms_at_compare = _load_live_wms_stock(forward_mapping)
        st.session_state["erp_compare_live_erp_rows"] = snapshot.to_dict("records")
        st.session_state["erp_compare_live_file_signature"] = signature
        st.session_state["erp_compare_live_compared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["erp_compare_live_source_rows"] = int(source_rows)
        st.session_state["erp_compare_live_wms_fingerprint"] = _wms_fingerprint(wms_at_compare)

    stored_rows = st.session_state.get("erp_compare_live_erp_rows")
    if stored_rows is None:
        return

    erp_snapshot = pd.DataFrame(stored_rows)
    wms_live = _load_live_wms_stock(forward_mapping)
    current_fingerprint = _wms_fingerprint(wms_live)
    compared_fingerprint = st.session_state.get("erp_compare_live_wms_fingerprint")
    if compared_fingerprint and compared_fingerprint != current_fingerprint:
        st.warning(
            "비교 실행 이후 WMS 재고가 변경되었습니다. 아래 결과는 현재 inventory 재고로 자동 재계산되었습니다."
        )

    if ambiguous:
        st.error(
            f"제품매칭표에 사업장별 중복·모호한 ERP 매핑이 {len(ambiguous)}건 있습니다. "
            "이 항목은 임의로 합치지 않습니다. 아래 목록에서 제품매칭표를 수정해 주세요."
        )
        with st.expander("모호한 제품매칭 목록", expanded=False):
            st.dataframe(pd.DataFrame(ambiguous), use_container_width=True, hide_index=True)

    result = _compare(erp_snapshot, wms_live)

    compared_at = st.session_state.get("erp_compare_live_compared_at", "-")
    wms_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_names = [
        f"{company}: {getattr(uploaded, 'name', '-')}"
        for company, uploaded in uploaded_files.items()
        if uploaded is not None
    ]
    st.caption(f"ERP 스냅샷 생성: {compared_at} · WMS inventory 재조회: {wms_checked_at}")
    if file_names:
        st.caption("ERP 원본 파일 · " + " | ".join(file_names))

    source_rows = int(st.session_state.get("erp_compare_live_source_rows", 0) or 0)
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("ERP 원본 행", f"{source_rows:,}건")
    metric2.metric("ERP 표준제품 합산", f"{len(erp_snapshot):,}건")
    metric3.metric("WMS 현재 표준제품", f"{len(wms_live):,}건")
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
