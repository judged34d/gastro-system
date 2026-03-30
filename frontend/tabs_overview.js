const API = (typeof window.getGastroApiBase === "function")
    ? window.getGastroApiBase()
    : (function () {
        if (window.GASTRO_API_BASE) return window.GASTRO_API_BASE;
        try {
            var ls = localStorage.getItem("gastro_api_base");
            if (ls && ls.trim()) return ls.trim().replace(/\/$/, "");
        } catch (e) {}
        var p = window.location.protocol;
        var h = window.location.hostname || "";
        if (/(^|\.)mpbin\.de$/i.test(h)) return "https://api.mpbin.de";
        if (p === "file:") return "http://localhost:8000";
        return p + "//" + (h || "localhost") + ":8000";
    })();

function formatEuro(v) {
    const n = Number(v || 0);
    return n.toFixed(2).replace(".", ",") + " €";
}

function getCtx() {
    try {
        return JSON.parse(localStorage.getItem("tabs_overview_ctx") || "null");
    } catch (_) {
        return null;
    }
}

function back() {
    const ctx = getCtx();
    localStorage.removeItem("tabs_overview_ctx");
    if (ctx && ctx.return_to) {
        window.location.href = ctx.return_to;
    } else {
        window.location.href = "my_orders.html";
    }
}

async function loadTabs() {
    const ctx = getCtx() || {};
    const qs = ctx.station_id ? ("?station_id=" + ctx.station_id) : "";
    const res = await fetch(API + "/tabs" + qs, { cache: "no-store" });
    if (!res.ok) {
        const t = await res.text();
        throw new Error(t || ("HTTP " + res.status));
    }
    const tabs = await res.json();
    return Array.isArray(tabs) ? tabs : [];
}

async function payTab(tabId) {
    const ctx = getCtx() || {};
    localStorage.setItem("tab_settle_ctx", JSON.stringify({
        tab_id: tabId,
        return_to: "tabs_overview.html",
        event_id: ctx.event_id || null,
        role: ctx.role || "waiter",
        user_id: ctx.user_id || null,
        station_id: ctx.station_id || null
    }));
    window.location.href = "tab_settle.html";
}

function render(tabs) {
    const wrap = document.getElementById("tabs");
    wrap.innerHTML = "";

    if (!tabs.length) {
        const empty = document.createElement("div");
        empty.className = "tab-tile";
        empty.style.width = "240px";
        empty.innerHTML = `<div class="tab-name">Keine offenen Deckel</div><div class="tab-balance"></div>`;
        wrap.appendChild(empty);
        return;
    }

    tabs.forEach(t => {
        const balance = Math.max(0, Number(t.balance || 0));
        if (balance <= 0.0001) return;
        const b = document.createElement("button");
        b.className = "tab-tile";
        b.onclick = () => payTab(t.id);
        b.innerHTML = `
            <div class="tab-name">${t.name}</div>
            <div class="tab-balance">Offen: ${formatEuro(balance)}<br><small>Klick = abrechnen</small></div>
        `;
        wrap.appendChild(b);
    });

    if (!wrap.children.length && tabs.length > 0) {
        const empty = document.createElement("div");
        empty.className = "tab-tile";
        empty.style.width = "min(100%, 320px)";
        empty.innerHTML = `<div class="tab-name">Keine offenen Deckel</div><div class="tab-balance"><small>Alle Deckel sind ausgeglichen.</small></div>`;
        wrap.appendChild(empty);
    }
}

async function load() {
    try {
        const tabs = await loadTabs();
        tabs.sort((a, b) => Number(b.balance || 0) - Number(a.balance || 0));
        render(tabs);
    } catch (e) {
        const wrap = document.getElementById("tabs");
        wrap.innerHTML = "";
        const err = document.createElement("div");
        err.className = "tab-tile";
        err.style.width = "min(100%, 360px)";
        err.innerHTML = `<div class="tab-name">Fehler beim Laden</div><div class="tab-balance">${String(e.message || e)}</div>`;
        wrap.appendChild(err);
    }
}

load();

