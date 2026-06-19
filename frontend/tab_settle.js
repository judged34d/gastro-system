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
let ctx = null;
let tab = null;
let items = {};
let selection = {};
let actionBusy = false;

function euro(v) {
    return Number(v || 0).toFixed(2).replace(".", ",") + " €";
}

function nav(href) {
    if (!href) return;
    window.location.href = href;
}

function getCtx() {
    try {
        return JSON.parse(localStorage.getItem("tab_settle_ctx") || "null");
    } catch (_) {
        return null;
    }
}

function backToOverview() {
    if (ctx && ctx.return_to) {
        nav(ctx.return_to);
    } else {
        nav("tabs_overview.html");
    }
}

function cancel() {
    localStorage.removeItem("tab_settle_ctx");
    backToOverview();
}

async function loadTab() {
    ctx = getCtx();
    if (!ctx || !ctx.tab_id) {
        alert("Kein Deckel-Kontext gefunden");
        nav("tabs_overview.html");
        return;
    }
    const qs = ctx.event_id ? ("?event_id=" + encodeURIComponent(ctx.event_id)) : "";
    const res = await fetch(API + "/tabs/" + ctx.tab_id + "/items" + qs, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || "Deckel nicht gefunden");
        cancel();
        return;
    }
    tab = { id: data.tab_id, name: data.tab_name };
    document.getElementById("title").innerText = "Deckel: " + (tab.name || ("#" + tab.id));

    items = {};
    selection = {};
    (data.items || []).forEach((i) => {
        if (!items[i.name]) {
            items[i.name] = {
                name: i.name,
                price: Number(i.unit_price || 0),
                quantity_open: 0,
                quantity_total: 0,
                quantity_paid: 0,
                entries: []
            };
        }
        items[i.name].quantity_open += Number(i.quantity_open || 0);
        items[i.name].quantity_total += Number(i.quantity_total || 0);
        items[i.name].quantity_paid += Number(i.quantity_paid || 0);
        items[i.name].entries.push({
            tab_entry_id: i.tab_entry_id,
            qty: Number(i.quantity_open || 0)
        });
    });
    Object.keys(items).forEach((k) => { selection[k] = 0; });
    render();
}

async function cancelItems() {
    if (actionBusy || !tab) return;
    const reasonEl = document.getElementById("cancelReason");
    const reason = reasonEl && reasonEl.value ? String(reasonEl.value) : "";
    if (!reason) {
        alert("Bitte einen Storno-Grund auswählen.");
        return;
    }
    const entries = buildSelectedEntries();
    if (!entries.length) {
        alert("Keine Auswahl getroffen");
        return;
    }
    if (!window.confirm("Ausgewählte Positionen wirklich stornieren?")) {
        return;
    }

    actionBusy = true;
    const qs = ctx.event_id ? ("?event_id=" + encodeURIComponent(ctx.event_id)) : "";
    const payload = {
        entries: entries,
        reason: reason,
        created_by_role: ctx.role || "waiter",
        created_by_user_id: ctx.user_id || null,
        created_by_station_id: ctx.station_id || null,
    };

    const res = await fetch(API + "/tabs/" + tab.id + "/cancel-items" + qs, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const data = await res.json().catch(function () { return {}; });
    actionBusy = false;
    if (!res.ok) {
        alert(data.error || data.message || "Storno fehlgeschlagen");
        return;
    }
    alert("Storno erfolgreich verbucht");
    if (reasonEl) reasonEl.value = "";
    if (typeof invalidateTabsCache === "function") {
        invalidateTabsCache(ctx.station_id || null);
    }
    loadTab();
}

async function payNowWithType(paymentType) {
    if (actionBusy) return;
    if (!tab) return;
    const entries = buildSelectedEntries();
    if (!entries.length) {
        alert("Keine Auswahl getroffen");
        return;
    }
    const qs = ctx.event_id ? ("?event_id=" + encodeURIComponent(ctx.event_id)) : "";
    const payload = {
        entries,
        payment_type: paymentType,
        created_by_role: ctx.role || "waiter",
        created_by_user_id: ctx.user_id || null,
        created_by_station_id: ctx.station_id || null
    };

    const res = await fetch(API + "/tabs/" + tab.id + "/pay-items" + qs, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || "Fehler beim Kassieren");
        return;
    }
    alert((paymentType === "card" ? "Kartenzahlung: " : "Kassiert: ") + euro(data.paid_amount || 0));
    if (typeof invalidateTabsCache === "function") {
        invalidateTabsCache(ctx.station_id || null);
    }
    localStorage.removeItem("tab_settle_ctx");
    backToOverview();
}

async function payNow() {
    return payNowWithType("paid");
}

async function payNowCard() {
    return payNowWithType("card");
}

function moveToOtherTab() {
    if (!tab) return;
    const entries = buildSelectedEntries();
    if (!entries.length) {
        alert("Keine Auswahl getroffen");
        return;
    }
    localStorage.setItem("tab_ctx", JSON.stringify({
        mode: "tab_transfer_items",
        source_tab_id: tab.id,
        entries,
        station_id: ctx.station_id || null,
        event_id: ctx.event_id || null,
        role: ctx.role || "waiter",
        user_id: ctx.user_id || null
    }));
    localStorage.removeItem("tab_settle_ctx");
    nav("tab_select.html");
}

function add(name) {
    if (selection[name] < items[name].quantity_open) selection[name]++;
    render();
}

function remove(name) {
    if (selection[name] > 0) selection[name]--;
    render();
}

function selectAll(name) {
    selection[name] = Number(items[name].quantity_open || 0);
    render();
}

function render() {
    const container = document.getElementById("orders");
    container.innerHTML = "";
    let payTotal = 0;
    let restTotal = 0;
    Object.values(items).forEach((i) => {
        const selectedQty = Number(selection[i.name] || 0);
        const remainingQty = Number(i.quantity_open) - selectedQty;
        payTotal += selectedQty * i.price;
        restTotal += remainingQty * i.price;
        const safeName = i.name.replace(/'/g, "\\'");
        const div = document.createElement("div");
        div.className = "item";
        div.innerHTML = `
            <div>
              <div>${remainingQty}x ${i.name}</div>
              <div class="item-detail">Bezahlt: ${i.quantity_paid} | Offen: ${i.quantity_open}</div>
            </div>
            <div>${euro(i.price)}</div>
            <div>${euro(remainingQty * i.price)}</div>
            <div class="selector">
                <button class="plus-btn" onclick="add('${safeName}')">+</button>
                <span class="selector-value">${selectedQty}</span>
                <button class="minus-btn" onclick="remove('${safeName}')">-</button>
                <button class="all-btn" onclick="selectAll('${safeName}')">Alle</button>
            </div>
        `;
        container.appendChild(div);
    });
    document.getElementById("total").innerText =
        "Zu zahlen: " + euro(payTotal) + " | Rest: " + euro(restTotal);
}

function buildSelectedEntries() {
    const result = [];
    for (const name of Object.keys(items)) {
        let qty = Number(selection[name] || 0);
        if (qty <= 0) continue;
        for (const e of items[name].entries) {
            if (qty <= 0) break;
            const use = Math.min(qty, Number(e.qty || 0));
            if (use > 0) {
                result.push({ tab_entry_id: e.tab_entry_id, quantity: use });
                qty -= use;
            }
        }
    }
    return result;
}

loadTab();

