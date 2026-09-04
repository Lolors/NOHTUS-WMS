NOHTUS 발주관리 시스템 v17
==========================

핵심 변경점
-----------
- 단가/금액/총금액 완전 제거
- 제품코드/제품명/규격/단위/수량 중심 구조
- 발주서 HTML 템플릿 분리
- 최근 발주 복사
- 자주 주문하는 품목 추천
- 임시저장/발주완료/발주서 목록
- 엑셀/PDF 출력

실행 방법
---------
1. Python 3.11 설치
2. install_once.bat 1회 실행
3. run_app.bat 실행

로고
----
assets/logo.png 또는 app.py 옆 logo.png 를 넣으면 발주서에 자동 적용됩니다.

중요
----
data 폴더의 CSV가 실제 데이터입니다.
공용폴더에서 사용할 경우 data/output 쓰기 권한이 필요합니다.


PDF 다운로드 안내
----------------
v17.5부터 PDF는 발주서 미리보기 HTML을 캡쳐한 이미지 기반으로 생성됩니다.
처음 설치 시 install_once.bat를 실행하면 playwright와 chromium이 함께 설치됩니다.
이미 패키지를 설치해 둔 경우 아래 명령을 한 번 실행하세요.

python -m pip install playwright
python -m playwright install chromium


v17.6 PDF/JPG 출력 안내
----------------------
PDF/JPG는 화면이 열릴 때 자동 생성되지 않습니다.
발주서 미리보기에서 'PDF 생성' 또는 'JPG 생성' 버튼을 눌렀을 때만 생성됩니다.

PDF는 미리보기 HTML을 캡쳐한 이미지를 PDF에 넣는 방식입니다.
미리보기와 다른 ReportLab 기본 양식으로 자동 변환하지 않습니다.

필요 설치:
python -m pip install playwright
python -m playwright install chromium


v17.10 PDF/PNG 버튼 안내
-----------------------
PDF/PNG 캡쳐는 브라우저 보안 때문에 '한 번 클릭으로 파일 생성 + 다운로드'가 불안정할 수 있습니다.
그래서 v17.10에서는 다음 방식으로 안정화했습니다.

1. PDF 또는 PNG 아이콘을 누르면 미리보기 화면을 캡쳐해서 파일을 생성합니다.
2. 생성이 끝나면 같은 위치의 PDF/PNG 아이콘이 다운로드 버튼으로 바뀝니다.
3. 바뀐 버튼을 한 번 더 누르면 파일이 저장됩니다.

명령어를 실행했는데도 오류가 나면, 앱을 실행한 Python과 명령어를 실행한 Python이 다를 가능성이 큽니다.
앱을 실행하는 같은 CMD에서 아래 명령어를 실행하세요.

python -m pip install playwright
python -m playwright install chromium
