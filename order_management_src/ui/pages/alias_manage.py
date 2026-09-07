"""별칭 관리 전용 화면."""
from __future__ import annotations

import pandas as pd

from db_migration import normalize_product_code
from ui.pages import catalog


def render(core_app, data) -> None:
    st = core_app.st
    vendors_df = catalog._normalize_vendors(data["vendors"])
    products_df = catalog._normalize_products(data["products"])
    aliases_df = catalog._normalize_aliases(data["aliases"])

    st.markdown("## 별칭 관리")
    st.caption("별칭은 제품코드에 연결되며, 제품목록을 교체해도 같은 제품코드의 최신 정보가 유지됩니다.")

    lookup = products_df.set_index("제품코드", drop=False) if not products_df.empty else pd.DataFrame()
    vendor_options = ["전체"] + vendors_df["거래처명"].drop_duplicates().tolist()

    with st.container(border=True):
        st.markdown("### 신규 별칭 추가")
        c1, c2, c3, c4 = st.columns([2, 2, 3, 3], gap="small")
        selected_vendor = c1.selectbox("거래처", vendor_options, key="alias_new_vendor")
        alias_name = c2.text_input("별칭", key="alias_new_name")
        keyword = c3.text_input(
            "연결 제품 검색",
            placeholder="제품명·제품코드·규격 검색",
            key="alias_new_product_search",
        )

        candidates = products_df.copy()
        keyword_text = str(keyword or "").strip()
        if keyword_text:
            mask = (
                candidates["제품코드"].astype(str).str.contains(keyword_text, case=False, na=False, regex=False)
                | candidates["제품명"].astype(str).str.contains(keyword_text, case=False, na=False, regex=False)
                | candidates["규격"].astype(str).str.contains(keyword_text, case=False, na=False, regex=False)
            )
            candidates = candidates[mask]
        candidates = candidates.head(100)
        candidate_codes = candidates["제품코드"].tolist()
        selected_code = c4.selectbox(
            "연결 제품",
            candidate_codes,
            format_func=lambda code: f'{lookup.loc[code, "제품명"]} | {lookup.loc[code, "규격"]} | {lookup.loc[code, "포장단위"]} ({code})',
            key="alias_new_product",
        ) if candidate_codes else None
        if not candidate_codes:
            c4.caption("검색 결과가 없습니다.")

        if st.button("별칭 추가", type="primary", use_container_width=True, key="alias_new_add"):
            if not alias_name.strip():
                st.warning("별칭을 입력하세요.")
            elif not selected_code:
                st.warning("연결할 제품을 선택하세요.")
            else:
                row = pd.DataFrame([{
                    "거래처명": selected_vendor,
                    "별칭": alias_name.strip(),
                    "제품코드": normalize_product_code(selected_code),
                }])
                combined = catalog._normalize_aliases(pd.concat([aliases_df, row], ignore_index=True))
                if len(combined) == len(aliases_df):
                    st.warning("이미 등록된 별칭입니다.")
                else:
                    core_app.save_aliases(combined)
                    st.success("별칭을 추가했습니다.")
                    st.rerun()

    st.markdown("### 별칭 목록 수정")
    if aliases_df.empty:
        st.info("등록된 별칭이 없습니다.")
        return

    view = aliases_df.copy()
    view["제품명"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "제품명"] if not lookup.empty and code in lookup.index else "현재 제품목록에 없음"
    )
    view["규격"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "규격"] if not lookup.empty and code in lookup.index else ""
    )
    view["포장단위"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "포장단위"] if not lookup.empty and code in lookup.index else ""
    )
    view.insert(0, "삭제", False)
    edited = st.data_editor(
        view[["삭제", "거래처명", "별칭", "제품코드", "제품명", "규격", "포장단위"]],
        use_container_width=True,
        hide_index=True,
        disabled=["제품코드", "제품명", "규격", "포장단위"],
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제"),
            "거래처명": st.column_config.SelectboxColumn("거래처명", options=vendor_options),
            "제품코드": st.column_config.TextColumn("제품코드"),
        },
        key="alias_manage_editor",
    )
    save_col, delete_col = st.columns(2)
    if save_col.button("별칭 수정 저장", use_container_width=True, key="alias_manage_save"):
        core_app.save_aliases(catalog._normalize_aliases(edited))
        st.success("별칭 정보를 저장했습니다.")
        st.rerun()
    if delete_col.button("선택 별칭 삭제", use_container_width=True, key="alias_manage_delete"):
        remaining = edited.loc[edited["삭제"] != True]
        core_app.save_aliases(catalog._normalize_aliases(remaining))
        st.success("선택한 별칭을 삭제했습니다.")
        st.rerun()
