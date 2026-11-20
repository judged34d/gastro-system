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

let currentTabs = [];
let pendingCreateName = "";
let createBusy = false;

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

function isWaiterContext() {
    const ctx = getCtx() || {};
    return ctx.role !== "station" && !ctx.station_id;
}

function normalizeTabName(name) {
    return String(name || "")
        .trim()
        .toLocaleLowerCase("de")
        .replace(/ä/g, "a")
        .replace(/ö/g, "o")
        .replace(/ü/g, "u")
        .replace(/ß/g, "ss");
}

function isTabNameTakenLocally(name, excludeId) {
    const key = normalizeTabName(name);
    if (!key) return false;
    return currentTabs.some(function (t) {
        if (excludeId != null && Number(t.id) === Number(excludeId)) return false;
        return normalizeTabName(t.name) === key;
    });
}

function back() {
    const ctx = getCtx();
    const target = ctx && ctx.return_to ? ctx.return_to : "my_orders.html";
    nav(target);
}

function openCreate() {
    const panel = document.getElementById("create");
    const input = document.getElementById("newName");
    if (!panel) return;
    panel.style.display = "flex";
    if (input) {
        input.value = "";
        input.focus();
    }
}

function closeCreate() {
    const panel = document.getElementById("create");
    if (panel) panel.style.display = "none";
    pendingCreateName = "";
}

function showCreateConfirm(name) {
    const modal = document.getElementById("createConfirmModal");
    const label = document.getElementById("createConfirmName");
    pendingCreateName = name;
    if (label) {
        label.textContent = "Name: " + name;
    }
    if (modal) {
        modal.style.display = "flex";
        modal.setAttribute("aria-hidden", "false");
    }
}

function hideCreateConfirm() {
    const modal = document.getElementById("createConfirmModal");
    if (modal) {
        modal.style.display = "none";
        modal.setAttribute("aria-hidden", "true");
    }
}

function cancelCreateConfirm() {
    hideCreateConfirm();
    pendingCreateName = "";
}

async function confirmCreateTab() {
    const name = pendingCreateName;
    hideCreateConfirm();
    pendingCreateName = "";
    if (!name) return;
    await createTabRequest(name);
}

async function submitCreateTab() {
    if (createBusy) return;
    const input = document.getElementById("newName");
    const name = input ? input.value.trim() : "";
    if (!name) {
        alert("Deckelname fehlt");
        return;
    }
    if (isTabNameTakenLocally(name)) {
        alert("Ein Deckel mit diesem Namen existiert bereits.");
        return;
    }
    if (isWaiterContext()) {
        showCreateConfirm(name);
        return;
    }
    await createTabRequest(name);
}

async function createTabRequest(name) {
    if (createBusy) return;
    createBusy = true;
    const ctx = getCtx() || {};
    const qs = ctx.station_id ? ("?station_id=" + encodeURIComponent(ctx.station_id)) : "";
    const res = await fetch(API + "/tabs" + qs, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name }),
    });
    const data = await res.json().catch(function () { return {}; });
    createBusy = false;
    if (!res.ok) {
        alert(data.error || "Deckel konnte nicht angelegt werden");
        return;
    }
    if (typeof invalidateTabsCache === "function") {
        invalidateTabsCache(ctx.station_id || null);
    }
    closeCreate();
    tabLoader.refresh();
}

async function renameTab(tab) {
    const name = window.prompt("Deckel umbenennen:", tab.name || "");
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) {
        alert("Name fehlt");
        return;
    }
    if (isTabNameTakenLocally(trimmed, tab.id)) {
        alert("Ein Deckel mit diesem Namen existiert bereits.");
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
    currentTabs = Array.isArray(tabs) ? tabs : [];
    const wrap = document.getElementById("tabs");
    if (!wrap || typeof renderTabTiles !== "function") return;

    renderTabTiles(wrap, tabs, {
        showAllBalances: true,
        leadAddButton: true,
        onAdd: openCreate,
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

document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("newName");
    if (input) {
        input.addEventListener("keydown", function (ev) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                submitCreateTab();
            }
        });
    }
});
