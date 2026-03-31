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

async function fetchTabs(ctx) {
    const qs = ctx && ctx.station_id ? ("?station_id=" + ctx.station_id) : "";
    const res = await fetch(API + "/tabs" + qs, { cache: "no-store" });
    return await res.json();
}

function renderTabs(tabs) {
    const ctx = getCtx() || {};
    const wrap = document.getElementById("tabs");
    wrap.innerHTML = "";

    const add = document.createElement("button");
    add.className = "tab-tile tab-tile-add";
    add.onclick = () => openCreate();
    add.innerHTML = `
        <div class="tab-name">+ Deckel</div>
        <div class="tab-balance">Hinzufügen</div>
    `;
    wrap.appendChild(add);

    tabs.forEach(t => {
        const b = document.createElement("button");
        b.className = "tab-tile";
        if ((ctx.mode === "tab_transfer_items" || ctx.mode === "tab_transfer") && Number(ctx.source_tab_id) === Number(t.id)) {
            b.disabled = true;
        }
        b.onclick = () => chooseTab(t.id);
        b.innerHTML = `
            <div class="tab-name">${t.name}</div>
            <div class="tab-balance">Offen: ${formatEuro(t.balance)}</div>
        `;
        wrap.appendChild(b);
    });
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
        body: JSON.stringify({ name })
    });
    if (!res.ok) {
        alert("Deckel konnte nicht angelegt werden");
        return;
    }
    closeCreate();
    load();
}

async function chooseTab(tabId) {
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
        for (const e of entries) {
            const pres = await fetch(API + "/orders/" + e.order_id + "/pay-item", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_item_id: e.order_item_id,
                    quantity: e.quantity,
                    payment_type: "tab",
                    tab_id: tabId
                })
            });
            const pdata = await pres.json().catch(() => ({}));
            if (!pres.ok) {
                alert(pdata.message || pdata.error || ("Buchung fehlgeschlagen (" + pres.status + ")"));
                return;
            }
        }
        localStorage.removeItem("tab_ctx");
        if (ctx.mode === "station_pay_items") {
            localStorage.removeItem("order_manage_ctx");
            window.location.href = "kitchen.html";
        } else {
            window.location.href = "order_manage.html";
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
                created_by_station_id: ctx.station_id || null
            })
        });
        const data = await res.json();
        if (!res.ok) {
            alert(data.error || "Umbuchung fehlgeschlagen");
            return;
        }
        alert("Umgebucht: " + formatEuro(data.moved_amount || 0));
        localStorage.removeItem("tab_ctx");
        window.location.href = "tabs_overview.html";
        return;
    }

    if (ctx.mode === "tab_transfer") {
        if (!ctx.source_tab_id) {
            alert("Quell-Deckel fehlt");
            return;
        }
        const amount = (ctx.amount === null || ctx.amount === undefined || ctx.amount === "")
            ? null
            : Number(ctx.amount);
        if (amount !== null && (!Number.isFinite(amount) || amount <= 0)) {
            alert("Ungültiger Betrag");
            return;
        }
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
                created_by_station_id: ctx.station_id || null
            })
        });
        const data = await res.json();
        if (!res.ok) {
            alert(data.error || "Umbuchung fehlgeschlagen");
            return;
        }
        alert("Umgebucht: " + formatEuro(data.moved_amount || 0));
        localStorage.removeItem("tab_ctx");
        window.location.href = "tabs_overview.html";
        return;
    }

    alert("Unbekannter Kontext");
}

function cancel() {
    const ctx = getCtx();
    localStorage.removeItem("tab_ctx");
    if (ctx && ctx.mode === "station_pay_items") {
        window.location.href = "kitchen.html";
    } else if (ctx && (ctx.mode === "tab_transfer" || ctx.mode === "tab_transfer_items")) {
        window.location.href = "tabs_overview.html";
    } else {
        window.location.href = "order_manage.html";
    }
}

async function load() {
    const ctx = getCtx();
    setSubtitle(ctx);
    const tabs = await fetchTabs(ctx);
    renderTabs(Array.isArray(tabs) ? tabs : []);
}

load();

