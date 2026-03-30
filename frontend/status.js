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
    // Allow pinch zoom globally; we block accidental double-tap zoom via touch handler below.
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
