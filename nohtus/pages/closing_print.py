from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.closing_date_fix as closing_date_fix


_PRINT_BUTTON_LABEL = "마감 체크리스트 출력"
_OLD_DOWNLOAD_LABEL = "마감 체크리스트 PDF 다운로드"


def _render_print_button(items, ds: str) -> None:
    table_html = closing_date_fix._location_aware_html(items, include_style=False)
    printable_document = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>마감 체크리스트 · {ds}</title>
<style>
@page {{ size: A4 landscape; margin: 10mm; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #111827; font-family: Arial, 'Malgun Gothic', sans-serif; }}
h1 {{ margin: 0 0 4px; font-size: 22px; }}
.print-date {{ margin: 0 0 14px; color: #475569; font-size: 12px; }}
.today-out-table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #94a3b8; font-size: 10px; table-layout: auto; }}
.today-out-table th {{ background: #f1f5f9; color: #111827; font-weight: 800; border: 1px solid #94a3b8; padding: 5px; text-align: center; white-space: nowrap; }}
.today-out-table td {{ border: 1px solid #94a3b8; padding: 5px; vertical-align: middle; color: #111827; word-break: keep-all; }}
.today-out-table td.num {{ text-align: right; font-weight: 700; white-space: nowrap; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
</style>
</head>
<body>
<h1>마감 체크리스트</h1>
<div class="print-date">기준일: {ds}</div>
{table_html}
<script>
window.addEventListener('load', function () {{
  window.focus();
  setTimeout(function () {{ window.print(); }}, 120);
}});
</script>
</body>
</html>"""
    document_json = json.dumps(printable_document, ensure_ascii=False)

    components.html(
        f"""
        <style>
        html, body {{ margin: 0; padding: 0; background: transparent; }}
        .print-button {{
            width: 100%;
            min-height: 40px;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 8px;
            background: white;
            color: #31333f;
            font: 600 14px Arial, 'Malgun Gothic', sans-serif;
            cursor: pointer;
        }}
        .print-button:hover {{ border-color: #ff4b4b; color: #ff4b4b; }}
        </style>
        <button class="print-button" id="closing-print-button" type="button">{_PRINT_BUTTON_LABEL}</button>
        <script>
        const printableDocument = {document_json};
        document.getElementById('closing-print-button').addEventListener('click', function () {{
            const printWindow = window.open('', '_blank', 'noopener,noreferrer');
            if (!printWindow) {{
                alert('인쇄창이 차단되었습니다. 브라우저의 팝업 차단을 해제한 뒤 다시 눌러주세요.');
                return;
            }}
            printWindow.document.open();
            printWindow.document.write(printableDocument);
            printWindow.document.close();
        }});
        </script>
        """,
        height=44,
        scrolling=False,
    )


def page_closing():
    """마감 체크리스트 PDF 다운로드를 브라우저 직접 출력으로 교체한다."""
    original_download_button = st.download_button
    original_location_html = closing_date_fix._location_aware_html
    captured = {"items": None}

    def capturing_location_html(items, *args, **kwargs):
        try:
            captured["items"] = items.copy()
        except Exception:
            captured["items"] = items
        return original_location_html(items, *args, **kwargs)

    def patched_download_button(label, *args, **kwargs):
        if str(label or "").strip() == _OLD_DOWNLOAD_LABEL:
            items = captured.get("items")
            if items is None:
                st.warning("출력할 체크리스트 표를 불러오지 못했습니다.")
                return False
            ds = str(st.session_state.get("closing_date") or "")
            _render_print_button(items, ds)
            return False
        return original_download_button(label, *args, **kwargs)

    closing_date_fix._location_aware_html = capturing_location_html
    st.download_button = patched_download_button
    try:
        return closing_date_fix.page_closing()
    finally:
        closing_date_fix._location_aware_html = original_location_html
        st.download_button = original_download_button
