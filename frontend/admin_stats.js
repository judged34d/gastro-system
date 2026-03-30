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
let currentEventLabel = "";

function euro(v) {
    return Number(v || 0).toFixed(2).replace(".", ",") + " €";
}
function money(v) {
    return `<span class="num">${euro(v)}</span>`;
}

function nowStamp() {
    const d = new Date();
    return d.toLocaleString("de-DE");
}

function goBack() {
    window.location.href = "admin.html";
}

async function loadEvents() {
    const data = await fetch(API + "/admin/events").then(r => r.json());
    const sel = document.getElementById("eventSelect");
    const params = new URLSearchParams(window.location.search);
    const requestedEvent = params.get("event_id");
    sel.innerHTML = "";
    (data.events || []).forEach(e => {
        const op = document.createElement("option");
        op.value = e.id;
        op.text = `#${e.id} - ${e.name}`;
        if (requestedEvent && Number(requestedEvent) === Number(e.id)) op.selected = true;
        if (!requestedEvent && data.active_event && Number(data.active_event.id) === Number(e.id)) op.selected = true;
        sel.appendChild(op);
    });
    if (sel.options.length > 0 && !sel.value) sel.selectedIndex = 0;
}

function sumCell(label, value) {
    return `<div class="sum-label">${label}</div><span class="num">${euro(value)}</span>`;
}

function renderTable(elId, headers, rows, sumValues = null) {
    const table = document.getElementById(elId);
    let html = "<thead><tr>";
    headers.forEach(h => html += `<th>${h}</th>`);
    html += "</tr></thead><tbody>";
    rows.forEach(r => {
        html += "<tr>";
        r.forEach(c => html += `<td>${c}</td>`);
        html += "</tr>";
    });
    html += "</tbody>";
    if (sumValues && sumValues.length === 3) {
        const leftCols = Math.max(1, headers.length - 3);
        html += `<tfoot><tr class="sum-row"><td colspan="${leftCols}">SUMME</td><td>${sumCell("Offen", sumValues[0])}</td><td>${sumCell("Rest", sumValues[1])}</td><td>${sumCell("Alle Beträge", sumValues[2])}</td></tr></tfoot>`;
    }
    table.innerHTML = html;
}

async function loadStats() {
    const eventId = document.getElementById("eventSelect").value;
    const data = await fetch(API + "/admin/events/stats?event_id=" + eventId).then(r => r.json());
    const eventLabel = document.getElementById("eventSelect").selectedOptions?.[0]?.text || ("#" + eventId);
    currentEventLabel = eventLabel;

    document.getElementById("summary").innerHTML = `
        <div>Event: <b>${eventLabel}</b></div>
        <div>Erstellt am: <b>${nowStamp()}</b></div>
        <div>Orders gesamt: <b>${data.summary.orders_total || 0}</b> | bezahlt: <b>${data.summary.orders_paid || 0}</b> | offen: <b>${data.summary.orders_open || 0}</b></div>
    `;

    const orderOpen = (data.orders || []).reduce((s, o) => s + Number(o.open_amount || 0), 0);
    const orderAll = (data.orders || []).reduce((s, o) => s + Number(o.total_amount || 0), 0);
    const orderRest = orderAll - orderOpen;
    renderTable(
        "tableTotal",
        ["Order", "Bedienung", "Tisch", "Status", "Ordersumme", "Offen", "Abgerechnet"],
        (data.orders || []).map(o => [
            "#" + o.order_number,
            o.waiter_name || "-",
            o.table_name || "-",
            o.status,
            money(o.total_amount),
            money(o.open_amount),
            Number(o.open_amount || 0) <= 0.0001 ? "Ja" : "Nein",
        ]),
        [orderOpen, orderRest, orderAll]
    );

    const waiterOpen = (data.by_waiter || []).reduce((s, w) => s + Number(w.orders_open_amount || 0), 0);
    const waiterAll = (data.by_waiter || []).reduce((s, w) => s + Number(w.orders_total_amount || 0), 0);
    const waiterRest = waiterAll - waiterOpen;
    renderTable(
        "tableWaiter",
        ["Bedienung", "Orders", "Gesamtsumme Orders", "Offen", "Alles kassiert"],
        (data.by_waiter || []).map(w => [
            w.waiter_name || "-",
            w.orders || 0,
            money(w.orders_total_amount),
            money(w.orders_open_amount),
            Number(w.orders_open_amount || 0) <= 0.0001 ? "Ja" : "Nein",
        ]),
        [waiterOpen, waiterRest, waiterAll]
    );

    const tableOpen = (data.by_table || []).reduce((s, t) => s + Number(t.orders_open_amount || 0), 0);
    const tableAll = (data.by_table || []).reduce((s, t) => s + Number(t.orders_total_amount || 0), 0);
    const tableRest = tableAll - tableOpen;
    renderTable(
        "tableTables",
        ["Tisch", "Orders", "Gesamtsumme Orders", "Offen", "Alles kassiert"],
        (data.by_table || []).map(t => [
            t.table_name || "-",
            t.orders || 0,
            money(t.orders_total_amount),
            money(t.orders_open_amount),
            Number(t.orders_open_amount || 0) <= 0.0001 ? "Ja" : "Nein",
        ]),
        [tableOpen, tableRest, tableAll]
    );

    const tabsOpen = (data.tabs || []).reduce((s, t) => s + Number(t.balance || 0), 0);
    const tabsAll = (data.tabs || []).reduce((s, t) => s + Number(t.entries_amount || 0), 0);
    const tabsRest = tabsAll - tabsOpen;
    renderTable(
        "tableTabs",
        ["Deckel", "Gesamtsumme", "Bezahlt", "Offen", "Status"],
        (data.tabs || []).map(t => [
            t.name,
            money(t.entries_amount),
            money(t.payments_amount),
            money(t.balance),
            Number(t.balance || 0) <= 0.0001 ? "Kassiert" : "Zahlungen offen",
        ]),
        [tabsOpen, tabsRest, tabsAll]
    );

    const catOpen = (data.by_category || []).reduce((s, c) => s + Number(c.open_amount || 0), 0);
    const catAll = (data.by_category || []).reduce((s, c) => s + Number(c.total_amount || 0), 0);
    const catRest = catAll - catOpen;
    renderTable(
        "tableCategories",
        ["Kategorie", "Offen", "Rest", "Gesamt"],
        (data.by_category || []).map(c => [
            c.category_name || "-",
            money(c.open_amount),
            money(Number(c.total_amount || 0) - Number(c.open_amount || 0)),
            money(c.total_amount),
        ]),
        [catOpen, catRest, catAll]
    );

    document.getElementById("finalTotal").innerHTML =
        `<div>Gesamter Umsatz: <span class="num">${euro(data.revenue_total_amount || 0)}</span></div>` +
        `<div>Noch offen: <span class="num">${euro(data.open_total_amount || 0)}</span></div>`;
}

function printFullReport() {
    const summary = document.getElementById("summary");
    const total = document.getElementById("tableTotal");
    const waiter = document.getElementById("tableWaiter");
    const tables = document.getElementById("tableTables");
    const tabs = document.getElementById("tableTabs");
    const categories = document.getElementById("tableCategories");
    const finalTotal = document.getElementById("finalTotal");

    const w = window.open("", "_blank");
    w.document.write(`
        <html><head><title>Event-Statistik</title>
        <style>
          body{font-family:Arial,sans-serif;padding:16px}
          h1{font-size:20px;margin-bottom:6px}
          h2{font-size:16px;margin:16px 0 6px}
          .meta{margin-bottom:10px;color:#444}
          table{width:100%;border-collapse:collapse}
          th,td{border:1px solid #ddd;padding:8px;font-size:12px;text-align:left}
          th{background:#f3f3f3}
          .block{margin-bottom:14px}
          .final{font-size:16px;font-weight:700;margin-top:12px}
        </style></head><body>
        <h1>Event-Statistik</h1>
        <div class="meta">Event: ${currentEventLabel || "-"}</div>
        <div class="meta">Erstellt am: ${nowStamp()}</div>
        <div class="block">${summary ? summary.innerHTML : ""}</div>
        <h2>Gesamt (Orders)</h2>
        ${total ? total.outerHTML : ""}
        <h2>Bedienungen</h2>
        ${waiter ? waiter.outerHTML : ""}
        <h2>Tische</h2>
        ${tables ? tables.outerHTML : ""}
        <h2>Deckel</h2>
        ${tabs ? tabs.outerHTML : ""}
        <h2>Kategorien</h2>
        ${categories ? categories.outerHTML : ""}
        <div class="final">${finalTotal ? finalTotal.innerHTML : ""}</div>
        </body></html>
    `);
    w.document.close();
    w.focus();
    w.print();
    w.close();
}

loadEvents().then(loadStats);

