"""제품코드를 기준으로 별칭 연결을 안전하게 유지하는 별칭 관리 모듈."""

import re

import pandas as pd
import streamlit as st

import app_pdf_png_flow as flow

base_app = flow.base_app
ALIAS_COLUMNS = ["거래처명", "별칭", "제품코드"]
PRODUCT_CODE_WIDTH = 5


def normalize_product_code(value):
    """ERP 제품코드를 선행 0이 유지되는 5자리 문자열로 정리합니다."""
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()
    if not text:
        return ""

    # 엑셀에서 숫자로 읽힌 131.0 같은 값도 00131로 복원합니다.
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]

    if text.isdigit():
        return text.zfill(PRODUCT_CODE_WIDTH)

    return text


def normalize_alias_table(df):
    """별칭 원본 3개 컬럼만 안전하게 정리합니다."""
    if df is None:
        return pd.DataFrame(columns=ALIAS_COLUMNS)

    clean = pd.DataFrame(index=df.index)
    for col in ALIAS_COLUMNS:
        if col in df.columns:
            value = df[col]
            # 같은 이름의 중복 컬럼이 생긴 경우 첫 번째 컬럼만 사용합니다.
            if isinstance(value, pd.DataFrame):
                value = value.iloc[:, 0]
            clean[col] = value
        else:
            clean[col] = ""

    clean = clean.fillna("")
    clean["거래처명"] = clean["거래처명"].astype(str).str.strip()
    clean["별칭"] = clean["별칭"].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)

    clean = clean[(clean["별칭"] != "") & (clean["제품코드"] != "")]
    return clean[ALIAS_COLUMNS].reset_index(drop=True)


def _product_lookup(products):
    """현재 제품목록을 제품코드 기준 조회표로 만듭니다."""
    product_df = products.copy().fillna("")
    if "정식제품명" not in product_df.columns:
        product_df["정식제품명"] = product_df.get("제품명", "")
    if "단위" not in product_df.columns:
        product_df["단위"] = product_df.get("포장단위", "")

    for col in ["정식제품명", "규격", "단위"]:
        if col not in product_df.columns:
            product_df[col] = ""
        product_df[col] = product_df[col].astype(str).str.strip()

    if "제품코드" not in product_df.columns:
        product_df["제품코드"] = ""
    product_df["제품코드"] = product_df["제품코드"].map(normalize_product_code)

    product_df = product_df[product_df["제품코드"] != ""]
    product_df = product_df.drop_duplicates("제품코드", keep="last")
    return product_df.set_index("제품코드", drop=False)


def page_alias_manage(vendors, products, aliases):
    st.markdown("## 별칭 관리")
    st.caption("별칭은 변하지 않는 제품코드에 연결됩니다. 제품목록을 교체해도 같은 제품코드의 현재 제품정보를 다시 불러옵니다.")

    aliases = normalize_alias_table(aliases)
    lookup = _product_lookup(products)
    vendor_options = ["전체"] + vendors["거래처명"].dropna().astype(str).drop_duplicates().tolist()

    with st.container(border=True):
        st.markdown("### 신규 별칭 추가")
        selected_vendor = st.selectbox("거래처", vendor_options, key="alias_new_vendor")
        new_alias = st.text_input("별칭", key="alias_new_name")

        product_codes = [code for code in lookup.index.astype(str).tolist() if code.strip()]
        selected_product_code = st.selectbox(
            "연결 제품",
            product_codes,
            format_func=lambda code: f'{lookup.loc[code, "정식제품명"]} ({code})',
            key="alias_new_product",
        ) if product_codes else None

        if st.button("별칭 추가", type="primary", use_container_width=True):
            if not new_alias.strip():
                st.warning("별칭을 입력하세요.")
            elif not selected_product_code:
                st.warning("연결할 제품을 선택하세요.")
            else:
                normalized_code = normalize_product_code(selected_product_code)
                duplicate = aliases[
                    (aliases["거래처명"] == selected_vendor)
                    & (aliases["별칭"] == new_alias.strip())
                    & (aliases["제품코드"] == normalized_code)
                ]
                if not duplicate.empty:
                    st.warning("이미 등록된 별칭입니다.")
                else:
                    new_row = pd.DataFrame([{
                        "거래처명": selected_vendor,
                        "별칭": new_alias.strip(),
                        "제품코드": normalized_code,
                    }])
                    base_app.save_aliases(normalize_alias_table(pd.concat([aliases, new_row], ignore_index=True)))
                    st.success("별칭을 추가했습니다.")
                    st.rerun()

    st.markdown("### 별칭 목록 수정")
    if aliases.empty:
        st.info("등록된 별칭이 없습니다.")
        return

    # 별칭 원본은 그대로 두고 제품정보는 제품코드로 조회해서 화면 표시용으로만 붙입니다.
    view = aliases.copy()
    view["제품명"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "정식제품명"] if code in lookup.index else "현재 제품목록에 없음"
    )
    view["규격"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "규격"] if code in lookup.index else ""
    )
    view["포장단위"] = view["제품코드"].map(
        lambda code: lookup.loc[code, "단위"] if code in lookup.index else ""
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
        key="alias_editor_product_code_link",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("별칭 수정 저장", use_container_width=True):
            # 삭제 체크 여부와 제품 표시정보는 무시하고 별칭 원본 3개 컬럼만 저장합니다.
            clean = normalize_alias_table(edited)
            base_app.save_aliases(clean)
            st.success("별칭 정보를 저장했습니다.")
            st.rerun()

    with c2:
        if st.button("선택 별칭 삭제", use_container_width=True):
            remaining = edited.loc[edited["삭제"] != True].copy()
            clean = normalize_alias_table(remaining)
            base_app.save_aliases(clean)
            st.success("선택한 별칭을 삭제했습니다.")
            st.rerun()


base_app.page_alias_manage = page_alias_manage


if __name__ == "__main__":
    base_app.main()
