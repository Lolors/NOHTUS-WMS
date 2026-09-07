"""1~12월을 4x3 원형 버튼 묶음으로 보여주는 월 선택 컴포넌트."""
from __future__ import annotations

from datetime import date


def render_month_grid(
    st,
    key_prefix: str,
    default_year: int | None = None,
    default_month: int | None = None,
    scale: float = 1.0,
    year_font_scale: float = 1.0,
    side_content=None,
):
    """연도 이동 화살표와 1~12월 원형 버튼 그리드(4x3)를 그리고 선택된 (year, month)를 반환한다.

    scale: 전체 박스(연도 영역 + 원형 버튼)의 크기 배율. 1.0이 원래 크기이며,
    0.25를 주면 박스와 원형 버튼이 모두 25% 크기로 줄어든다.
    year_font_scale: 연도 숫자("2026년") 글자 크기에만 추가로 곱해지는 배율.
    side_content: scale이 1보다 작을 때 남는 오른쪽 여백에 그릴 콜백. 인자 없이 호출된다.
    """
    today = date.today()
    year_key = f"{key_prefix}_year"
    month_key = f"{key_prefix}_month"

    if year_key not in st.session_state:
        st.session_state[year_key] = default_year or today.year
    if month_key not in st.session_state:
        st.session_state[month_key] = default_month or today.month

    month_button_height = max(14, round(52 * scale))
    year_nav_height = max(12, round(40 * scale))
    year_font_size = max(6, round(17 * scale * year_font_scale))

    st.markdown(
        f"""
        <style>
        div[class*="st-key-{key_prefix}_month_"] button {{
            border-radius: 999px !important;
            aspect-ratio: 1 / 1;
            width: 100%;
            height: auto;
            min-height: {month_button_height}px;
            padding: 0 !important;
            font-weight: 800;
            font-size: {max(8, round(13 * scale))}px;
        }}
        div[class*="st-key-{key_prefix}_year_nav_"] button {{
            border-radius: 999px !important;
            aspect-ratio: 1 / 1;
            width: 100%;
            min-height: {year_nav_height}px;
            padding: 0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    spacer = None
    if scale < 1:
        box_col, spacer = st.columns([scale, 1 - scale])
    else:
        box_col = st.container()

    with box_col:
        year_cols = st.columns([1, 3, 1])
        with year_cols[0]:
            if st.button("◀", key=f"{key_prefix}_year_nav_prev", use_container_width=True):
                st.session_state[year_key] -= 1
                st.rerun()
        with year_cols[1]:
            st.markdown(
                f"<div style='text-align:center;font-weight:900;font-size:{year_font_size}px;padding-top:6px;'>"
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

    if side_content is not None and spacer is not None:
        with spacer:
            side_content()

    return st.session_state[year_key], st.session_state[month_key]
