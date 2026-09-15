"""국가명(한글 표기) → 국기 이모지.

mobile_app/app.js의 COUNTRY_CODES와 같은 데이터를 Python 쪽에서도 쓸 수 있게
따로 둔 모듈. 이모지는 ISO 3166-1 alpha-2 코드로부터 유니코드 regional
indicator 조합으로 계산하므로, 새 나라가 필요하면 이모지를 따로 찾을 필요
없이 코드 한 줄만 추가하면 된다.
"""

from __future__ import annotations

COUNTRY_CODES = {
    "국내": "KR", "한국": "KR", "대한민국": "KR", "북한": "KP",
    # 아시아
    "일본": "JP", "중국": "CN", "대만": "TW", "홍콩": "HK", "마카오": "MO",
    "몽골": "MN", "베트남": "VN", "태국": "TH", "필리핀": "PH", "말레이시아": "MY",
    "싱가포르": "SG", "인도네시아": "ID", "미얀마": "MM", "캄보디아": "KH",
    "라오스": "LA", "브루나이": "BN", "동티모르": "TL", "인도": "IN",
    "파키스탄": "PK", "방글라데시": "BD", "스리랑카": "LK", "네팔": "NP",
    "부탄": "BT", "몰디브": "MV", "아프가니스탄": "AF",
    "카자흐스탄": "KZ", "우즈베키스탄": "UZ", "투르크메니스탄": "TM",
    "타지키스탄": "TJ", "키르기스스탄": "KG", "조지아": "GE", "아르메니아": "AM",
    "아제르바이잔": "AZ", "튀르키예": "TR", "터키": "TR",
    "이란": "IR", "이라크": "IQ", "시리아": "SY", "레바논": "LB", "요르단": "JO",
    "이스라엘": "IL", "팔레스타인": "PS", "사우디아라비아": "SA",
    "아랍에미리트": "AE", "UAE": "AE", "카타르": "QA", "쿠웨이트": "KW",
    "바레인": "BH", "오만": "OM", "예멘": "YE",
    # 유럽
    "러시아": "RU", "우크라이나": "UA", "벨라루스": "BY", "폴란드": "PL",
    "체코": "CZ", "슬로바키아": "SK", "헝가리": "HU", "루마니아": "RO",
    "불가리아": "BG", "몰도바": "MD", "세르비아": "RS", "크로아티아": "HR",
    "슬로베니아": "SI", "보스니아헤르체고비나": "BA", "몬테네그로": "ME",
    "북마케도니아": "MK", "알바니아": "AL", "그리스": "GR", "이탈리아": "IT",
    "스페인": "ES", "포르투갈": "PT", "프랑스": "FR", "독일": "DE",
    "오스트리아": "AT", "스위스": "CH", "리히텐슈타인": "LI", "네덜란드": "NL",
    "벨기에": "BE", "룩셈부르크": "LU", "영국": "GB", "아일랜드": "IE",
    "아이슬란드": "IS", "덴마크": "DK", "노르웨이": "NO", "스웨덴": "SE",
    "핀란드": "FI", "에스토니아": "EE", "라트비아": "LV", "리투아니아": "LT",
    "몰타": "MT", "키프로스": "CY", "산마리노": "SM", "모나코": "MC",
    "안도라": "AD", "바티칸": "VA",
    # 아프리카
    "이집트": "EG", "리비아": "LY", "튀니지": "TN", "알제리": "DZ",
    "모로코": "MA", "수단": "SD", "남수단": "SS", "에티오피아": "ET",
    "에리트레아": "ER", "지부티": "DJ", "소말리아": "SO", "케냐": "KE",
    "우간다": "UG", "탄자니아": "TZ", "르완다": "RW", "부룬디": "BI",
    "콩고민주공화국": "CD", "콩고공화국": "CG", "가봉": "GA", "적도기니": "GQ",
    "카메룬": "CM", "중앙아프리카공화국": "CF", "차드": "TD", "니제르": "NE",
    "나이지리아": "NG", "베냉": "BJ", "토고": "TG", "가나": "GH",
    "코트디부아르": "CI", "라이베리아": "LR", "시에라리온": "SL", "기니": "GN",
    "기니비사우": "GW", "세네갈": "SN", "감비아": "GM", "말리": "ML",
    "부르키나파소": "BF", "모리타니": "MR", "카보베르데": "CV",
    "남아프리카공화국": "ZA", "나미비아": "NA", "보츠와나": "BW",
    "짐바브웨": "ZW", "잠비아": "ZM", "말라위": "MW", "모잠비크": "MZ",
    "마다가스카르": "MG", "모리셔스": "MU", "세이셸": "SC", "코모로": "KM",
    "레소토": "LS", "에스와티니": "SZ", "앙골라": "AO",
    # 아메리카
    "미국": "US", "캐나다": "CA", "멕시코": "MX", "과테말라": "GT",
    "벨리즈": "BZ", "온두라스": "HN", "엘살바도르": "SV", "니카라과": "NI",
    "코스타리카": "CR", "파나마": "PA", "쿠바": "CU", "자메이카": "JM",
    "아이티": "HT", "도미니카공화국": "DO", "바하마": "BS",
    "트리니다드토바고": "TT", "바베이도스": "BB", "콜롬비아": "CO",
    "베네수엘라": "VE", "가이아나": "GY", "수리남": "SR", "에콰도르": "EC",
    "페루": "PE", "볼리비아": "BO", "브라질": "BR", "파라과이": "PY",
    "우루과이": "UY", "아르헨티나": "AR", "칠레": "CL",
    # 오세아니아
    "호주": "AU", "뉴질랜드": "NZ", "파푸아뉴기니": "PG", "피지": "FJ",
    "솔로몬제도": "SB", "바누아투": "VU", "사모아": "WS", "통가": "TO",
    "키리바시": "KI", "투발루": "TV", "나우루": "NR", "팔라우": "PW",
    "마셜제도": "MH", "미크로네시아": "FM",
}


def flag_emoji_for_code(code: str) -> str:
    """유니코드 국기 이모지(regional indicator 조합)를 반환한다.

    Windows 브라우저/폰트 환경 상당수가 이 조합을 실제 국기 그림으로
    합치지 못하고 "TH"처럼 두 글자를 따로 보여준다. 화면에 그대로 쓰지
    말고 flag_icon_html_for_country()의 이미지 아이콘을 쓴다.
    """
    code = str(code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + (ord(ch) - ord("A"))) for ch in code)


def flag_emoji_for_country(country_name: str) -> str:
    code = COUNTRY_CODES.get(str(country_name or "").strip())
    return flag_emoji_for_code(code) if code else ""


def country_code_for(country_name: str) -> str:
    return COUNTRY_CODES.get(str(country_name or "").strip(), "")


def flag_icon_html_for_country(country_name: str) -> str:
    """유니코드 이모지 대신 flagcdn.com의 실제 국기 이미지 아이콘 <img> 태그를 만든다.

    OS/폰트에 상관없이 항상 그림으로 보이게 하기 위함(위 flag_emoji_for_*의
    한계 설명 참고).
    """
    code = country_code_for(country_name)
    if not code:
        return ""
    lower = code.lower()
    return (
        f'<img class="flag-ico" src="https://flagcdn.com/{lower}.svg" '
        f'width="18" height="13" alt="{code}" loading="lazy" '
        f'onerror="this.remove()">'
    )
