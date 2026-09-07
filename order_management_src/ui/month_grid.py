"""1~12월을 4x3 원형 버튼 묶음으로 보여주는 월 선택 컴포넌트."""
from __future__ import annotations

from datetime import date


def render_month_grid(st, key_prefix: str, default_year: int | None = None, default_month: int | None = None):
    """연도 이동 화살표와 1~12월 원형 버튼 그리드(4x3)를 그리고 선택된 (year, month)를 반환한다."""
    today = date.today()
    year_key = f"{key_prefix}_year"
    month_key = f"{key_prefix}_month"

    if year_key not in st.session_state:
        st.session_state[year_key] = default_year or today.year
    if month_key not in st.session_state:
        st.session_state[month_key] = default_month or today.month

    st.markdown(
        f"""
        <style>
        div[class*="st-key-{key_prefix}_month_"] button {{
            border-radius: 999px !important;
            aspect-ratio: 1 / 1;
            width: 100%;
            height: auto;
            min-height: 52px;
            padding: 0 !important;
            font-weight: 800;
        }}
        div[class*="st-key-{key_prefix}_year_nav_"] button {{
            border-radius: 999px !important;
            aspect-ratio: 1 / 1;
            width: 100%;
            min-height: 40px;
            padding: 0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    year_cols = st.columns([1, 3, 1])
    with year_cols[0]:
        if st.button("◀", key=f"{key_prefix}_year_nav_prev", use_container_width=True):
            st.session_state[year_key] -= 1
            st.rerun()
    with year_cols[1]:
        st.markdown(
            f"<div style='text-align:center;font-weight:900;font-size:17px;padding-top:6px;'>"
            f"{st.session_state[year_key]}년</div>",
            unsafe_allow_html=True,
        )
    with year_cols[2]:
        if st.button("▶", key=f"{key_prefix}_year_nav_next", use_container_width=True):
            st.session_state[year_key] += 1
            st.rerun()

    for row in range(3):
        cols = st.columns(4, gap="small")
        for col_index in range(4):
            month = row * 4 + col_index + 1
            with cols[col_index]:
                selected = st.session_state[month_key] == month
                if st.button(
                    f"{month}월",
                    key=f"{key_prefix}_month_{month}",
                    use_container_width=True,
                    type="primary" if selected else "secondary",
                ):
                    st.session_state[month_key] = month
                    st.rerun()

    return st.session_state[year_key], st.session_state[month_key]
