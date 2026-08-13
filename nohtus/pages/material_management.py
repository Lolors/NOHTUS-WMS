from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.db import connect, q


_TRUE_MATERIAL_VALUES = ("1", "true", "yes", "y", "o", "v", "체크", "부자재")


def material_products():
    placeholders = ",".join("?" for _ in _TRUE_MATERIAL_VALUES)
    return q(
        f"""
        SELECT TRIM(standard_name) AS standard_name,
               GROUP_CONCAT(DISTINCT NULLIF(TRIM(COALESCE(erp_nohtuspharm_name,'')),'')) AS erp_names
        FROM products
        WHERE LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT))) IN ({placeholders})
          AND TRIM(COALESCE(standard_name,''))<>''
        GROUP BY TRIM(standard_name)
        ORDER BY TRIM(standard_name)
        """,
        _TRUE_MATERIAL_VALUES,
    )


def material_candidates(term=""):
    term = str(term or "").strip()
    like = f"%{term}%"
    return q(
        """
        SELECT TRIM(standard_name) AS standard_name,
               GROUP_CONCAT(DISTINCT NULLIF(TRIM(COALESCE(erp_nohtuspharm_name,'')),'')) AS erp_names
        FROM products
        WHERE TRIM(COALESCE(standard_name,''))<>''
          AND LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT)))
              NOT IN ('1','true','yes','y','o','v','체크','부자재')
          AND (?='' OR standard_name LIKE ? OR COALESCE(aliases,'') LIKE ?
               OR COALESCE(erp_nohtuspharm_name,'') LIKE ?
               OR COALESCE(erp_nohtus_name,'') LIKE ? OR COALESCE(erp_noh_name,'') LIKE ?
               OR COALESCE(bidata_name,'') LIKE ?)
        GROUP BY TRIM(standard_name)
        ORDER BY TRIM(standard_name)
        LIMIT 100
        """,
        (term, like, like, like, like, like, like),
    )


def set_material_products(product_names, is_material):
    names = sorted({str(name or "").strip() for name in product_names if str(name or "").strip()})
    if not names:
        return 0
    with connect() as con:
        placeholders = ",".join("?" for _ in names)
        cur = con.execute(
            f"UPDATE products SET is_material=? WHERE TRIM(standard_name) IN ({placeholders})",
            (1 if is_material else 0, *names),
        )
        con.commit()
        return int(cur.rowcount or 0)


def _labels(df: pd.DataFrame):
    return {
        f"{row.standard_name} | {row.erp_names or '-'}": str(row.standard_name)
        for row in df.itertuples()
    }


def page_material_management():
    st.title("부자재 관리")
    st.caption("출고 대상에서 제외할 부자재 제품을 관리합니다. G1/G2 구역과 홍보물랙 재고는 제품 등록 여부와 관계없이 계속 자동 제외됩니다.")
    st.info("현재 제품 단위 분류를 관리하며, 향후 완제품과 부자재의 BOM 관계를 이 메뉴에 확장할 수 있습니다.")

    st.markdown("### 부자재 추가")
    term = st.text_input(
        "제품 검색",
        placeholder="표준제품명, ERP명, 비자료명 또는 별칭을 입력하세요",
        key="material_management_search",
    )
    candidates = material_candidates(term)
    if candidates.empty:
        st.caption("추가할 수 있는 제품이 없습니다.")
    else:
        labels = _labels(candidates)
        selected = st.multiselect(
            "부자재로 추가할 제품",
            list(labels),
            key="material_management_add_selection",
        )
        if st.button("선택 제품 부자재 추가", type="primary", use_container_width=True):
            if not selected:
                st.warning("추가할 제품을 선택하세요.")
            else:
                set_material_products([labels[label] for label in selected], True)
                st.session_state.pop("material_management_add_selection", None)
                st.success(f"{len(selected)}개 제품을 부자재로 추가했습니다.")
                st.rerun()

    st.markdown("### 등록된 부자재")
    registered = material_products()
    if registered.empty:
        st.info("직접 등록된 부자재가 없습니다.")
        return

    display = registered.rename(columns={"standard_name": "표준제품명", "erp_names": "노투스팜 ERP명"})
    st.dataframe(display, hide_index=True, use_container_width=True)
    labels = _labels(registered)
    remove = st.multiselect(
        "부자재에서 제외할 제품",
        list(labels),
        key="material_management_remove_selection",
    )
    if st.button("선택 제품 부자재 해제", use_container_width=True):
        if not remove:
            st.warning("해제할 제품을 선택하세요.")
        else:
            set_material_products([labels[label] for label in remove], False)
            st.session_state.pop("material_management_remove_selection", None)
            st.success(f"{len(remove)}개 제품을 부자재에서 해제했습니다.")
            st.rerun()
