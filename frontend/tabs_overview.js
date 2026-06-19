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

function nav(href) {
    if (!href) return;
    window.location.href = href;
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
    const target = ctx && ctx.return_to ? ctx.return_to : "my_orders.html";
    nav(target);
}

async function renameTab(tab) {
    const name = window.prompt("Deckel umbenennen:", tab.name || "");
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) {
        alert("Name fehlt");
        return;
    }
    const res = await fetch(API + "/tabs/" + tab.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Umbenennen fehlgeschlagen");
        return;
    }
    if (typeof invalidateTabsCache === "function") {
        const ctx = getCtx() || {};
        invalidateTabsCache(ctx.station_id || null);
    }
    tabLoader.refresh();
}

function payTab(tabId) {
    const ctx = getCtx() || {};
    localStorage.setItem("tab_settle_ctx", JSON.stringify({
        tab_id: tabId,
        return_to: "tabs_overview.html",
        event_id: ctx.event_id || null,
        role: ctx.role || "waiter",
        user_id: ctx.user_id || null,
        station_id: ctx.station_id || null,
    }));
    nav("tab_settle.html");
}

function render(tabs) {
    const wrap = document.getElementById("tabs");
    if (!wrap || typeof renderTabTiles !== "function") return;

    renderTabTiles(wrap, tabs, {
        showAllBalances: true,
        onSelect: function (t) {
            payTab(t.id);
        },
        onRename: renameTab,
    });
}

function showLoadError(e) {
    const wrap = document.getElementById("tabs");
    if (!wrap) return;
    if (wrap.querySelector(".tabs-unified-grid, .tab-tile")) return;
    const err = document.createElement("div");
    err.className = "tab-empty-msg";
    err.textContent = "Fehler beim Laden: " + String(e.message || e);
    wrap.replaceChildren(err);
}

const tabLoader = createTabListLoader({
    api: API,
    getContainer: function () {
        return document.getElementById("tabs");
    },
    getStationId: function () {
        const ctx = getCtx() || {};
        return ctx.station_id || null;
    },
    onRender: render,
    onError: showLoadError,
});

tabLoader.load();
