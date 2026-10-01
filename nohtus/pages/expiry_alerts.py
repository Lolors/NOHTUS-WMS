"""유통기한 임박 재고를 사업장/로케이션/제조번호별 표로 표시한다."""
from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v2 as components

from nohtus.mobile_api import queries as mobile_queries
from nohtus.pages.product_photo_input import render_photo_input
from nohtus.services.expiry_rules import expiry_badge_for_date_text
from nohtus.services.stock_rules import is_export_waiting_location
from nohtus.services.product_images import get_product_image_path, product_jpeg_preview

WAREHOUSE_OPTIONS = [("창고 전체", "all"), ("용인창고", "yongin"), ("화성창고", "hwaseong")]
PERIOD_OPTIONS = [("3개월 이내", "3m"), ("6개월 이내", "6m"), ("1년 이내", "1y")]


@st.cache_resource
def _get_expiry_responsive_layout():
    return components.component(
        "expiry_responsive_layout",
        js="""
        export default function(component) {
            const page = component.parentElement.closest('.st-key-expiry_alert_page');
            if (!page) return;
            const main = page.closest('[data-testid="stMainBlockContainer"], .block-container') || page.parentElement;
            const updateWidth = () => {
                const style = getComputedStyle(main);
                const available = main.clientWidth - parseFloat(style.paddingLeft || 0) - parseFloat(style.paddingRight || 0);
                // Restore the space lost by resizing the browser, so 40% is
                // based on the maximized content width, not the current window.
                const windowGap = Math.max(0, window.screen.availWidth - window.outerWidth);
                const target = Math.round((available + windowGap) * 0.4);
                if (target > 0) page.style.setProperty('--expiry-page-width', `${target}px`);
            };
            const observer = new ResizeObserver(updateWidth);
            observer.observe(main);
            window.addEventListener('resize', updateWidth);
            updateWidth();
            return () => {
                observer.disconnect();
                window.removeEventListener('resize', updateWidth);
            };
        }
        """,
        isolate_styles=False,
    )


@st.cache_resource
def _get_expiry_photo_table():
    return components.component(
        "expiry_photo_table",
        html='<div class="expiry-table-content"></div>',
        js="""
        export default function(component) {
            const { data, parentElement, setTriggerValue } = component;
            const root = parentElement.querySelector('.expiry-table-content');
            root.innerHTML = data;
            const onClick = (event) => {
                const button = event.target.closest('button[data-product]');
                if (button && root.contains(button)) {
                    setTriggerValue('photo', button.dataset.product);
                }
            };
            root.addEventListener('click', onClick);
            return () => root.removeEventListener('click', onClick);
        }
        """,
        isolate_styles=False,
    )


@st.dialog("제품 사진 보기 · 변경", width="large")
def _expiry_photo_dialog(product_name: str):
    # 기존 제품 사진 저장 경로를 재사용하여 원본과 썸네일을 함께 갱신한다.
    from nohtus.pages.location_map import _safe_product_image_stem, _save_product_image

    st.markdown(
        """
        <span class="expiry-photo-dialog-marker" style="display:none"></span>
        <style>
        [role="dialog"]:has(.expiry-photo-dialog-marker) {
            max-height:90vh !important;
            max-height:90dvh !important;
            overflow-y:auto !important;
            box-sizing:border-box;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption(product_name)
    photo_col, input_col = st.columns([1, 1], gap="large")
    with photo_col:
        image_path = get_product_image_path(product_name)
        if image_path:
            from streamlit import runtime
            try:
                jpeg = product_jpeg_preview(image_path)
            except (OSError, ValueError) as exc:
                st.error(f"사진을 불러오지 못했습니다: {exc}")
            else:
                filename = f"{_safe_product_image_stem(product_name)}.jpg"
                # A real .jpg URL and explicit download filename prevent Windows
                # MIME registry defaults from naming data-URL downloads .jfif.
                url = runtime.get_instance().media_file_mgr.add(
                    jpeg, "image/jpeg", f"product-photo-preview-{product_name}",
                    file_name=filename, is_for_static_download=True,
                )
                url = url.rsplit(".", 1)[0] + ".jpg"
                st.caption("미리보기 400px · JPG 저장 시 너비 800px")
                st.markdown(
                    '<div style="overflow:auto;max-height:55vh;">'
                    f'<img src="{html.escape(url, quote=True)}" alt="제품 사진" '
                    'style="display:block;width:400px;max-width:100%;height:auto;margin:0 auto;">'
                    '</div>', unsafe_allow_html=True,
                )
        else:
            st.info("현재 등록된 제품 사진이 없습니다.")
    with input_col:
        uploaded = render_photo_input(
            key_prefix=f"expiry_photo_{product_name}",
            upload_key=f"expiry_photo_upload_{product_name}",
        )
        with st.container(horizontal=True, horizontal_alignment="center"):
            if st.button("사진 저장", type="primary", disabled=uploaded is None,
                         key=f"expiry_photo_save_{product_name}"):
                try:
                    _save_product_image(product_name, uploaded)
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
                else:
                    st.rerun()



def _inject_css():
    st.markdown("""
    <style>
    .st-key-expiry_alert_page { width: min(100%, var(--expiry-page-width, 40%)); min-width: 0; }
    .st-key-expiry_responsive_layout { display: none; }
    .expiry-table-content { width: 100%; min-width: 0; }
    .expiry-table-wrap { width: 100%; box-sizing: border-box; border: 1px solid #e5e8ee; border-radius: 10px; }
    .expiry-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 12px; }
    .expiry-table th { background: #f8fafc; text-align: left; white-space: normal; }
    .expiry-table th, .expiry-table td { padding: 8px 4px; border-bottom: 1px solid #e5e8ee; vertical-align: middle; overflow-wrap: anywhere; white-space: normal; }
    .expiry-table tr:last-child td { border-bottom: 0; }
    .expiry-table .expiry-name { min-width: 0; overflow-wrap: anywhere; }
    .expiry-table .expiry-qty { text-align: right; white-space: normal; font-weight: 750; }
    .expiry-table .expiry-photo { text-align: center; }
    .expiry-photo-button { border: 0; padding: 0; background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; width: 100%; max-width: 40px; min-width: 0; min-height: 32px; }
    .expiry-photo-button:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
    .expiry-date { white-space: normal; }
    .expiry-thumb { width: 100%; max-width: 40px; height: auto; aspect-ratio: 1; object-fit: contain; border-radius: 6px; }
    .expiry-badge { display: inline-block; padding: 2px 6px; border-radius: 999px; font-size: 10px; font-weight: 750; white-space: normal; max-width: 100%; box-sizing: border-box; overflow-wrap: anywhere; margin-top: 3px; }
    .expiry-badge.red { background: #fee2e2; color: #b91c1c; }
    .expiry-badge.yellow { background: #fef3c7; color: #a16207; }
    .expiry-badge.blue { background: #dbeafe; color: #1d4ed8; }
    .expiry-badge.export { background: #e0f2fe; color: #0369a1; }
    </style>
    """, unsafe_allow_html=True)


def _inventory_table_html(inventory, *, show_photo=True):
    rows_html = []
    thumbnails = {}
    for row in inventory.sort_values(["_expiry", "product_name", "company", "location", "lot"]).itertuples(index=False):
        name = str(row.product_name or "")
        photo_cell = ""
        if show_photo:
            if name not in thumbnails:
                thumbnails[name] = mobile_queries.thumbnail_data_uri(name)
            thumbnail = thumbnails[name]
            photo = f'<img class="expiry-thumb" src="{html.escape(thumbnail, quote=True)}" alt="">' if thumbnail else '📷'
            photo_cell = (
                '<td class="expiry-photo"><button type="button" class="expiry-photo-button" '
                f'data-product="{html.escape(name, quote=True)}" '
                f'aria-label="{html.escape(name, quote=True)} 사진 보기 및 변경" '
                f'title="사진 원본 보기 · 변경">{photo}</button></td>'
            )
        badge = expiry_badge_for_date_text(str(row.exp_date or ""))
        date_text = badge["date"] if badge else str(row.exp_date or "")
        badge_html = f'<br><span class="expiry-badge {badge["level"]}">{html.escape(badge["label"])}</span>' if badge else ""
        waiting = '<br><span class="expiry-badge export">수출대기</span>' if is_export_waiting_location(row.location) else ""
        rows_html.append(
            f'<tr>{photo_cell}'
            f'<td>{html.escape(str(row.company or "-"))}</td>'
            f'<td>{html.escape(str(row.location or "-"))}{waiting}</td>'
            f'<td class="expiry-name">{html.escape(name)}</td>'
            f'<td>{html.escape(str(row.lot or "-"))}</td>'
            f'<td class="expiry-date">{html.escape(date_text)}{badge_html}</td>'
            f'<td class="expiry-qty">{int(row.qty or 0):,}개</td></tr>'
        )
    photo_header = '<th class="expiry-photo">사진</th>' if show_photo else ""
    # Fixed-layout table columns use percentages only; mixed calc() widths
    # on <col> can fall back to automatic allocation and widen both columns.
    widths = [7, 10, 9, 40, 14, 13, 7] if show_photo else [11, 10, 44, 14, 14, 7]
    columns = '<colgroup>' + ''.join(f'<col style="width:{width}%">' for width in widths) + '</colgroup>'
    return (
        f'<div class="expiry-table-wrap"><table class="expiry-table">{columns}<thead><tr>'
        f'{photo_header}<th>사업장</th><th>로케이션</th><th>제품명</th>'
        '<th>제조번호</th><th>유효</th><th class="expiry-qty">수량</th>'
        '</tr></thead><tbody>' + ''.join(rows_html) + '</tbody></table></div>'
    )


def page_expiry_alerts():
    _inject_css()
    with st.container(key="expiry_alert_page"):
        _get_expiry_responsive_layout()(key="expiry_responsive_layout", height=0)
        st.title("유통기한 임박")
        f1, f2, f3, f4 = st.columns([1, 1, 1.25, 1.15], gap="small", vertical_alignment="bottom")
        warehouse_label = f1.selectbox("창고", [label for label, _ in WAREHOUSE_OPTIONS], index=1, key="expiry_alert_warehouse")
        period_label = f2.selectbox("기간", [label for label, _ in PERIOD_OPTIONS], index=2, key="expiry_alert_period")
        scope_label = f3.radio("구분", ["자료", "비자료"], horizontal=True, key="expiry_alert_scope")
        exclude_export_waiting = f4.checkbox("수출대기 제외", value=True, key="expiry_alert_exclude_export_waiting")
        inventory = mobile_queries.expiry_inventory(
            period=dict(PERIOD_OPTIONS)[period_label],
            bidata_scope="bidata" if scope_label == "비자료" else "data",
            warehouse=dict(WAREHOUSE_OPTIONS)[warehouse_label],
        )
        if exclude_export_waiting and not inventory.empty:
            inventory = inventory.loc[~inventory["location"].apply(is_export_waiting_location)]
        if inventory.empty:
            st.info("조건에 맞는 임박재고가 없습니다.")
            return
        photo_event = _get_expiry_photo_table()(
            data=_inventory_table_html(inventory),
            key="expiry_inventory_photo_table",
            on_photo_change=lambda: None,
        )
        selected_product = photo_event.photo
        if selected_product and selected_product in set(inventory["product_name"].astype(str)):
            _expiry_photo_dialog(selected_product)
