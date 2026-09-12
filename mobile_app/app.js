(() => {
  "use strict";

  const API_BASE = "";
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
  const COUNTRY_FLAGS = {
    "국내": "🇰🇷", "한국": "🇰🇷", "대한민국": "🇰🇷",
    "러시아": "🇷🇺", "리투아니아": "🇱🇹", "미국": "🇺🇸", "스페인": "🇪🇸",
    "싱가포르": "🇸🇬", "우크라이나": "🇺🇦", "카자흐스탄": "🇰🇿", "태국": "🇹🇭",
    "필리핀": "🇵🇭", "홍콩": "🇭🇰", "베트남": "🇻🇳", "일본": "🇯🇵", "중국": "🇨🇳",
    "대만": "🇹🇼", "말레이시아": "🇲🇾", "인도네시아": "🇮🇩", "몽골": "🇲🇳",
    "캐나다": "🇨🇦", "호주": "🇦🇺", "영국": "🇬🇧", "독일": "🇩🇪", "프랑스": "🇫🇷", "포르투갈": "🇵🇹",
    "이탈리아": "🇮🇹", "네덜란드": "🇳🇱", "아랍에미리트": "🇦🇪", "UAE": "🇦🇪",
    "사우디아라비아": "🇸🇦", "인도": "🇮🇳", "브라질": "🇧🇷", "멕시코": "🇲🇽",
    "우즈베키스탄": "🇺🇿", "튀르키예": "🇹🇷", "터키": "🇹🇷", "폴란드": "🇵🇱",
    "뉴질랜드": "🇳🇿", "캄보디아": "🇰🇭", "미얀마": "🇲🇲", "라오스": "🇱🇦",
  };
  function countryFlag(country) {
    return COUNTRY_FLAGS[String(country || "").trim()] || "";
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
  }
  function showMain() {
    el("login-screen").hidden = true;
    el("main-screen").hidden = false;
    setTimeout(maybeShowA2HSOverlay, 700);
  }

  // ---------- 홈 화면에 추가 온보딩 ----------
  const A2HS_SEEN_KEY = "nohtus_a2hs_seen";
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
    localStorage.setItem(A2HS_SEEN_KEY, "1");
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
    if (localStorage.getItem(A2HS_SEEN_KEY)) return;
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
    return `
      <div class="result-card" data-name="${escapeHtml(item.name)}" role="button" tabindex="0">
        <div class="result-thumb">📷</div>
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
        return `
          <div class="loc-row" data-location="${escapeHtml(row.location || "")}">
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
      if (value === item.code || value.startsWith(item.code + "-")) {
        matched.add(item.code);
      }
    }
    return matched;
  }

  function renderLocationMapSvg(layout) {
    const { canvas, items } = layout;
    const scale = 0.6;
    const width = Math.round(canvas.width * scale);
    const height = Math.round(canvas.height * scale);
    const rects = items
      .map((item) => {
        const cx = item.x + item.width / 2;
        const cy = item.y + item.height / 2;
        return `
          <g class="map-cell" data-code="${escapeHtml(item.code)}">
            <rect class="map-cell-rect" x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="6" />
            <text class="map-cell-label" x="${cx}" y="${cy}">${escapeHtml(item.label)}</text>
          </g>
        `;
      })
      .join("");
    return `
      <svg width="${width}" height="${height}" viewBox="0 0 ${canvas.width} ${canvas.height}" xmlns="http://www.w3.org/2000/svg">
        ${rects}
      </svg>
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
      row.addEventListener("click", () => highlightMapLocation(row.dataset.location, row, container));
    });
  }

  async function highlightMapLocation(loc, rowEl, container) {
    const holder = el("stock-map-holder");
    const wrap = holder && holder.querySelector(".map-wrap");
    if (!wrap) return;
    try {
      const layout = await ensureLocationMapLayout();
      const matched = matchingCodes(loc, layout.items);
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
        const multi = group.items.length > 1;
        const only = group.items[0];
        const datesHtml = multi
          ? ""
          : `<div class="export-group-dates">
              ${only.created_date ? `<span class="export-group-date">📅 접수 ${escapeHtml(only.created_date)}</span>` : ""}
              ${only.confirmed_date ? `<span class="export-group-date">✅ 출고 ${escapeHtml(only.confirmed_date)}</span>` : ""}
            </div>`;
        return `
          <div class="export-card">
            <div class="export-group-header">
              <span class="export-group-title">${flag ? `<span class="export-group-flag">${flag}</span>` : ""}${escapeHtml(group.country)} · ${group.items.length}건</span>
              ${datesHtml}
            </div>
            ${group.items.map((item) => renderExportCaseRow(item, multi)).join("")}
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
