(() => {
  "use strict";

  // 이 정적 파일이 실제로 서빙된 경로를 기준으로 API prefix를 계산한다.
  // http://host:8535/ 에서 직접 열든 https://nohtus-wms.online/mobile/ 로
  // 열든, "/api/..." 요청이 항상 같은 prefix 아래로 가도록 하기 위함
  // (하드코딩된 "/mobile"이 아니라 location에서 유도해야 로컬 개발 시
  // 프리픽스 없는 접속도 그대로 동작한다).
  const API_BASE = (() => {
    const path = window.location.pathname;
    const idx = path.indexOf("/index.html");
    if (idx !== -1) return path.slice(0, idx);
    return path.endsWith("/") ? path.slice(0, -1) : path;
  })();
  const TOKEN_KEY = "nohtus_mobile_token";

  const el = (id) => document.getElementById(id);
  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  const fmtQty = (n) => `${Number(n || 0).toLocaleString("ko-KR")}개`;
  const fmtWon = (n) => `${Number(n || 0).toLocaleString("ko-KR")}원`;
  const fmtNum = (n) => Number(n || 0).toLocaleString("ko-KR");
  const _MONTH_LABELS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
  // 국가명(한글 표기, 통용 별칭 포함) → ISO 3166-1 alpha-2 코드.
  // 국기는 이 코드로 flagcdn.com 이미지를 불러와 그린다(countryFlag 참고).
  // 새 나라가 필요하면 이미지를 따로 구할 필요 없이 코드 한 줄만 추가하면 된다.
  const COUNTRY_CODES = {
    "국내": "KR", "한국": "KR", "대한민국": "KR", "북한": "KP",
    // 아시아
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
    // 유럽
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
    // 아프리카
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
    // 아메리카
    "미국": "US", "캐나다": "CA", "멕시코": "MX", "과테말라": "GT",
    "벨리즈": "BZ", "온두라스": "HN", "엘살바도르": "SV", "니카라과": "NI",
    "코스타리카": "CR", "파나마": "PA", "쿠바": "CU", "자메이카": "JM",
    "아이티": "HT", "도미니카공화국": "DO", "바하마": "BS",
    "트리니다드토바고": "TT", "바베이도스": "BB", "콜롬비아": "CO",
    "베네수엘라": "VE", "가이아나": "GY", "수리남": "SR", "에콰도르": "EC",
    "페루": "PE", "볼리비아": "BO", "브라질": "BR", "파라과이": "PY",
    "우루과이": "UY", "아르헨티나": "AR", "칠레": "CL",
    // 오세아니아
    "호주": "AU", "뉴질랜드": "NZ", "파푸아뉴기니": "PG", "피지": "FJ",
    "솔로몬제도": "SB", "바누아투": "VU", "사모아": "WS", "통가": "TO",
    "키리바시": "KI", "투발루": "TV", "나우루": "NR", "팔라우": "PW",
    "마셜제도": "MH", "미크로네시아": "FM",
  };
  // 유니코드 국기 이모지(regional indicator 두 글자 조합)는 Windows의 여러
  // 브라우저/폰트 환경에서 그림으로 합쳐지지 않고 "TH"처럼 글자 두 개로
  // 따로 보인다. OS에 상관없이 항상 그림으로 보이도록 flagcdn.com의 실제
  // 국기 이미지를 쓴다.
  function countryFlag(country) {
    const code = COUNTRY_CODES[String(country || "").trim()];
    if (!code) return "";
    const lower = code.toLowerCase();
    return `<img class="flag-ico" src="https://flagcdn.com/${lower}.svg" width="18" height="13" alt="${code}" loading="lazy" onerror="this.remove()">`;
  }
  const debounce = (fn, ms) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  };

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }
  function setToken(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function api(path, options = {}) {
    const token = getToken();
    const headers = Object.assign({}, options.headers || {}, {
      Authorization: token ? `Bearer ${token}` : "",
    });
    if (options.body) headers["Content-Type"] = "application/json";
    const res = await fetch(API_BASE + path, { ...options, headers });
    if (res.status === 401) {
      setToken("");
      showLogin();
      throw new Error("unauthorized");
    }
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `요청 실패 (${res.status})`);
    }
    return res.json();
  }

  function showLogin() {
    el("login-screen").hidden = false;
    el("main-screen").hidden = true;
    setTimeout(maybeShowA2HSOverlay, 700);
  }
  function showMain() {
    el("login-screen").hidden = true;
    el("main-screen").hidden = false;
    setTimeout(maybeShowA2HSOverlay, 700);
  }

  // ---------- 홈 화면에 추가 온보딩 ----------
  let deferredInstallPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
  });

  function isStandaloneDisplay() {
    return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  }

  function a2hsContentHtml(kind) {
    if (kind === "ios") {
      return `
        <div class="a2hs-icon">📲</div>
        <div class="a2hs-title">홈 화면에 추가하고 앱처럼 쓰세요</div>
        <div class="a2hs-desc">아이콘 하나로 바로 열리고, 로그인도 계속 유지돼요.</div>
        <div class="a2hs-share-hint"><span class="a2hs-share-icon">⬆️</span>Safari 하단 공유 버튼을 눌러주세요</div>
        <div class="a2hs-desc">그다음 <b>'홈 화면에 추가'</b>를 선택하면 끝이에요.</div>
        <div class="a2hs-bounce">⬇️</div>
        <button class="primary-button" id="a2hs-dismiss">확인했어요</button>
      `;
    }
    if (kind === "android-installable") {
      return `
        <div class="a2hs-icon">📲</div>
        <div class="a2hs-title">홈 화면에 추가하고 앱처럼 쓰세요</div>
        <div class="a2hs-desc">아이콘 하나로 바로 열리고, 로그인도 계속 유지돼요.</div>
        <button class="primary-button" id="a2hs-install">홈 화면에 추가</button>
        <button class="a2hs-later" id="a2hs-dismiss">나중에 할게요</button>
      `;
    }
    return `
      <div class="a2hs-icon">📲</div>
      <div class="a2hs-title">홈 화면에 추가하고 앱처럼 쓰세요</div>
      <div class="a2hs-desc">브라우저 메뉴에서 <b>'홈 화면에 추가'</b> 또는 <b>'앱 설치'</b>를 선택해보세요.<br/>아이콘 하나로 바로 열리고, 로그인도 계속 유지돼요.</div>
      <button class="primary-button" id="a2hs-dismiss">확인했어요</button>
    `;
  }

  function dismissA2HSOverlay() {
    el("a2hs-overlay").hidden = true;
  }

  function showA2HSOverlay() {
    const ua = navigator.userAgent || "";
    const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    let kind = "generic";
    if (isIOS) kind = "ios";
    else if (deferredInstallPrompt) kind = "android-installable";

    el("a2hs-card").innerHTML = a2hsContentHtml(kind);
    el("a2hs-overlay").hidden = false;

    const dismissBtn = el("a2hs-dismiss");
    if (dismissBtn) dismissBtn.addEventListener("click", dismissA2HSOverlay);
    el("a2hs-overlay").querySelector(".a2hs-backdrop").addEventListener("click", dismissA2HSOverlay);

    const installBtn = el("a2hs-install");
    if (installBtn) {
      installBtn.addEventListener("click", async () => {
        if (deferredInstallPrompt) {
          deferredInstallPrompt.prompt();
          try {
            await deferredInstallPrompt.userChoice;
          } catch (e) {
            /* 사용자가 설치 프롬프트를 닫아도 온보딩은 그냥 종료한다 */
          }
          deferredInstallPrompt = null;
        }
        dismissA2HSOverlay();
      });
    }
  }

  function maybeShowA2HSOverlay() {
    if (isStandaloneDisplay()) return;
    showA2HSOverlay();
  }

  // ---------- 로그인 ----------
  el("login-submit").addEventListener("click", doLogin);
  el("login-password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });

  async function doLogin() {
    const username = el("login-username").value.trim();
    const password = el("login-password").value;
    const errorBox = el("login-error");
    errorBox.textContent = "";
    if (!username || !password) {
      errorBox.textContent = "아이디와 비밀번호를 입력하세요.";
      return;
    }
    try {
      const res = await fetch(API_BASE + "/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        errorBox.textContent = detail.detail || "로그인에 실패했습니다.";
        return;
      }
      const data = await res.json();
      setToken(data.token);
      el("login-password").value = "";
      showMain();
      initTabs();
      loadStock();
    } catch (err) {
      errorBox.textContent = "네트워크 오류가 발생했습니다.";
    }
  }

  el("logout-button").addEventListener("click", async () => {
    try {
      await api("/api/logout", { method: "POST" });
    } catch (e) {
      /* 토큰이 이미 무효해도 로그아웃은 계속 진행 */
    }
    setToken("");
    showLogin();
  });

  // ---------- 탭 전환 ----------
  let tabsInitialized = false;
  function initTabs() {
    if (tabsInitialized) return;
    tabsInitialized = true;
    document.querySelectorAll(".tab-button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.dataset.tab;
        el("stock-screen").hidden = tab !== "stock";
        el("expiry-screen").hidden = tab !== "expiry";
        el("purchase-screen").hidden = tab !== "purchase";
        el("export-screen").hidden = tab !== "export";
        if (tab === "expiry" && !expiryLoadedOnce) {
          expiryLoadedOnce = true;
          loadExpiry();
        }
        if (tab === "export" && !exportLoadedOnce) {
          exportLoadedOnce = true;
          loadExportCountries();
          loadExport();
        }
      });
    });
  }

  // ---------- 재고 검색 ----------
  function renderResultCard(item, opts = {}) {
    const badgeHtml = item.badge
      ? `${opts.hideBadgeLevel ? "" : `<span class="badge ${item.badge.level}">${escapeHtml(item.badge.label)}</span>`}<span class="badge-date">${escapeHtml(item.badge.date)}</span>`
      : "";
    const exportHtml = item.export_waiting
      ? `<span class="badge export">✈️ 수출대기중</span>`
      : "";
    const hasBadgeRow = badgeHtml || exportHtml;
    const thumbHtml = item.thumbnail
      ? `<img src="${item.thumbnail}" alt="" />`
      : "📷";
    return `
      <div class="result-card" data-name="${escapeHtml(item.name)}" role="button" tabindex="0">
        <div class="result-thumb">${thumbHtml}</div>
        <div class="result-info">
          <div class="result-name">${escapeHtml(item.name)}</div>
          <div class="result-company">${escapeHtml(item.summary || "재고 없음")}</div>
          ${hasBadgeRow ? `<div class="result-badges">${exportHtml}${badgeHtml}</div>` : ""}
        </div>
        <div class="result-qty">${fmtQty(item.total_qty)}</div>
      </div>
    `;
  }

  function bindResultCards(container, onOpen) {
    container.querySelectorAll(".result-card").forEach((card) => {
      card.addEventListener("click", () => onOpen(card.dataset.name));
    });
  }

  function emptyStateHtml(icon, title, sub) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">${icon}</div>
        <div class="empty-state-title">${escapeHtml(title)}</div>
        ${sub ? `<div class="empty-state-sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    `;
  }

  function skeletonCardsHtml(count) {
    const card = `
      <div class="skeleton-card">
        <div class="skeleton-block skeleton-thumb"></div>
        <div class="skeleton-lines">
          <div class="skeleton-block skeleton-line w60"></div>
          <div class="skeleton-block skeleton-line w40"></div>
        </div>
        <div class="skeleton-block skeleton-qty"></div>
      </div>
    `;
    return `<div class="result-list">${card.repeat(count)}</div>`;
  }

  function renderLocationCards(rows, emptyHtml, clickable) {
    if (!rows || rows.length === 0) {
      return emptyHtml;
    }
    const rowsHtml = rows
      .map((row) => {
        const metaParts = [row.company, row.lot ? `LOT ${row.lot}` : "", row.exp_date ? `유통기한 ${row.exp_date}` : ""]
          .filter(Boolean)
          .map(escapeHtml)
          .join(" · ");
        const exportBadge = row.export_waiting ? ` <span class="badge export">✈️ 수출대기중</span>` : "";
        const occupied = row.occupied_cells && row.occupied_cells.length ? row.occupied_cells : [row.location];
        return `
          <div class="loc-row" data-location="${escapeHtml(row.location || "")}" data-occupied="${escapeHtml(occupied.join(","))}">
            <div>
              <div class="loc-name">${escapeHtml(row.location || "-")}${exportBadge}</div>
              <div class="loc-meta">${metaParts}</div>
            </div>
            <div class="loc-qty">${fmtQty(row.qty)}</div>
          </div>
        `;
      })
      .join("");
    return `<div class="loc-list${clickable ? " map-linked" : ""}">${rowsHtml}</div>`;
  }

  function renderDetailHeader(detail) {
    const photo = detail.thumbnail
      ? `<img src="${detail.thumbnail}" alt="" />`
      : "";
    return `
      <div class="detail-header">
        <div class="detail-photo">${photo}</div>
        <div>
          <div class="detail-name">${escapeHtml(detail.name)}</div>
          <div class="detail-company">${escapeHtml(detail.summary || "재고 없음")}</div>
        </div>
        <div class="detail-total">${fmtQty(detail.total_qty)}</div>
      </div>
    `;
  }

  const stockSearchInput = el("stock-search");
  const stockResults = el("stock-results");
  const stockSectionLabel = el("stock-section-label");
  const stockListView = el("stock-list-view");
  const stockDetailView = el("stock-detail-view");
  const stockExcludeMaterial = el("stock-exclude-material");
  stockExcludeMaterial.addEventListener("change", loadStock);

  async function loadStock() {
    const term = stockSearchInput.value.trim();
    if (!term) {
      stockSectionLabel.hidden = true;
      stockResults.innerHTML = emptyStateHtml("📦", "제품을 검색해보세요", "제품명 또는 별칭으로 찾을 수 있어요");
      return;
    }
    stockSectionLabel.hidden = true;
    stockResults.innerHTML = skeletonCardsHtml(3);
    try {
      const params = new URLSearchParams({
        q: term,
        limit: "20",
        exclude_material: stockExcludeMaterial.checked ? "true" : "false",
      });
      const data = await api(`/api/products/search?${params.toString()}`);
      if (!data.results.length) {
        stockSectionLabel.hidden = true;
        stockResults.innerHTML = emptyStateHtml("🔍", "검색 결과가 없어요", "다른 검색어로 다시 시도해보세요");
        return;
      }
      stockSectionLabel.hidden = false;
      stockSectionLabel.textContent = `검색 결과 ${data.results.length}건`;
      stockResults.innerHTML = data.results.map((item) => renderResultCard(item)).join("");
      bindResultCards(stockResults, openStockDetail);
    } catch (err) {
      if (err.message !== "unauthorized") {
        stockSectionLabel.hidden = true;
        stockResults.innerHTML = emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
      }
    }
  }
  stockSearchInput.addEventListener("input", debounce(loadStock, 250));

  async function openStockDetail(name) {
    stockListView.hidden = true;
    stockDetailView.hidden = false;
    stockDetailView.innerHTML = `<button class="back-button">‹ 검색 결과</button>${skeletonCardsHtml(1)}`;
    stockDetailView.querySelector(".back-button").addEventListener("click", closeStockDetail);
    try {
      const detail = await api(`/api/products/${encodeURIComponent(name)}`);
      stockDetailView.innerHTML =
        `<button class="back-button">‹ 검색 결과</button>` +
        renderDetailHeader(detail) +
        renderLocationCards(detail.rows, emptyStateHtml("📦", "현재 재고가 없어요"), true) +
        `<div id="stock-map-holder"></div>`;
      stockDetailView.querySelector(".back-button").addEventListener("click", closeStockDetail);
      await loadLocationMapInto(el("stock-map-holder"));
      bindLocationRowClicks(stockDetailView);
    } catch (err) {
      if (err.message !== "unauthorized") {
        stockDetailView.innerHTML =
          `<button class="back-button">‹ 검색 결과</button>` +
          emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        stockDetailView.querySelector(".back-button").addEventListener("click", closeStockDetail);
      }
    }
  }
  function closeStockDetail() {
    stockDetailView.hidden = true;
    stockListView.hidden = false;
  }

  // ---------- 미니 로케이션맵 ----------
  let locationMapLayoutPromise = null;
  function ensureLocationMapLayout() {
    if (!locationMapLayoutPromise) {
      locationMapLayoutPromise = api("/api/location-map/layout").catch((err) => {
        locationMapLayoutPromise = null;
        throw err;
      });
    }
    return locationMapLayoutPromise;
  }

  function matchingCodes(loc, items) {
    const matched = new Set();
    const value = String(loc || "").trim();
    if (!value) return matched;
    for (const item of items) {
      if (item.kind !== "zone" && item.kind !== "location") continue;
      if (value === item.code || value.startsWith(item.code + "-")) {
        matched.add(item.code);
      }
    }
    return matched;
  }

  function mapFillFor(item, companyColors) {
    if (item.fill_type === "company") return companyColors[item.company] || "#ffffff";
    if (item.fill_type === "solid") return item.fill_color || "#ffffff";
    if (item.fill_type === "hatched") return "url(#map-hatch)";
    return "none";
  }

  function renderMapLabel(item, cx, cy) {
    const lines = String(item.label || "").split("\n");
    const lineHeight = 22;
    const startDy = -((lines.length - 1) * lineHeight) / 2;
    const tspans = lines
      .map((line, i) => `<tspan x="${cx}" dy="${i === 0 ? startDy : lineHeight}">${escapeHtml(line)}</tspan>`)
      .join("");
    return `<text class="map-cell-label" x="${cx}" y="${cy}">${tspans}</text>`;
  }

  function renderLocationMapSvg(layout) {
    const { canvas, items } = layout;
    const companyColors = layout.company_colors || {};
    const scale = 0.6;
    const width = Math.round(canvas.width * scale);
    const height = Math.round(canvas.height * scale);

    const shapesHtml = items
      .filter((item) => item.kind === "shape")
      .map((item) => {
        if (item.shape_type === "polyline") {
          const points = (item.path_points || [])
            .map(([px, py]) => `${item.x + px},${item.y + py}`)
            .join(" ");
          return `<polyline class="map-shape-line" points="${points}" stroke="${escapeHtml(item.stroke)}" />`;
        }
        if (item.shape_type === "door") {
          const r = Math.min(item.width, item.height);
          return `<path class="map-shape-door" d="M ${item.x} ${item.y} A ${r} ${r} 0 0 1 ${item.x + r} ${item.y + r}" stroke="${escapeHtml(item.stroke)}" />`;
        }
        // rounded_rect(기본값)
        const fill = mapFillFor(item, companyColors);
        return `<rect class="map-shape-rect" x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="10" fill="${fill}" stroke="${escapeHtml(item.stroke)}" />`;
      })
      .join("");

    const cellsHtml = items
      .filter((item) => item.kind === "zone" || item.kind === "location")
      .map((item) => {
        const cx = item.x + item.width / 2;
        const cy = item.y + item.height / 2;
        const fill = mapFillFor(item, companyColors);
        const dot = item.has_stock
          ? `<circle class="map-cell-dot" cx="${item.x + item.width - 10}" cy="${item.y + 10}" r="7" />`
          : "";
        return `
          <g class="map-cell" data-code="${escapeHtml(item.code)}">
            <rect class="map-cell-rect" x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="8" fill="${fill}" stroke="${escapeHtml(item.stroke)}" />
            ${renderMapLabel(item, cx, cy)}
            ${dot}
          </g>
        `;
      })
      .join("");

    return `
      <svg width="${width}" height="${height}" viewBox="0 0 ${canvas.width} ${canvas.height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="map-hatch" width="10" height="10" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="10" stroke="#c2c2c2" stroke-width="4" />
          </pattern>
        </defs>
        ${shapesHtml}
        ${cellsHtml}
      </svg>
    `;
  }

  function renderMapLegend(layout) {
    const companyColors = layout.company_colors || {};
    const usedCompanies = new Set(
      (layout.items || [])
        .filter((item) => (item.kind === "zone" || item.kind === "location") && item.fill_type === "company")
        .map((item) => item.company)
    );
    const skip = new Set(["특수", "기타"]);
    const entries = Object.keys(companyColors).filter((name) => usedCompanies.has(name) && !skip.has(name));
    if (!entries.length) return "";
    return `
      <div class="map-company-legend">
        ${entries
          .map(
            (name) =>
              `<span class="map-company-chip"><span class="map-company-swatch" style="background:${escapeHtml(companyColors[name])}"></span>${escapeHtml(name)}</span>`
          )
          .join("")}
      </div>
    `;
  }

  async function loadLocationMapInto(holder) {
    if (!holder) return;
    holder.innerHTML = `<div class="map-section"><div class="section-label" style="margin-top:0">로케이션맵</div><div class="spinner-row" style="padding:24px 0;color:var(--text-muted);font-size:13px;text-align:center;">불러오는 중…</div></div>`;
    try {
      const layout = await ensureLocationMapLayout();
      if (!layout.items || !layout.items.length) {
        holder.innerHTML = "";
        return;
      }
      holder.innerHTML = `
        <div class="map-section">
          <div class="section-label" style="margin-top:0">로케이션맵</div>
          ${renderMapLegend(layout)}
          <div class="map-hint">위의 위치를 눌러보세요</div>
          <div class="map-wrap" id="stock-map-wrap">${renderLocationMapSvg(layout)}</div>
          <div class="map-legend"><span class="map-legend-swatch"></span>선택한 위치</div>
        </div>
      `;
    } catch (err) {
      holder.innerHTML = "";
    }
  }

  function bindLocationRowClicks(container) {
    container.querySelectorAll(".loc-row[data-location]").forEach((row) => {
      const occupied = (row.dataset.occupied || row.dataset.location || "").split(",").filter(Boolean);
      row.addEventListener("click", () => highlightMapLocation(occupied, row, container));
    });
  }

  async function highlightMapLocation(locs, rowEl, container) {
    const holder = el("stock-map-holder");
    const wrap = holder && holder.querySelector(".map-wrap");
    if (!wrap) return;
    try {
      const layout = await ensureLocationMapLayout();
      const matched = new Set();
      (Array.isArray(locs) ? locs : [locs]).forEach((loc) => {
        matchingCodes(loc, layout.items).forEach((code) => matched.add(code));
      });
      wrap.querySelectorAll(".map-cell").forEach((cell) => {
        cell.classList.toggle("lit", matched.has(cell.dataset.code));
      });
      if (container) {
        container.querySelectorAll(".loc-row.active").forEach((r) => r.classList.remove("active"));
      }
      if (rowEl) rowEl.classList.add("active");

      holder.scrollIntoView({ behavior: "smooth", block: "nearest" });
      const litRect = wrap.querySelector(".map-cell.lit rect");
      if (litRect) {
        const svgEl = wrap.querySelector("svg");
        const scaleX = svgEl.clientWidth / svgEl.viewBox.baseVal.width;
        const targetX = Number(litRect.getAttribute("x")) * scaleX;
        wrap.scrollTo({ left: Math.max(0, targetX - wrap.clientWidth / 2), behavior: "smooth" });
      }
    } catch (err) {
      /* 맵을 못 불러왔으면 조용히 무시 — 위치 목록 자체는 이미 보이고 있다 */
    }
  }

  // ---------- 임박재고 ----------
  let expiryLoadedOnce = false;
  const expiryResults = el("expiry-results");
  const expiryListView = el("expiry-list-view");
  const expiryDetailView = el("expiry-detail-view");
  const expiryExcludeBidata = el("expiry-exclude-bidata");
  const expiryPeriodSelect = el("expiry-period");
  const expiryWarehouseSelect = el("expiry-warehouse");
  let expiryPeriod = expiryPeriodSelect.value;
  let expiryWarehouse = expiryWarehouseSelect.value;

  expiryPeriodSelect.addEventListener("change", () => {
    expiryPeriod = expiryPeriodSelect.value;
    loadExpiry();
  });
  expiryWarehouseSelect.addEventListener("change", () => {
    expiryWarehouse = expiryWarehouseSelect.value;
    loadExpiry();
  });
  expiryExcludeBidata.addEventListener("change", loadExpiry);

  function groupResultsByExpiryLevel(results) {
    const order = ["red", "yellow", "blue"];
    const buckets = { red: [], yellow: [], blue: [] };
    for (const item of results) {
      const level = item.badge && item.badge.level;
      if (buckets[level]) buckets[level].push(item);
    }
    return order.map((level) => ({ level, label: buckets[level][0] ? buckets[level][0].badge.label : "", items: buckets[level] })).filter((g) => g.items.length);
  }

  function renderExpiryGroups(results) {
    const groups = groupResultsByExpiryLevel(results);
    return groups
      .map(
        (group) => `
          <div class="expiry-group">
            <div class="expiry-group-header">
              <span class="badge ${group.level}">${escapeHtml(group.label)}</span>
              <span class="expiry-group-count">${group.items.length}건</span>
            </div>
            <div class="result-list">${group.items.map((item) => renderResultCard(item, { hideBadgeLevel: true })).join("")}</div>
          </div>
        `
      )
      .join("");
  }

  async function loadExpiry() {
    expiryResults.innerHTML = skeletonCardsHtml(3);
    const params = new URLSearchParams({
      period: expiryPeriod,
      exclude_bidata: expiryExcludeBidata.checked ? "true" : "false",
      warehouse: expiryWarehouse,
      limit: "300",
    });
    try {
      const data = await api(`/api/expiry?${params.toString()}`);
      if (!data.results.length) {
        expiryResults.innerHTML = emptyStateHtml("⏰", "조건에 맞는 임박재고가 없어요", "기간이나 창고를 바꿔보세요");
        return;
      }
      expiryResults.innerHTML = renderExpiryGroups(data.results);
      bindResultCards(expiryResults, openExpiryDetail);
    } catch (err) {
      if (err.message !== "unauthorized") {
        expiryResults.innerHTML = emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
      }
    }
  }

  async function openExpiryDetail(name) {
    expiryListView.hidden = true;
    expiryDetailView.hidden = false;
    expiryDetailView.innerHTML = `<button class="back-button">‹ 목록</button>${skeletonCardsHtml(1)}`;
    expiryDetailView.querySelector(".back-button").addEventListener("click", closeExpiryDetail);
    try {
      const params = new URLSearchParams({
        period: expiryPeriod,
        exclude_bidata: expiryExcludeBidata.checked ? "true" : "false",
        warehouse: expiryWarehouse,
      });
      const detail = await api(`/api/expiry/${encodeURIComponent(name)}?${params.toString()}`);
      expiryDetailView.innerHTML =
        `<button class="back-button">‹ 목록</button>` +
        renderDetailHeader(detail) +
        renderLocationCards(detail.rows, emptyStateHtml("⏰", "조건에 맞는 임박재고가 없어요"));
      expiryDetailView.querySelector(".back-button").addEventListener("click", closeExpiryDetail);
    } catch (err) {
      if (err.message !== "unauthorized") {
        expiryDetailView.innerHTML =
          `<button class="back-button">‹ 목록</button>` +
          emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        expiryDetailView.querySelector(".back-button").addEventListener("click", closeExpiryDetail);
      }
    }
  }
  function closeExpiryDetail() {
    expiryDetailView.hidden = true;
    expiryListView.hidden = false;
  }

  // ---------- 매입가 조회 ----------
  const purchaseSearchInput = el("purchase-search");
  const purchaseResults = el("purchase-results");
  const purchaseSectionLabel = el("purchase-section-label");
  const purchaseListView = el("purchase-list-view");
  const purchaseDetailView = el("purchase-detail-view");
  let purchasePeriod = "1y";

  el("purchase-period").querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      el("purchase-period").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      purchasePeriod = btn.dataset.period;
      loadPurchase();
    });
  });
  purchaseSearchInput.addEventListener("input", debounce(loadPurchase, 250));

  function renderPurchaseCard(item) {
    return `
      <div class="result-card" data-name="${escapeHtml(item.name)}" role="button" tabindex="0">
        <div class="result-thumb">💰</div>
        <div class="result-info">
          <div class="result-name">${escapeHtml(item.name)}</div>
          <div class="result-company">${item.count}건 · 최근 매입 ${escapeHtml(item.latest_date || "-")}</div>
        </div>
        <div class="result-qty">${fmtWon(item.latest_price)}</div>
      </div>
    `;
  }

  function renderPurchaseRecordCards(rows) {
    if (!rows || rows.length === 0) {
      return emptyStateHtml("💰", "매입 이력이 없어요", "기간을 바꿔보세요");
    }
    const rowsHtml = rows
      .map((row) => {
        const metaParts = [
          row.business_name,
          row.purchase_date,
          row.specification ? `규격 ${row.specification}` : "",
          `수량 ${fmtNum(row.quantity)}`,
          row.note || "",
        ].filter(Boolean).map(escapeHtml).join(" · ");
        return `
          <div class="loc-row">
            <div>
              <div class="loc-name">${escapeHtml(row.supplier_name || "-")}</div>
              <div class="loc-meta">${metaParts}</div>
            </div>
            <div class="loc-qty">${fmtWon(row.unit_price)}</div>
          </div>
        `;
      })
      .join("");
    return `<div class="loc-list">${rowsHtml}</div>`;
  }

  async function loadPurchase() {
    const term = purchaseSearchInput.value.trim();
    if (!term) {
      purchaseSectionLabel.hidden = true;
      purchaseResults.innerHTML = emptyStateHtml("💰", "제품을 검색해보세요", "제품명 또는 별칭으로 매입 이력을 찾을 수 있어요");
      return;
    }
    purchaseSectionLabel.hidden = true;
    purchaseResults.innerHTML = skeletonCardsHtml(3);
    try {
      const params = new URLSearchParams({ q: term, period: purchasePeriod, limit: "20" });
      const data = await api(`/api/purchase/search?${params.toString()}`);
      if (!data.results.length) {
        purchaseResults.innerHTML = emptyStateHtml("🔍", "검색 결과가 없어요", "다른 검색어나 기간으로 다시 시도해보세요");
        return;
      }
      purchaseSectionLabel.hidden = false;
      purchaseSectionLabel.textContent = `검색 결과 ${data.results.length}건`;
      purchaseResults.innerHTML = data.results.map((item) => renderPurchaseCard(item)).join("");
      purchaseResults.querySelectorAll(".result-card").forEach((card) => {
        card.addEventListener("click", () => openPurchaseDetail(card.dataset.name));
      });
    } catch (err) {
      if (err.message !== "unauthorized") {
        purchaseSectionLabel.hidden = true;
        purchaseResults.innerHTML = emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
      }
    }
  }

  async function openPurchaseDetail(name) {
    purchaseListView.hidden = true;
    purchaseDetailView.hidden = false;
    purchaseDetailView.innerHTML = `<button class="back-button">‹ 검색 결과</button>${skeletonCardsHtml(1)}`;
    purchaseDetailView.querySelector(".back-button").addEventListener("click", closePurchaseDetail);
    try {
      const params = new URLSearchParams({ period: purchasePeriod });
      const detail = await api(`/api/purchase/${encodeURIComponent(name)}?${params.toString()}`);
      purchaseDetailView.innerHTML =
        `<button class="back-button">‹ 검색 결과</button>` +
        `<div class="section-label" style="margin-top:0">${escapeHtml(detail.name)} · ${detail.rows.length}건</div>` +
        renderPurchaseRecordCards(detail.rows);
      purchaseDetailView.querySelector(".back-button").addEventListener("click", closePurchaseDetail);
    } catch (err) {
      if (err.message !== "unauthorized") {
        purchaseDetailView.innerHTML =
          `<button class="back-button">‹ 검색 결과</button>` +
          emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        purchaseDetailView.querySelector(".back-button").addEventListener("click", closePurchaseDetail);
      }
    }
  }
  function closePurchaseDetail() {
    purchaseDetailView.hidden = true;
    purchaseListView.hidden = false;
  }

  // ---------- 수출 현황 ----------
  let exportLoadedOnce = false;
  const exportFiltersView = el("export-filters-view");
  const exportYearView = el("export-year-view");
  const exportDetailView = el("export-detail-view");
  const exportInProgressResults = el("export-in-progress-results");
  const exportCompletedResults = el("export-completed-results");
  const exportCountryFilter = el("export-country-filter");
  const exportTransportFilter = el("export-transport-filter");
  let exportCountry = "";
  let exportTransport = "";
  let exportPeriod = "recent";
  let exportDetailReturnTo = "filters"; // "filters" | "year"
  let exportDetailReturnYear = null;

  exportCountryFilter.addEventListener("change", () => {
    exportCountry = exportCountryFilter.value;
    loadExport();
  });
  exportTransportFilter.addEventListener("change", () => {
    exportTransport = exportTransportFilter.value;
    loadExport();
  });
  el("export-period").querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      el("export-period").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      exportPeriod = btn.dataset.period;
      loadExport();
    });
  });

  async function loadExportCountries() {
    try {
      const data = await api("/api/export/countries");
      const options = data.countries
        .map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`)
        .join("");
      exportCountryFilter.innerHTML = `<option value="">국가 전체</option>${options}`;
      exportCountryFilter.value = exportCountry;
    } catch (err) {
      /* 국가 목록을 못 불러와도 대시보드는 그대로 보여준다 */
    }
  }

  function groupByCountry(cases) {
    const order = [];
    const map = new Map();
    for (const item of cases) {
      const key = item.country || "국가 미지정";
      if (!map.has(key)) {
        map.set(key, []);
        order.push(key);
      }
      map.get(key).push(item);
    }
    return order.map((country) => ({ country, items: map.get(country) }));
  }

  function renderExportCaseRow(item, showOwnDates) {
    const salesClass = item.sales_status === "등록완료" ? "green" : item.sales_status === "등록중" ? "yellow" : "gray";
    const noteHtml = item.note ? `<div class="export-note">${escapeHtml(item.note)}</div>` : "";
    const title = [item.buyer, item.transport_mode ? (item.transport_icon ? item.transport_icon + " " : "") + item.transport_mode : ""]
      .filter(Boolean)
      .join(" · ") || "-";
    const datesHtml =
      showOwnDates && (item.created_date || item.confirmed_date)
        ? `<div class="export-case-dates">
            ${item.created_date ? `<span class="export-case-date">📅 접수 ${escapeHtml(item.created_date)}</span>` : ""}
            ${item.confirmed_date ? `<span class="export-case-date">✅ 출고 ${escapeHtml(item.confirmed_date)}</span>` : ""}
          </div>`
        : "";
    return `
      <div class="export-case-row" data-id="${item.id}" role="button" tabindex="0">
        <div class="export-card-top">
          <div class="export-buyer">${escapeHtml(title)}</div>
          <span class="stage-badge" style="background:${escapeHtml(item.stage_bg)};color:${escapeHtml(item.stage_fg)}">${escapeHtml(item.stage)}</span>
        </div>
        ${datesHtml}
        <div class="export-progress-row">
          <div class="export-progress-track"><div class="export-progress-fill" style="width:${item.progress_percent}%"></div></div>
          <span class="export-progress-label">${item.progress_percent}%</span>
        </div>
        <div class="export-bottom-row">
          <span class="export-products">${escapeHtml(item.products_summary)}</span>
          <span class="badge ${salesClass}">매출 ${escapeHtml(item.sales_status)}</span>
        </div>
        ${noteHtml}
      </div>
    `;
  }

  function renderGroupedCases(cases) {
    const groups = groupByCountry(cases);
    return groups
      .map((group) => {
        const flag = countryFlag(group.country);
        return `
          <div class="export-card">
            <div class="export-group-header">
              <span class="export-group-title">${flag ? `<span class="export-group-flag">${flag}</span>` : ""}${escapeHtml(group.country)} · ${group.items.length}건</span>
            </div>
            ${group.items.map((item) => renderExportCaseRow(item, true)).join("")}
          </div>
        `;
      })
      .join("");
  }

  function bindExportCaseRows(container, returnTo, returnYear) {
    container.querySelectorAll(".export-case-row").forEach((row) => {
      row.addEventListener("click", () => openExportDetail(row.dataset.id, returnTo, returnYear));
    });
  }

  function renderYearCard(yearInfo) {
    return `
      <div class="year-card" data-year="${yearInfo.year}" role="button" tabindex="0">
        <div>
          <div class="year-card-label">${yearInfo.year}년</div>
          <div class="year-card-count">${yearInfo.count}건</div>
        </div>
        <span class="year-card-arrow">›</span>
      </div>
    `;
  }

  function renderMonthCard(monthInfo) {
    return `
      <div class="year-card" data-year="${monthInfo.year}" data-month="${monthInfo.month}" role="button" tabindex="0">
        <div>
          <div class="year-card-label">${monthInfo.year}년 ${escapeHtml(monthInfo.label)}</div>
          <div class="year-card-count">${monthInfo.count}건</div>
        </div>
        <span class="year-card-arrow">›</span>
      </div>
    `;
  }

  async function loadExport() {
    exportInProgressResults.innerHTML = skeletonCardsHtml(2);
    exportCompletedResults.innerHTML = "";
    try {
      const params = new URLSearchParams();
      if (exportCountry) params.set("country", exportCountry);
      if (exportTransport) params.set("transport", exportTransport);
      params.set("period", exportPeriod);
      const data = await api(`/api/export/dashboard?${params.toString()}`);

      exportInProgressResults.innerHTML = data.in_progress.length
        ? renderGroupedCases(data.in_progress)
        : emptyStateHtml("✈️", "진행 중인 수출 건이 없어요");
      bindExportCaseRows(exportInProgressResults, "filters", null);

      if (data.completed_mode === "years") {
        exportCompletedResults.innerHTML = data.completed_years.length
          ? data.completed_years.map((y) => renderYearCard(y)).join("")
          : emptyStateHtml("📦", "완료된 수출 건이 없어요");
        exportCompletedResults.querySelectorAll(".year-card").forEach((card) => {
          card.addEventListener("click", () => openExportDrill({ year: card.dataset.year }));
        });
      } else if (data.completed_mode === "months") {
        exportCompletedResults.innerHTML = data.completed_months.length
          ? data.completed_months.map((m) => renderMonthCard(m)).join("")
          : emptyStateHtml("📦", "완료된 수출 건이 없어요");
        exportCompletedResults.querySelectorAll(".year-card").forEach((card) => {
          card.addEventListener("click", () => openExportDrill({ year: card.dataset.year, month: card.dataset.month }));
        });
      } else {
        exportCompletedResults.innerHTML = data.completed_cases.length
          ? renderGroupedCases(data.completed_cases)
          : emptyStateHtml("📦", "최근 2주 내 완료된 건이 없어요");
        bindExportCaseRows(exportCompletedResults, "filters", null);
      }
    } catch (err) {
      if (err.message !== "unauthorized") {
        exportInProgressResults.innerHTML = emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        exportCompletedResults.innerHTML = "";
      }
    }
  }

  async function openExportDrill({ year, month }) {
    exportFiltersView.hidden = true;
    exportYearView.hidden = false;
    exportYearView.innerHTML = `<button class="back-button">‹ 수출 현황</button>${skeletonCardsHtml(2)}`;
    exportYearView.querySelector(".back-button").addEventListener("click", closeExportYear);
    const titleText = month ? `${year}년 ${_MONTH_LABELS[Number(month) - 1]}` : `${year}년`;
    const returnKey = month ? `${year}-${month}` : `${year}`;
    try {
      const params = new URLSearchParams();
      if (exportCountry) params.set("country", exportCountry);
      if (exportTransport) params.set("transport", exportTransport);
      const path = month
        ? `/api/export/dashboard/month/${encodeURIComponent(year)}/${encodeURIComponent(month)}`
        : `/api/export/dashboard/year/${encodeURIComponent(year)}`;
      const data = await api(`${path}?${params.toString()}`);
      exportYearView.innerHTML =
        `<button class="back-button">‹ 수출 현황</button>` +
        `<div class="section-label" style="margin-top:0">${escapeHtml(titleText)} · ${data.cases.length}건</div>` +
        (data.cases.length ? renderGroupedCases(data.cases) : emptyStateHtml("📦", "해당 기간에 완료된 건이 없어요"));
      exportYearView.querySelector(".back-button").addEventListener("click", closeExportYear);
      bindExportCaseRows(exportYearView, "year", returnKey);
    } catch (err) {
      if (err.message !== "unauthorized") {
        exportYearView.innerHTML =
          `<button class="back-button">‹ 수출 현황</button>` +
          emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        exportYearView.querySelector(".back-button").addEventListener("click", closeExportYear);
      }
    }
  }
  function closeExportYear() {
    exportYearView.hidden = true;
    exportFiltersView.hidden = false;
  }

  function renderOrderItemCards(items) {
    if (!items || items.length === 0) {
      return emptyStateHtml("📦", "주문목록이 없어요");
    }
    const statusClass = { "입고완료": "green", "부분입고": "yellow", "미입고": "gray" };
    const rowsHtml = items
      .map((item) => `
        <div class="loc-row">
          <div>
            <div class="loc-name">${item.no}. ${escapeHtml(item.product_name || "-")}</div>
            <div class="loc-meta">수량 ${fmtNum(item.quantity)}${item.unit ? escapeHtml(item.unit) : ""}</div>
          </div>
          <span class="badge ${statusClass[item.intake_status] || "gray"}">${escapeHtml(item.intake_status)}</span>
        </div>
      `)
      .join("");
    return `<div class="loc-list">${rowsHtml}</div>`;
  }

  async function openExportDetail(caseId, returnTo, returnYear) {
    exportDetailReturnTo = returnTo || "filters";
    exportDetailReturnYear = returnYear || null;
    exportFiltersView.hidden = true;
    exportYearView.hidden = true;
    exportDetailView.hidden = false;
    exportDetailView.innerHTML = `<button class="back-button">‹ 뒤로</button>${skeletonCardsHtml(2)}`;
    exportDetailView.querySelector(".back-button").addEventListener("click", closeExportDetail);
    try {
      const data = await api(`/api/export/cases/${encodeURIComponent(caseId)}/items`);
      exportDetailView.innerHTML =
        `<button class="back-button">‹ 뒤로</button>` +
        `<div class="section-label" style="margin-top:0">주문목록</div>` +
        renderOrderItemCards(data.items);
      exportDetailView.querySelector(".back-button").addEventListener("click", closeExportDetail);
    } catch (err) {
      if (err.message !== "unauthorized") {
        exportDetailView.innerHTML =
          `<button class="back-button">‹ 뒤로</button>` +
          emptyStateHtml("⚠️", "불러오지 못했어요", "네트워크 상태를 확인하고 다시 시도해주세요");
        exportDetailView.querySelector(".back-button").addEventListener("click", closeExportDetail);
      }
    }
  }
  function closeExportDetail() {
    exportDetailView.hidden = true;
    if (exportDetailReturnTo === "year" && exportDetailReturnYear) {
      exportYearView.hidden = false;
    } else {
      exportFiltersView.hidden = false;
    }
  }

  // ---------- 부팅 ----------
  async function boot() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
    const token = getToken();
    if (!token) {
      showLogin();
      return;
    }
    try {
      await api("/api/me");
      showMain();
      initTabs();
    } catch (err) {
      showLogin();
    }
  }
  boot();
})();
