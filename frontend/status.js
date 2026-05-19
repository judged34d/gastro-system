/**
 * Ampel:
 * - Grün: Tunnel + Backend (REMOTE_API /health) UND Frontend (gleiche Origin /health.json)
 * - Gelb: kein Tunnel/Remote, aber LAN: LOCAL_API /health OK und Frontend /health.json OK
 * - Rot: sonst
 */
(function () {
  const REMOTE_API = "https://api.mpbin.de";
  const LOCAL_API = "http://192.168.0.165:8000";
  const POLL_MS = 5000;
  let lastTouchEnd = 0;

  function enforceViewportZoomPolicy() {
    const vp = document.querySelector('meta[name="viewport"]');
    if (!vp) return;
    const content = vp.getAttribute("content") || "";
    if (/user-scalable\s*=\s*no/i.test(content)) {
      return;
    }
    vp.setAttribute("content", "width=device-width, initial-scale=1.0, user-scalable=yes, maximum-scale=5.0");
  }

  function preventDoubleTapZoom() {
    document.addEventListener(
      "touchend",
      function (ev) {
        if ((ev.changedTouches && ev.changedTouches.length !== 1) || (ev.touches && ev.touches.length > 0)) {
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

  async function fetchOk(url) {
    try {
      const r = await fetch(url, {
        method: "GET",
        cache: "no-store",
        credentials: "omit",
      });
      return r.ok;
    } catch (_) {
      return false;
    }
  }

  async function check() {
    const remoteHealth = REMOTE_API + "/health";
    const localHealth = LOCAL_API + "/health";
    const originHealth =
      window.location.origin + "/health.json";

    const remoteOk = await fetchOk(remoteHealth);
    // Mixed Content vermeiden: wenn die Seite über HTTPS läuft, darf der Browser
    // kein http://192.168... laden. "Gelb" ist sowieso nur im LAN-Modus relevant
    // (wenn man das Frontend direkt über http://<pi>:8080 öffnet).
    const canCheckLocal = window.location.protocol === "http:";
    const localOk = canCheckLocal ? await fetchOk(localHealth) : false;
    const frontendOk = await fetchOk(originHealth);

    let level = "red";
    let label = "Offline";

    if (remoteOk && frontendOk) {
      level = "green";
      label = "Online";
    } else if (!remoteOk && localOk && frontendOk) {
      level = "yellow";
      label = "Nur LAN";
    } else {
      level = "red";
      label = "Offline";
    }

    const bar = el();
    bar.className = "gastro-status " + level;
    bar.textContent = label;
    bar.title =
      level === "green"
        ? "Backend, Frontend und Tunnel erreichbar"
        : level === "yellow"
          ? "Nur lokal (LAN) – kein Tunnel zur API"
          : "System nicht voll nutzbar";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      enforceViewportZoomPolicy();
      preventDoubleTapZoom();
      check();
    });
  } else {
    enforceViewportZoomPolicy();
    preventDoubleTapZoom();
    check();
  }
  setInterval(check, POLL_MS);
})();

(function initGastroTapFeedback() {
  const TAP_SELECTOR =
    "button:not(:disabled), .product, .category, .header-btn, .minus, .tableBox, .terminal-big-btn";

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
