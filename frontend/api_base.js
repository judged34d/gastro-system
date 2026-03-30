/**
 * Backend-Basis-URL:
 * - optional: window.GASTRO_API_BASE oder localStorage "gastro_api_base"
 * - jede *.mpbin.de-Seite (http oder https) → https://api.mpbin.de
 * - sonst gleicher Host :8000 (Pi/LAN)
 */
function getGastroApiBase() {
    if (window.GASTRO_API_BASE) {
        return window.GASTRO_API_BASE;
    }
    try {
        var ls = localStorage.getItem("gastro_api_base");
        if (ls && ls.trim()) {
            return ls.trim().replace(/\/$/, "");
        }
    } catch (e) {}
    const host = window.location.hostname || "";
    if (/(^|\.)mpbin\.de$/i.test(host)) {
        return "https://api.mpbin.de";
    }
    const proto = window.location.protocol;
    if (proto === "file:") {
        return "http://localhost:8000";
    }
    return proto + "//" + (host || "localhost") + ":8000";
}

window.getGastroApiBase = getGastroApiBase;
