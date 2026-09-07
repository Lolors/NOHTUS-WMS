"""화면에 보이는 발주서 미리보기를 그대로 PDF/JPG로 저장하는 툴바.

서버에서 별도 브라우저(Playwright)를 새로 띄워 다시 렌더링하는 대신,
사용자가 지금 보고 있는 iframe 안의 DOM을 그대로 인쇄(PDF)하거나
캡처(JPG)한다. WMS 수출 모듈의 "공유용 문서/최종문서" 다운로드 방식과 동일하다.
"""
from __future__ import annotations

import json
import re


def _safe_filename(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or "발주서"


def _print_script(title: str) -> str:
    """window.print()를 부르기 전에 문서 제목을 바꿔서, 브라우저의 'PDF로 저장'
    인쇄 대화상자가 이 제목을 파일명으로 제안하게 한다."""
    encoded_title = json.dumps(title, ensure_ascii=False)
    return f"""<script>
function printPreviewDocument() {{
  const requestedTitle = {encoded_title};
  let hostDocument = document;
  try {{
    if (window.parent && window.parent.document) hostDocument = window.parent.document;
  }} catch (error) {{
    hostDocument = document;
  }}
  const previousHostTitle = hostDocument.title;
  const previousDocumentTitle = document.title;
  hostDocument.title = requestedTitle;
  document.title = requestedTitle;
  let restored = false;
  const restoreTitle = () => {{
    if (restored) return;
    restored = true;
    hostDocument.title = previousHostTitle;
    document.title = previousDocumentTitle;
  }};
  window.addEventListener('afterprint', restoreTitle, {{once: true}});
  window.setTimeout(restoreTitle, 120000);
  window.print();
}}
</script>"""


def _jpg_script(title: str) -> str:
    """html2canvas로 .paper 영역을 화면에 보이는 그대로 캡처해 JPG로 저장한다.

    .paper는 화면에 좁게 들어가도록 transform:scale(0.9)+width:111.11% 트릭을
    쓰는데, html2canvas는 이 transform을 무시하고 축소 전(더 넓은) 크기로
    캡처해버려 여백이 크게 남는다. 캡처 직전에만 잠깐 원래 크기(transform 없음,
    width 100%)로 되돌렸다가 캡처가 끝나면 원래 상태로 복원한다."""
    encoded_filename = json.dumps(f"{title}.jpg", ensure_ascii=False)
    script = """<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script>
function downloadPreviewJpg() {
  const target = document.querySelector('.paper');
  if (!target || typeof html2canvas === 'undefined') {
    alert('이미지 캡처 기능을 불러오지 못했습니다. 인터넷 연결을 확인하고 다시 시도해주세요.');
    return;
  }
  const previousTransform = target.style.transform;
  target.style.transform = 'none';
  const restore = () => {
    target.style.transform = previousTransform;
  };
  html2canvas(target, {scale: 2, backgroundColor: '#ffffff', useCORS: true}).then(function(canvas) {
    restore();
    const link = document.createElement('a');
    link.download = FILENAME_PLACEHOLDER;
    link.href = canvas.toDataURL('image/jpeg', 0.92);
    link.click();
  }).catch(function() {
    restore();
    alert('JPG 저장에 실패했습니다. 다시 시도해주세요.');
  });
}
</script>"""
    return script.replace("FILENAME_PLACEHOLDER", encoded_filename)


_TOOLBAR_STYLE = """<style>
.preview-export-toolbar {
    width: 100%;
    padding: 8px 0 12px;
    text-align: right;
}
.preview-export-toolbar button {
    border-radius: 8px;
    font-weight: 700;
    padding: 8px 16px;
    cursor: pointer;
    margin-left: 8px;
    font-size: 13px;
}
.preview-export-toolbar .btn-print {
    border: 0;
    background: #173b5f;
    color: #fff;
}
.preview-export-toolbar .btn-jpg {
    border: 1px solid #173b5f;
    background: #fff;
    color: #173b5f;
}
@media print {
    .preview-export-toolbar { display: none !important; }
    /* .paper는 화면에 좁게 맞추려고 transform:scale(0.9)를 쓰는데, 인쇄 시에는
       이 축소를 빼는 대신 width:111.111%(원래 디자인 폭)는 그대로 둬서 실제
       디자인 크기로 찍히게 한다. width까지 100%로 누르면 오히려 내용이
       좁아져 줄바꿈이 늘고 셀 안 여백이 커진다. */
    .paper {
        transform: none !important;
    }
}
</style>"""


def inject_export_toolbar(html: str, filename_base: str) -> str:
    """미리보기 HTML의 <body> 안에 인쇄(PDF)/JPG 저장 버튼을 심는다."""
    title = _safe_filename(filename_base)
    scripts = _print_script(title) + _jpg_script(title)
    head_addition = _TOOLBAR_STYLE + scripts
    if "</head>" in html:
        html = html.replace("</head>", head_addition + "</head>", 1)
    else:
        html = head_addition + html

    toolbar = (
        '<div class="preview-export-toolbar">'
        '<button class="btn-jpg" onclick="downloadPreviewJpg()">JPG 저장</button>'
        '<button class="btn-print" onclick="printPreviewDocument()">PDF로 인쇄/저장</button>'
        "</div>"
    )
    if "<body>" in html:
        html = html.replace("<body>", "<body>" + toolbar, 1)
    else:
        html = toolbar + html
    return html
