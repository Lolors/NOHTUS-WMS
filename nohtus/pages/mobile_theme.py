"""모바일 재고 화면 전용 디자인 토큰과 공용 컴포넌트.

기존 mobile_stock_layout_patch* 체인이 각자 CSS를 중복 정의하고 있어,
새로 추가하는 스타일(하단 탭바, 상단바, 카드 그림자, 위치별 카드 리스트)만
이 모듈 하나로 모아 둔다. 기존 파일들의 CSS는 그대로 두고 이 모듈을
가장 나중에 주입해 필요한 부분만 덮어쓴다.
"""

import html

import streamlit as st


def inject_mobile_theme():
    st.markdown(
        """
        <style>
        :root {
            --wms-primary: #2563eb;
            --wms-primary-soft: rgba(37, 99, 235, .08);
            --wms-bg: #f3f5f9;
            --wms-surface: #ffffff;
            --wms-border: #e5e8ee;
            --wms-shadow: 0 1px 3px rgba(15, 23, 42, .07), 0 1px 2px rgba(15, 23, 42, .04);
            --wms-radius-lg: 16px;
            --wms-radius-md: 12px;
            --wms-text: #182033;
            --wms-text-muted: #6b7280;
        }

        @media (max-width: 768px) {
            [data-testid="stAppViewContainer"], .stApp {
                background: var(--wms-bg) !important;
            }

            .wms-app-bar {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 8px 2px 4px;
                font-weight: 800;
                font-size: 15px;
                color: var(--wms-text);
                position: relative;
                top: 48px;
            }
            .wms-app-bar-icon { font-size: 18px; line-height: 1; }

            /* 카드 그림자/배경 — 기존 st.container(border=True) 카드를 앱스러운 카드로 */
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlockBorderWrapper"] {
                background: var(--wms-surface) !important;
                border-color: var(--wms-border) !important;
                box-shadow: var(--wms-shadow) !important;
            }

            /* 밑줄 탭을 알약형 세그먼트 컨트롤로 전환 (앱바 바로 아래, 상단 고정) */
            div[data-testid="stTabs"] [data-baseweb="tab-list"] {
                background: #e9ecf2 !important;
                border: 0 !important;
                border-radius: 999px !important;
                box-shadow: none !important;
                padding: 4px !important;
                gap: 4px !important;
                margin: 2px 0 14px !important;
            }
            div[data-testid="stTabs"] button[data-baseweb="tab"] {
                flex: 1 1 0 !important;
                justify-content: center !important;
                min-height: 40px !important;
                border-radius: 999px !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                color: var(--wms-text-muted) !important;
                transition: background .15s ease, color .15s ease;
            }
            div[data-testid="stTabs"] button[aria-selected="true"] {
                color: var(--wms-text) !important;
                background: var(--wms-surface) !important;
                box-shadow: var(--wms-shadow) !important;
                font-weight: 800 !important;
            }
            div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
            div[data-testid="stTabs"] [data-baseweb="tab-border"] {
                display: none !important;
            }
            div[data-testid="stTabs"] [data-baseweb="tab-panel"] {
                padding-top: 0 !important;
            }

            /* 위치별 재고 상세를 표 대신 리스트 카드로 */
            .wms-loc-list {
                border: 1px solid var(--wms-border);
                border-radius: var(--wms-radius-md);
                overflow: hidden;
                background: var(--wms-surface);
                box-shadow: var(--wms-shadow);
            }
            .wms-loc-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                padding: 12px 14px;
                border-bottom: 1px solid var(--wms-border);
            }
            .wms-loc-row:last-child { border-bottom: 0; }
            .wms-loc-name {
                font-size: 14px;
                font-weight: 750;
                color: var(--wms-text);
                margin-bottom: 2px;
            }
            .wms-loc-meta {
                font-size: 11.5px;
                color: var(--wms-text-muted);
            }
            .wms-loc-qty {
                font-size: 15px;
                font-weight: 800;
                color: var(--wms-text);
                white-space: nowrap;
            }
            .wms-loc-empty {
                padding: 22px 14px;
                text-align: center;
                color: var(--wms-text-muted);
                font-size: 13px;
                border: 1px dashed var(--wms-border);
                border-radius: var(--wms-radius-md);
                background: var(--wms-surface);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_bar(title="NOHTUS WMS", icon="📦"):
    st.markdown(
        f'<div class="wms-app-bar">'
        f'<span class="wms-app-bar-icon">{html.escape(icon)}</span>'
        f'<span>{html.escape(title)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_location_cards(df, empty_message="표시할 재고 내역이 없습니다."):
    """사업장/로케이션/제조번호/유통기한/수량 컬럼을 가진 df를 카드 리스트로 렌더링."""
    if df is None or df.empty:
        st.markdown(
            f'<div class="wms-loc-empty">{html.escape(empty_message)}</div>',
            unsafe_allow_html=True,
        )
        return

    rows_html = []
    for _, row in df.iterrows():
        company = str(row.get("사업장", "") or "").strip()
        location = str(row.get("로케이션", "") or "").strip()
        lot = str(row.get("제조번호", "") or "").strip()
        exp = str(row.get("유통기한", "") or "").strip()
        qty = row.get("수량", 0)
        try:
            qty_text = f"{int(qty):,}개"
        except (TypeError, ValueError):
            qty_text = str(qty)

        meta_parts = [p for p in [company, f"LOT {lot}" if lot else "", f"유통기한 {exp}" if exp else ""] if p]
        meta = " · ".join(meta_parts)
        rows_html.append(
            '<div class="wms-loc-row">'
            '<div>'
            f'<div class="wms-loc-name">{html.escape(location or "-")}</div>'
            f'<div class="wms-loc-meta">{html.escape(meta)}</div>'
            '</div>'
            f'<div class="wms-loc-qty">{html.escape(qty_text)}</div>'
            '</div>'
        )

    st.markdown(f'<div class="wms-loc-list">{"".join(rows_html)}</div>', unsafe_allow_html=True)
