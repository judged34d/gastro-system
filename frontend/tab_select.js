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

let selectBusy = false;

function nav(href) {
    if (!href) return;
    window.location.href = href;
}

function getCtx() {
    try {
        return JSON.parse(localStorage.getItem("tab_ctx") || "null");
    } catch (_) {
        return null;
    }
}

function setSubtitle(ctx) {
    const el = document.getElementById("subtitle");
    if (!el) return;
    if (!ctx) {
        el.textContent = "";
        return;
    }
    if (ctx.mode === "waiter_pay_items") {
        el.textContent = "Auswahl auf Deckel schreiben";
    } else if (ctx.mode === "station_pay_items") {
        el.textContent = "Theken-Artikel auf Deckel schreiben";
    } else if (ctx.mode === "tab_transfer_items") {
        el.textContent = "Artikel auf anderen Deckel umbuchen";
    } else if (ctx.mode === "tab_transfer") {
        el.textContent = "Betrag auf anderen Deckel umbuchen";
    } else {
        el.textContent = "";
    }
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

function renderTabs(tabs) {
    const ctx = getCtx() || {};
    const wrap = document.getElementById("tabs");
    if (!wrap || typeof renderTabTiles !== "function") return;

    renderTabTiles(wrap, tabs, {
        showAllBalances: true,
        leadAddButton: true,
        onAdd: openCreate,
        onRename: renameTab,
        disableTabId:
            ctx.mode === "tab_transfer_items" || ctx.mode === "tab_transfer"
                ? ctx.source_tab_id
                : null,
        onSelect: function (t) {
            chooseTab(t.id);
        },
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

function openCreate() {
    document.getElementById("create").style.display = "block";
    const i = document.getElementById("newName");
    i.value = "";
    i.focus();
}

function closeCreate() {
    document.getElementById("create").style.display = "none";
}

async function createTab() {
    const ctx = getCtx() || {};
    const name = (document.getElementById("newName").value || "").trim();
    if (!name) {
        alert("Deckelname fehlt");
        return;
    }
    const qs = ctx.station_id ? ("?station_id=" + ctx.station_id) : "";
    const res = await fetch(API + "/tabs" + qs, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    });
    if (!res.ok) {
        alert("Deckel konnte nicht angelegt werden");
        return;
    }
    if (typeof invalidateTabsCache === "function") {
        invalidateTabsCache(ctx.station_id || null);
    }
    closeCreate();
    tabLoader.refresh();
}

async function chooseTab(tabId) {
    if (selectBusy) return;
    const ctx = getCtx();
    if (!ctx) {
        alert("Kein Kontext gefunden");
        return;
    }

    if (ctx.mode === "waiter_pay_items" || ctx.mode === "station_pay_items") {
        const entries = Array.isArray(ctx.entries) ? ctx.entries : [];
        if (!entries.length) {
            alert("Keine Auswahl getroffen");
            return;
        }
        selectBusy = true;
        for (const e of entries) {
            const pres = await fetch(API + "/orders/" + e.order_id + "/pay-item", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_item_id: e.order_item_id,
                    quantity: e.quantity,
                    payment_type: "tab",
                    tab_id: tabId,
                }),
            });
            const pdata = await pres.json().catch(() => ({}));
            if (!pres.ok) {
                selectBusy = false;
                alert(pdata.message || pdata.error || ("Buchung fehlgeschlagen (" + pres.status + ")"));
                return;
            }
        }
        selectBusy = false;
        if (typeof invalidateTabsCache === "function") {
            invalidateTabsCache(ctx.station_id || null);
        }
        localStorage.removeItem("tab_ctx");
        if (ctx.mode === "station_pay_items") {
            localStorage.removeItem("order_manage_ctx");
            nav("kitchen.html");
        } else {
            nav("order_manage.html");
        }
        return;
    }

    if (ctx.mode === "tab_transfer_items") {
        if (!ctx.source_tab_id) {
            alert("Quell-Deckel fehlt");
            return;
        }
        const entries = Array.isArray(ctx.entries) ? ctx.entries : [];
        if (!entries.length) {
            alert("Keine Artikel gewählt");
            return;
        }
        selectBusy = true;
        const qs = ctx.event_id ? ("?event_id=" + encodeURIComponent(ctx.event_id)) : "";
        const res = await fetch(API + "/tabs/transfer-items" + qs, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_tab_id: ctx.source_tab_id,
                target_tab_id: tabId,
                entries,
                created_by_role: ctx.role || "waiter",
                created_by_user_id: ctx.user_id || null,
                created_by_station_id: ctx.station_id || null,
            }),
        });
        const data = await res.json();
        selectBusy = false;
        if (!res.ok) {
            alert(data.error || "Umbuchung fehlgeschlagen");
            return;
        }
        alert("Umgebucht: " + formatEuro(data.moved_amount || 0));
        if (typeof invalidateTabsCache === "function") {
            invalidateTabsCache(ctx.station_id || null);
        }
        localStorage.removeItem("tab_ctx");
        nav("tabs_overview.html");
        return;
    }

    if (ctx.mode === "tab_transfer") {
        if (!ctx.source_tab_id) {
            alert("Quell-Deckel fehlt");
            return;
        }
        const amount =
            ctx.amount === null || ctx.amount === undefined || ctx.amount === ""
                ? null
                : Number(ctx.amount);
        if (amount !== null && (!Number.isFinite(amount) || amount <= 0)) {
            alert("Ungültiger Betrag");
            return;
        }
        selectBusy = true;
        const qs = ctx.event_id ? ("?event_id=" + encodeURIComponent(ctx.event_id)) : "";
        const res = await fetch(API + "/tabs/transfer" + qs, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_tab_id: ctx.source_tab_id,
                target_tab_id: tabId,
                amount: amount || 999999999,
                created_by_role: ctx.role || "waiter",
                created_by_user_id: ctx.user_id || null,
                created_by_station_id: ctx.station_id || null,
            }),
        });
        const data = await res.json();
        selectBusy = false;
        if (!res.ok) {
            alert(data.error || "Umbuchung fehlgeschlagen");
            return;
        }
        alert("Umgebucht: " + formatEuro(data.moved_amount || 0));
        if (typeof invalidateTabsCache === "function") {
            invalidateTabsCache(ctx.station_id || null);
        }
        localStorage.removeItem("tab_ctx");
        nav("tabs_overview.html");
        return;
    }

    alert("Unbekannter Kontext");
}

function formatEuro(v) {
    return Number(v || 0).toFixed(2).replace(".", ",") + " €";
}

function cancel() {
    const ctx = getCtx();
    localStorage.removeItem("tab_ctx");
    if (ctx && ctx.mode === "station_pay_items") {
        nav("kitchen.html");
    } else if (ctx && (ctx.mode === "tab_transfer" || ctx.mode === "tab_transfer_items")) {
        nav("tabs_overview.html");
    } else if (ctx && ctx.mode === "waiter_pay_items") {
        nav("order_manage.html");
    } else {
        nav("tabs_overview.html");
    }
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
    onRender: function (tabs) {
        setSubtitle(getCtx());
        renderTabs(tabs);
    },
    onError: showLoadError,
});

tabLoader.load();
