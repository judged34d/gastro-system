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
const ORDER_STATUS_MAX_ITEM_ROWS = 8;

/** SVG-Haken (gut sichtbar auf dunklem Hintergrund) */
const SVG_CHECK =
    '<svg class="prep-svg" viewBox="0 0 24 24" focusable="false" aria-hidden="true">' +
    '<path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
const SVG_CROSS =
    '<svg class="prep-svg" viewBox="0 0 24 24" focusable="false" aria-hidden="true">' +
    '<path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';

function formatPrice(v) {
    return Number(v).toFixed(2).replace(".", ",") + " €";
}

function statusClass(key) {
    const k = String(key || "open");
    if (k === "ready") return "sk-ready";
    if (k === "preparing") return "sk-preparing";
    if (k === "partial") return "sk-partial";
    if (k === "paid") return "sk-paid";
    if (k === "new") return "sk-new";
    return "sk-open";
}

async function load() {
    const grid = document.getElementById("grid");
    const info = document.getElementById("info");
    grid.innerHTML = "";

    let orders = [];
    try {
        const res = await fetch(API + "/orders/status-board", { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        orders = Array.isArray(data) ? data : [];
    } catch (e) {
        info.innerText = "Fehler beim Laden · " + (e.message || e);
        const err = document.createElement("div");
        err.className = "tile";
        err.innerHTML = "<div class='tile-header'>Keine Verbindung zur API</div><div class='meta'>Prüfen Sie Netzwerk / gleichen Host :8000</div>";
        grid.appendChild(err);
        while (grid.children.length < 15) {
            const empty = document.createElement("div");
            empty.className = "tile";
            empty.style.opacity = "0.2";
            empty.innerHTML = "<div class='tile-header'>-</div>";
            grid.appendChild(empty);
        }
        return;
    }

    const shown = orders.slice(0, 15);
    const rest = Math.max(0, orders.length - shown.length);
    info.innerText = shown.length + " / " + orders.length + " offene Bestellungen" + (rest > 0 ? (" | +" + rest + " weitere") : "") +
        " · nach Bezahlung aus der Ansicht · Theken-Display: Kachel max. 90s / bei Platzbedarf";

    shown.forEach(o => {
        const div = document.createElement("div");
        const sk = o.status_key || "open";
        div.className = "tile" + (o.all_ready ? " all-ready" : "") + " st-" + sk;

        let html = "";
        html += "<div class='tile-header'>#" + o.order_number + " - " + o.table_name + "</div>";
        html += "<div class='meta'>" + o.waiter_name + " | Stationen: " + o.station_ready + "/" + o.station_total + "</div>";
        html += "<div class='status-pill " + statusClass(sk) + "'>" + (o.status || "") + "</div>";
        html += "<div class='table'>";
        html += "<div class='row header-row'><div class='prep-cell prep-h'>Zub.</div><div>Artikel</div><div>Preis</div><div>Summe</div></div>";
        const items = o.items || [];
        const preview = items.length > ORDER_STATUS_MAX_ITEM_ROWS ? items.slice(0, ORDER_STATUS_MAX_ITEM_ROWS) : items;
        const more = Math.max(0, items.length - preview.length);
        preview.forEach(i => {
            let inner;
            let title;
            let icls;
            if (i.prep_ready === true) {
                inner = SVG_CHECK;
                title = "Zubereitet";
                icls = "prep-yes";
            } else if (i.prep_ready === false) {
                inner = SVG_CROSS;
                title = "Noch nicht zubereitet";
                icls = "prep-no";
            } else {
                inner = "?";
                title = "Status unbekannt (Backend/Deploy prüfen)";
                icls = "prep-unknown";
            }
            html += "<div class='row'><div class='prep-cell' title='" + title + "'><span class='prep-badge prep-icon " + icls + "'>" + inner + "</span></div><div>" +
                i.quantity_open + "x " + i.name + "</div><div>" +
                formatPrice(i.price) + "</div><div>" + formatPrice(i.quantity_open * i.price) + "</div></div>";
        });
        if (more > 0) {
            html += "<div class='row row-more'>+" + more + " weitere Artikel</div>";
        }
        html += "</div>";
        html += "<div class='total'>Offen: " + formatPrice(o.total_open) + "</div>";
        div.innerHTML = html;
        grid.appendChild(div);
    });

    while (grid.children.length < 15) {
        const empty = document.createElement("div");
        empty.className = "tile";
        empty.style.opacity = "0.25";
        empty.innerHTML = "<div class='tile-header'>-</div>";
        grid.appendChild(empty);
    }
}

load();
setInterval(load, 3000);
