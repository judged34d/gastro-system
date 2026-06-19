/**
 * Ampel (leichtgewichtig – blockiert keine Seiten-Navigation):
 * - Grün: API + Frontend OK + Tunnel (Remote) OK
 * - Gelb: API + Frontend OK, kein Tunnel
 * - Rot: API oder Frontend nicht erreichbar
 */
(function () {
  const REMOTE_API = "https://api.mpbin.de";
  const STATUS_CACHE_KEY = "gastro_status_v1";
  const POLL_MS = 30000;
  const FAST_TIMEOUT_MS = 1200;
  const REMOTE_TIMEOUT_MS = 2500;
  const MIN_CHECK_GAP_MS = 4000;
  const DECKEL_PAGE_RE = /\/(tabs_overview|tab_select|tab_settle)\.html/i;

  function isDeckelPage() {
    return DECKEL_PAGE_RE.test(window.location.pathname || "");
  }

  let lastTouchEnd = 0;
  let checkGen = 0;
  let checkAbort = null;
  let lastCheckAt = 0;
  let remoteCheckTimer = null;

  function enforceViewportZoomPolicy() {
    const vp = document.querySelector('meta[name="viewport"]');
    if (!vp) return;
    const content = vp.getAttribute("content") || "";
    if (/user-scalable\s*=\s*no/i.test(content)) return;
    vp.setAttribute(
      "content",
      "width=device-width, initial-scale=1.0, user-scalable=yes, maximum-scale=5.0"
    );
  }

  function isInteractiveTouchTarget(el) {
    if (!el || !el.closest) return false;
    return !!el.closest(
      "button, a, input, select, textarea, label, [onclick], .back-btn, .tab-tile, .header-btn, .table-btn, .product, .category, .open-btn"
    );
  }

  function preventDoubleTapZoom() {
    document.addEventListener(
      "touchend",
      function (ev) {
        if (
          (ev.changedTouches && ev.changedTouches.length !== 1) ||
          (ev.touches && ev.touches.length > 0)
        ) {
          return;
        }
        if (isInteractiveTouchTarget(ev.target)) {
          lastTouchEnd = Date.now();
          return;
        }
        const now = Date.now();
        if (now - lastTouchEnd < 320) {
          ev.preventDefault();
        }
        lastTouchEnd = now;
      },
      { passive: false }
    );
  }

  function el() {
    let bar = document.getElementById("gastro-status");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "gastro-status";
      bar.className = "gastro-status";
      bar.setAttribute("aria-live", "polite");
      document.body.appendChild(bar);
    }
    return bar;
  }

  function readCache() {
    try {
      const raw = sessionStorage.getItem(STATUS_CACHE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function writeCache(level, label, title) {
    try {
      sessionStorage.setItem(
        STATUS_CACHE_KEY,
        JSON.stringify({ level: level, label: label, title: title, ts: Date.now() })
      );
    } catch (_) {}
  }

  function applyStatus(level, label, title) {
    const bar = el();
    bar.className = "gastro-status " + level;
    bar.textContent = label;
    bar.title = title || label;
    writeCache(level, label, title || label);
  }

  function applyCachedStatus() {
    const c = readCache();
    if (c && c.level && c.label) {
      applyStatus(c.level, c.label, c.title);
      return true;
    }
    applyStatus("yellow", "…", "Verbindung wird geprüft");
    return false;
  }

  function apiBase() {
    if (typeof window.getGastroApiBase === "function") {
      return window.getGastroApiBase().replace(/\/$/, "");
    }
    return "";
  }

  async function fetchOk(url, timeoutMs, parentSignal) {
    const ctrl = new AbortController();
    const timer = setTimeout(function () {
      ctrl.abort();
    }, timeoutMs);
    if (parentSignal) {
      parentSignal.addEventListener("abort", function () {
        ctrl.abort();
      });
    }
    try {
      const r = await fetch(url, {
        method: "GET",
        cache: "no-store",
        credentials: "omit",
        signal: ctrl.signal,
      });
      return r.ok;
    } catch (_) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  async function checkRemoteTunnel(gen) {
    const remoteOk = await fetchOk(REMOTE_API + "/health", REMOTE_TIMEOUT_MS, null);
    if (gen !== checkGen) return;
    const c = readCache();
    if (!c) return;
    if (remoteOk && (c.level === "yellow" || c.level === "green")) {
      applyStatus(
        "green",
        "Online",
        "Backend, Frontend und Tunnel erreichbar"
      );
    } else if (!remoteOk && c.level === "green") {
      applyStatus(
        "yellow",
        "Nur LAN",
        "Nur lokal (LAN) – kein Tunnel zur API"
      );
    }
  }

  async function check(force) {
    const now = Date.now();
    if (!force && now - lastCheckAt < MIN_CHECK_GAP_MS) {
      return;
    }
    lastCheckAt = now;

    const gen = ++checkGen;
    if (checkAbort) {
      checkAbort.abort();
    }
    checkAbort = new AbortController();
    const signal = checkAbort.signal;

    if (remoteCheckTimer) {
      clearTimeout(remoteCheckTimer);
      remoteCheckTimer = null;
    }

    const base = apiBase();
    const originHealth = window.location.origin + "/health.json";
    const checks = [fetchOk(originHealth, FAST_TIMEOUT_MS, signal)];
    if (base) {
      checks.push(fetchOk(base + "/health", FAST_TIMEOUT_MS, signal));
    }

    const results = await Promise.all(checks);
    if (gen !== checkGen) return;

    const frontendOk = results[0];
    const apiOk = base ? results[1] : true;

    if (apiOk && frontendOk) {
      applyStatus(
        "yellow",
        "Bereit",
        "System erreichbar – Tunnel wird geprüft"
      );
      if (!isDeckelPage()) {
        remoteCheckTimer = setTimeout(function () {
          checkRemoteTunnel(gen);
        }, 150);
      }
    } else {
      applyStatus(
        "red",
        "Offline",
        "System nicht voll nutzbar"
      );
    }
  }

  function scheduleCheck(force) {
    var delay = isDeckelPage() ? 4500 : 80;
    setTimeout(function () {
      check(force);
    }, delay);
  }

  applyCachedStatus();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      enforceViewportZoomPolicy();
      preventDoubleTapZoom();
      scheduleCheck(false);
    });
  } else {
    enforceViewportZoomPolicy();
    preventDoubleTapZoom();
    scheduleCheck(false);
  }

  setInterval(function () {
    check(false);
  }, POLL_MS);

  window.addEventListener("pageshow", function (ev) {
    applyCachedStatus();
    if (ev.persisted) {
      scheduleCheck(true);
    }
  });
})();

(function initGastroTapFeedback() {
  const TAP_SELECTOR =
    "button:not(:disabled), .product, .category, .header-btn, .minus, .tableBox, .terminal-big-btn, .tab-tile";

  let pressedEl = null;

  function isTappable(el) {
    if (!el || !el.matches) return false;
    if (!el.matches(TAP_SELECTOR)) return false;
    if (el.closest("#gastro-status")) return false;
    if (el.disabled) return false;
    return true;
  }

  function isDangerTap(el) {
    return !!el.matches(
      ".minus, .selector .minus-btn, .buttons button:last-child, .product-tile-remove, [data-tap-tone='danger']"
    );
  }

  function clearPressed() {
    if (pressedEl) {
      pressedEl.classList.remove("gastro-tap-pressed");
      pressedEl = null;
    }
  }

  function playFlash(el) {
    const danger = isDangerTap(el);
    el.classList.remove("gastro-tap-flash", "gastro-tap-flash-danger");
    void el.offsetWidth;
    el.classList.add(danger ? "gastro-tap-flash-danger" : "gastro-tap-flash");
    el.addEventListener(
      "animationend",
      function onEnd(ev) {
        if (ev.animationName.indexOf("gastro-tap-flash") === -1) return;
        el.classList.remove("gastro-tap-flash", "gastro-tap-flash-danger");
        el.removeEventListener("animationend", onEnd);
      },
      { once: true }
    );
  }

  function onPointerDown(ev) {
    if (ev.button > 0) return;
    const el = ev.target.closest(TAP_SELECTOR);
    if (!isTappable(el)) return;
    clearPressed();
    pressedEl = el;
    el.classList.add("gastro-tap-pressed");
  }

  function onPointerUp(ev) {
    if (ev.button > 0) return;
    const el = pressedEl || ev.target.closest(TAP_SELECTOR);
    if (!isTappable(el)) {
      clearPressed();
      return;
    }
    el.classList.remove("gastro-tap-pressed");
    pressedEl = null;
    playFlash(el);
  }

  function bind() {
    document.addEventListener("pointerdown", onPointerDown, { passive: true });
    document.addEventListener("pointerup", onPointerUp, { passive: true });
    document.addEventListener("pointercancel", onPointerUp, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();

(function initGastroDemoBanner() {
  const POLL_MS = 30000;
  const CACHE_KEY = "gastro_demo_banner_v1";

  function apiBase() {
    if (typeof window.getGastroApiBase === "function") {
      return window.getGastroApiBase().replace(/\/$/, "");
    }
    return "";
  }

  function bannerEl() {
    let bar = document.getElementById("gastro-demo-banner");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "gastro-demo-banner";
      bar.className = "gastro-demo-banner";
      bar.setAttribute("role", "status");
      bar.setAttribute("aria-live", "polite");
      document.body.insertBefore(bar, document.body.firstChild);
    }
    return bar;
  }

  function applyDemoState(isDemo, eventName) {
    const bar = bannerEl();
    if (isDemo) {
      document.body.classList.add("gastro-demo-active");
      bar.style.display = "flex";
      bar.textContent =
        "Demo-Modus – " +
        (eventName || "keine echten Umsätze") +
        " · PINs: Bedienung 1111/3333, Theke 2222";
      try {
        sessionStorage.setItem(
          CACHE_KEY,
          JSON.stringify({ is_demo: true, event_name: eventName || "", ts: Date.now() })
        );
      } catch (_) {}
      return;
    }
    document.body.classList.remove("gastro-demo-active");
    bar.style.display = "none";
    try {
      sessionStorage.removeItem(CACHE_KEY);
    } catch (_) {}
  }

  function applyCachedDemo() {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return false;
      const data = JSON.parse(raw);
      if (data && data.is_demo) {
        applyDemoState(true, data.event_name || "");
        return true;
      }
    } catch (_) {}
    return false;
  }

  async function refreshDemoBanner() {
    const base = apiBase();
    if (!base) return;
    try {
      const res = await fetch(base + "/event/active", {
        method: "GET",
        cache: "no-store",
        credentials: "omit",
      });
      if (!res.ok) return;
      const data = await res.json();
      applyDemoState(!!data.is_demo, data.event_name || "");
    } catch (_) {}
  }

  applyCachedDemo();
  refreshDemoBanner();
  setInterval(refreshDemoBanner, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshDemoBanner();
  });
})();
