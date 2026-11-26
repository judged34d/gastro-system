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

/* ============================================================
STATION NAME AUS LOGIN
============================================================ */
const stationName = localStorage.getItem("user_name");
document.getElementById("stationName").innerText = stationName || "Theke";

/* ============================================================
STATION ID
============================================================ */
let STATION_ID = localStorage.getItem("user_id");
let mode = "display";
const KITCHEN_SLOTS_KEY = "kitchen_display_slots";
let kitchenSlots = 15;
let stationProducts = [];
let stationCart = [];
let stationCategories = [];
let activeStationCategory = null;
let actionBusy = false;
/** Autodruck aus Admin; bei false → Bon-Button auf jeder Order-Kachel */
let ticketAutoprint = false;
let ticketPrinterReady = false;
let ticketConnection = "browser";
let printedOrderIds = new Set();

/** Max. Artikelzeilen in der Kachel; darüber Klick öffnet Detail-Modal */
const KITCHEN_TILE_MAX_ITEM_ROWS = 3;
let kitchenModalSlot = null;

function getKitchenSlots() {
    const n = Number(localStorage.getItem(KITCHEN_SLOTS_KEY) || 15);
    return n === 8 ? 8 : 15;
}

function applyKitchenSlotsLayout() {
    kitchenSlots = getKitchenSlots();
    document.documentElement.setAttribute("data-kitchen-slots", String(kitchenSlots));
    const btn15 = document.getElementById("kitchenSlots15");
    const btn8 = document.getElementById("kitchenSlots8");
    if (btn15) btn15.classList.toggle("is-active", kitchenSlots === 15);
    if (btn8) btn8.classList.toggle("is-active", kitchenSlots === 8);
}

function setKitchenSlots(count) {
    kitchenSlots = count === 8 ? 8 : 15;
    localStorage.setItem(KITCHEN_SLOTS_KEY, String(kitchenSlots));
    applyKitchenSlotsLayout();
    if (mode === "display") {
        load();
    }
}

function kitchenDisplayUrl() {
    return API + "/station/" + STATION_ID + "/display?slots=" + getKitchenSlots();
}

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const merged = Object.assign({}, options || {}, { signal: controller.signal });
    return fetch(url, merged).finally(() => clearTimeout(timer));
}

function setActionBusy(busy, text) {
    let overlay = document.getElementById("kitchenBusyOverlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "kitchenBusyOverlay";
        overlay.style.position = "fixed";
        overlay.style.inset = "0";
        overlay.style.zIndex = "1200";
        overlay.style.display = "none";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.background = "rgba(0,0,0,0.55)";
        overlay.style.fontSize = "20px";
        overlay.style.fontWeight = "bold";
        overlay.style.textAlign = "center";
        overlay.style.padding = "20px";
        document.body.appendChild(overlay);
    }
    overlay.innerText = text || "Bitte warten...";
    overlay.style.display = busy ? "flex" : "none";
}

/* ============================================================
STATUS TEXT
============================================================ */
function getStatusText(status) {
    if (status === "new") return "Neu";
    if (status === "preparing") return "Zubereitung";
    if (status === "ready") return "Zubereitet";
    return "";
}

function getStatusClass(status) {
    if (status === "new") return "status-new";
    if (status === "preparing") return "status-preparing";
    if (status === "ready") return "status-ready";
    return "";
}

/* ============================================================
KÜCHE: DETAIL-MODAL (lange Bestellungen)
============================================================ */
function closeKitchenOrderModal() {
    const modal = document.getElementById("kitchenDetailModal");
    if (modal) modal.classList.remove("is-open");
    kitchenModalSlot = null;
}

function openKitchenOrderModal(slot) {
    kitchenModalSlot = slot;
    const modal = document.getElementById("kitchenDetailModal");
    const titleEl = document.getElementById("kitchenModalTitle");
    const bodyEl = document.getElementById("kitchenModalBody");
    if (!modal || !titleEl || !bodyEl) return;

    titleEl.textContent = "#" + slot.order_number + " · " + slot.table_name + " · " + slot.waiter_name;

    let html = "<div class='table kitchen-modal-table'>";
    html += "<div class='row header-row'><div>Artikel</div><div>Preis</div><div>Summe</div></div>";
    slot.items.forEach(i => {
        html += "<div class='row'>";
        html += "<div>" + i.quantity_open + "x " + i.name + "</div>";
        html += "<div>" + formatPrice(i.unit_price) + "</div>";
        html += "<div>" + formatPrice(i.line_total) + "</div>";
        html += "</div>";
    });
    html += "</div>";
    html += "<div class='kitchen-modal-total'>Gesamt: " + formatPrice(slot.order_total) + "</div>";
    html += "<div class='kitchen-modal-status " + getStatusClass(slot.status) + "'>" + getStatusText(slot.status) + "</div>";
    bodyEl.innerHTML = html;

    const printBtn = document.querySelector("#kitchenDetailModal .kitchen-print-btn");
    if (printBtn) {
        printBtn.style.display = ticketPrinterReady ? "" : "none";
        printBtn.textContent = ticketAutoprint ? "Bon erneut" : "Bon drucken";
    }

    modal.classList.add("is-open");
}

async function confirmKitchenModalStatus() {
    if (actionBusy) return;
    if (!kitchenModalSlot) return;
    const oid = kitchenModalSlot.order_id;
    actionBusy = true;
    setActionBusy(true, "Status wird aktualisiert...");
    const res = await fetchWithTimeout(API + "/station/" + STATION_ID + "/orders/" + oid + "/status", {
        method: "POST"
    }, 10000).catch(() => null);
    actionBusy = false;
    setActionBusy(false);
    if (!res || !res.ok) {
        alert("Statusänderung fehlgeschlagen (Verbindung/Server).");
        return;
    }
    closeKitchenOrderModal();
    load();
}

function escapeHtml(s) {
    return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function openBrowserTicketPrint(ticket) {
    const items = (ticket.items || [])
        .map(i =>
            "<div class='item'><div class='qty'>" + escapeHtml(i.quantity) + "x</div>" +
            "<div class='iname'>" + escapeHtml(i.name) + "</div></div>"
        )
        .join("");
    const html =
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Bon</title><style>" +
        "@page{size:80mm auto;margin:3mm}" +
        "body{font-family:Arial Black,Arial,sans-serif;font-size:14px;width:74mm;margin:0;color:#000;background:#fff}" +
        ".logo{display:block;width:48mm;max-height:28mm;margin:0 auto 4px;object-fit:contain}" +
        ".station{text-align:center;font-size:16px;font-weight:800;margin:4px 0}" +
        ".waiter{text-align:center;font-size:32px;font-weight:900;line-height:1.05;margin:8px 0}" +
        ".table{font-size:28px;font-weight:900;line-height:1.1;margin:6px 0}" +
        ".meta{font-size:16px;font-weight:700;margin:2px 0}" +
        ".sep{border:none;border-top:2px solid #000;margin:8px 0}" +
        ".item{margin:8px 0}.qty{font-size:30px;font-weight:900;line-height:1}" +
        ".iname{font-size:20px;font-weight:700;line-height:1.15;margin-top:2px}" +
        ".foot{text-align:center;font-size:11px;margin-top:8px}" +
        "</style></head><body>" +
        "<img class='logo' src='ticket_logo.png' alt=''>" +
        "<div class='station'>" + escapeHtml(ticket.station_name || "") + "</div>" +
        "<div class='waiter'>" + escapeHtml(ticket.waiter_name || "—") + "</div>" +
        "<hr class='sep'>" +
        "<div class='table'>TISCH " + escapeHtml(ticket.table_name || "—") + "</div>" +
        "<div class='meta'>Order #" + escapeHtml(ticket.order_number || "") + "</div>" +
        "<div class='meta'>Zeit " + escapeHtml(ticket.created_at || "") + "</div>" +
        "<hr class='sep'>" + items + "<hr class='sep'>" +
        "<div class='foot'>Laufzettel – kein Kassenbon</div>" +
        "</body></html>";
    const w = window.open("", "_blank", "width=340,height=560");
    if (!w) throw new Error("Popup blockiert – bitte Popups für Gastro erlauben");
    w.document.open();
    w.document.write(html);
    w.document.close();
    w.focus();
    setTimeout(function () {
        try {
            w.print();
        } catch (e) {
            alert("Druckdialog fehlgeschlagen: " + e);
        }
    }, 300);
}

function isBrowserPrintMode() {
    const c = ticketConnection || "";
    return c === "browser" || c === "client";
}

async function printStationOrderBon(orderId, ev) {
    if (ev) {
        ev.preventDefault();
        ev.stopPropagation();
    }
    if (actionBusy) return;
    if (!orderId) return;
    if (!ticketPrinterReady) {
        alert("Kein Drucker für diese Station konfiguriert (Admin → Einstellungen).");
        return;
    }
    actionBusy = true;
    setActionBusy(true, "Bon wird vorbereitet...");
    try {
        if (isBrowserPrintMode()) {
            const tres = await fetchWithTimeout(
                API + "/station/" + STATION_ID + "/orders/" + orderId + "/ticket",
                { cache: "no-store" },
                10000
            ).catch(() => null);
            if (!tres || !tres.ok) throw new Error("Ticket vom Server nicht geladen");
            const tdata = await tres.json();
            if (!tdata.ticket) throw new Error("Kein Bon-Inhalt");
            openBrowserTicketPrint(tdata.ticket);
            printedOrderIds.add(Number(orderId));
        } else {
            const res = await fetchWithTimeout(
                API + "/station/" + STATION_ID + "/orders/" + orderId + "/print",
                { method: "POST" },
                10000
            ).catch(() => null);
            if (!res) throw new Error("Verbindung zum Server");
            const data = await res.json().catch(() => ({}));
            if (data.client_print && data.ticket) {
                openBrowserTicketPrint(data.ticket);
            } else if (!res.ok || !data.ok) {
                throw new Error(data.error || "Druck fehlgeschlagen");
            }
            printedOrderIds.add(Number(orderId));
        }
    } catch (err) {
        alert(err && err.message ? err.message : "Druck fehlgeschlagen");
    }
    actionBusy = false;
    setActionBusy(false);
}

async function reprintKitchenOrderBon() {
    if (!kitchenModalSlot) return;
    await printStationOrderBon(kitchenModalSlot.order_id);
}

/* ============================================================
LOAD
============================================================ */
async function load() {
    if (mode !== "display") return;
    const res = await fetch(kitchenDisplayUrl());
    const data = await res.json();
    ticketAutoprint = !!data.ticket_autoprint;
    ticketPrinterReady = !!data.ticket_printer_ready;
    ticketConnection = data.ticket_connection || "cups";

    if (window.GastroStationAlerts && data.orders) {
        GastroStationAlerts.process(data.orders, STATION_ID);
    }

    // Autodruck im Browser nur als Fallback (Dialog). CUPS/Netzwerk: Host druckt still.
    if (ticketAutoprint && ticketPrinterReady && isBrowserPrintMode() && Array.isArray(data.orders)) {
        for (const o of data.orders) {
            const oid = Number(o.order_id);
            if (!oid || printedOrderIds.has(oid)) continue;
            if (o.status && o.status !== "new") continue;
            printedOrderIds.add(oid);
            printStationOrderBon(oid).catch(() => {});
        }
    }

    const grid = document.getElementById("grid");
    const warning = document.getElementById("warning");

    grid.innerHTML = "";

    updateWarning(data.waiting);

    // Manual-Bon: sinnvoll auf der Kachel – wer den Zettel nimmt, tippt Bon und bereitet zu.
    const showTilePrint = ticketPrinterReady && !ticketAutoprint;

    data.slots.forEach(slot => {

        const div = document.createElement("div");
        div.classList.add("tile");

        if (!slot) {
            grid.appendChild(div);
            return;
        }

        div.classList.add(slot.status);

        const items = slot.items || [];
        const longOrder = items.length > KITCHEN_TILE_MAX_ITEM_ROWS;
        const preview = longOrder ? items.slice(0, KITCHEN_TILE_MAX_ITEM_ROWS) : items;
        const moreCount = longOrder ? items.length - KITCHEN_TILE_MAX_ITEM_ROWS : 0;

        let html = "";

        html += "<div class='tile-header'>" + slot.table_name + "</div>";
        html += "<div class='waiter'>" + slot.waiter_name + "</div>";
        html += "<div class='order-id'>#" + slot.order_number + "</div>";

        html += "<div class='table tile-table-preview'>";
        html += "<div class='row header-row'>";
        html += "<div>Artikel</div><div>Preis</div><div>Summe</div>";
        html += "</div>";

        preview.forEach(i => {
            html += "<div class='row'>";
            html += "<div>" + i.quantity_open + "x " + i.name + "</div>";
            html += "<div>" + formatPrice(i.unit_price) + "</div>";
            html += "<div>" + formatPrice(i.line_total) + "</div>";
            html += "</div>";
        });

        if (moreCount > 0) {
            html += "<div class='row row-more'>+" + moreCount + " weitere Artikel · Tippen für alle Zeilen</div>";
        }

        html += "</div>";

        /* ====================================================
        TOTAL + STATUS BLOCK
        ==================================================== */
        html += "<div class='total-block'>";
        html += "<div class='line'></div>";
        html += "<div class='total'>Gesamt: " + formatPrice(slot.order_total) + "</div>";
        html += "<div class='line'></div>";
        html += "<div class='status-text " + getStatusClass(slot.status) + "'>" +
                getStatusText(slot.status) +
                "</div>";
        html += "</div>";

        if (showTilePrint) {
            html += "<button type='button' class='tile-print-btn'>Bon</button>";
        }

        div.innerHTML = html;

        const printBtn = div.querySelector(".tile-print-btn");
        if (printBtn) {
            printBtn.onclick = (ev) => printStationOrderBon(slot.order_id, ev);
        }

        div.onclick = async () => {
            openKitchenOrderModal(slot);
        };

        grid.appendChild(div);
    });
}

/* ============================================================
NAV
============================================================ */
function setMode(next) {
    mode = next;
    document.getElementById("modeDisplay").style.display = next === "display" ? "block" : "none";
    document.getElementById("modeOrder").style.display = next === "order" ? "flex" : "none";
    document.getElementById("modeCashier").style.display = next === "cashier" ? "block" : "none";
    if (next === "display") {
        load();
    } else if (next === "order") {
        loadStationProducts();
    } else if (next === "cashier") {
        loadCashierOrders();
    }
}

function updateWarning(waiting) {
    const warning = document.getElementById("warning");
    if (!warning) return;
    if (waiting > 0) {
        warning.innerText = "⚠ " + waiting + " Bestellungen warten";
        warning.classList.add("warning-blink");
    } else {
        warning.innerText = "";
        warning.classList.remove("warning-blink");
    }
}

async function refreshQueueWarningOnly() {
    try {
        const res = await fetch(kitchenDisplayUrl());
        const data = await res.json();
        updateWarning(data.waiting || 0);
        if (window.GastroStationAlerts && data.orders) {
            GastroStationAlerts.process(data.orders, STATION_ID);
        }
    } catch (_) {
        // Keep last shown warning state on transient network errors.
    }
}

function syncHeaderStatusFromBadge() {
    const statusEl = document.getElementById("headerSystemStatus");
    if (!statusEl) return;
    const badge = document.getElementById("gastro-status");
    if (!badge) {
        statusEl.innerText = "Status: -";
        return;
    }
    statusEl.innerText = "Status: " + badge.textContent;
}

function formatShortPrice(v) {
    return Number(v).toFixed(2).replace(".", ",") + " €";
}

async function loadStationProducts() {
    const res = await fetch(API + "/station/" + STATION_ID + "/products");
    stationProducts = await res.json();
    const map = {};
    stationProducts.forEach(p => { map[p.category_id] = p.category_name; });
    stationCategories = Object.keys(map).map(id => ({ id: Number(id), name: map[id] }));
    if (!activeStationCategory && stationCategories.length) {
        activeStationCategory = stationCategories[0].id;
    }
    renderStationCategories();
    renderStationProducts();
    renderStationCart();
}

function renderStationCategories() {
    const catDiv = document.getElementById("stationCategories");
    if (!catDiv) return;
    catDiv.innerHTML = "";
    stationCategories.forEach(c => {
        const btn = document.createElement("div");
        btn.className = "category" + (c.id === activeStationCategory ? " active" : "");
        btn.innerText = c.name;
        btn.onclick = () => {
            activeStationCategory = c.id;
            renderStationCategories();
            renderStationProducts();
        };
        catDiv.appendChild(btn);
    });
}

function renderStationProducts() {
    const prodDiv = document.getElementById("stationProducts");
    prodDiv.innerHTML = "";
    const items = stationProducts.filter(p => Number(p.category_id) === Number(activeStationCategory));
    if (!items.length && stationProducts.length) {
        // Fallback: if category IDs come in unexpected format, show all instead of blank.
        items.push(...stationProducts);
    }
    if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "product";
        empty.innerHTML = "<b>Keine Produkte gefunden</b><div class='price'>Bitte Kategorien im Admin prüfen</div>";
        prodDiv.appendChild(empty);
        return;
    }
    items.forEach(p => {
            const tile = document.createElement("div");
            tile.className = "product";
            const line = stationCart.find(c => c.product_id === p.id);
            const qty = line ? line.quantity : 0;
            tile.innerHTML =
                typeof productTileHtml === "function"
                    ? productTileHtml(p, formatShortPrice(p.price), qty)
                    : `<b>${p.name}</b><br>${formatShortPrice(p.price)}`;
            if (typeof bindProductTile === "function") {
                bindProductTile(tile, p, () => addStationItem(p.id), removeStationItem);
            } else {
                tile.onclick = () => addStationItem(p.id);
            }
            prodDiv.appendChild(tile);
        });
}

function addStationItem(productId) {
    const product = stationProducts.find(p => p.id === productId);
    if (!product) return;
    const existing = stationCart.find(c => c.product_id === productId);
    if (existing) {
        existing.quantity += 1;
    } else {
        stationCart.push({
            product_id: product.id,
            name: product.name,
            price: product.price,
            quantity: 1,
        });
    }
    renderStationCart();
}

function removeStationItem(productId) {
    const existing = stationCart.find(c => c.product_id === productId);
    if (!existing) return;
    existing.quantity -= 1;
    if (existing.quantity <= 0) {
        stationCart = stationCart.filter(c => c.product_id !== productId);
    }
    renderStationCart();
}

function renderStationCart() {
    const div = document.getElementById("stationCart");
    const totalEl = document.getElementById("stationTotal");
    div.innerHTML = "<h3>Kassenzettel</h3>";
    div.innerHTML += `<div class="station-cart-header"><div>Artikel</div><div>Anz.</div><div>Summe</div><div></div></div>`;
    let total = 0;
    stationCart.forEach(c => {
        total += c.quantity * c.price;
        div.innerHTML += `
            <div class="cart-row">
                <span>${c.quantity}x ${c.name}</span>
                <span>${formatShortPrice(c.quantity * c.price)}</span>
                <span class="minus" onclick="removeStationItem(${c.product_id})">-</span>
            </div>
        `;
    });
    if (totalEl) totalEl.innerText = "Gesamt: " + formatShortPrice(total);
    renderStationProducts();
}

function clearStationCart() {
    stationCart = [];
    renderStationCart();
}

async function submitStationOrder() {
    if (actionBusy) return;
    if (!stationCart.length) {
        alert("Warenkorb leer");
        return;
    }
    actionBusy = true;
    setActionBusy(true, "Bestellung wird gesendet...");
    const res = await fetchWithTimeout(API + "/station/" + STATION_ID + "/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            items: stationCart.map(c => ({ product_id: c.product_id, quantity: c.quantity }))
        })
    }, 12000).catch(() => null);
    actionBusy = false;
    setActionBusy(false);
    if (!res) {
        alert("Keine Verbindung. Bitte erneut senden.");
        return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Fehler");
        return;
    }
    alert("Bestellung aufgenommen (#" + data.order_id + ")");
    stationCart = [];
    renderStationCart();
    setMode("display");
}

function openTabsOverviewFromStation() {
    localStorage.setItem("tabs_overview_ctx", JSON.stringify({
        return_to: "kitchen.html",
        role: "station",
        station_id: STATION_ID,
        user_id: null
    }));
    window.location.href = "tabs_overview.html";
}

function openStationCashierOrder(orderId, orderNumber) {
    localStorage.setItem("order_manage_ctx", JSON.stringify({
        mode: "station_cashier_order",
        station_id: STATION_ID,
        order_id: Number(orderId || 0),
        order_number: Number(orderNumber || 0)
    }));
    window.location.href = "order_manage.html";
}

async function loadCashierOrders() {
    const res = await fetch(API + "/station/" + STATION_ID + "/orders/open");
    const orders = await res.json();
    const div = document.getElementById("cashierOrders");
    div.innerHTML = "";
    if (!orders.length) {
        div.innerHTML = "<div>Keine offenen Orders.</div>";
        return;
    }
    orders.forEach(o => {
        const card = document.createElement("div");
        card.className = "cashier-card";
        let html = `<div><b>#${o.order_number}</b> – ${o.table_name}</div>`;
        o.items.forEach(i => {
            html += `<div class="cashier-row"><span>${i.quantity_open}x ${i.name}</span><span>${formatShortPrice(i.quantity_open * i.price)}</span></div>`;
        });
        html += `<div><b>Offen: ${formatShortPrice(o.total_open)}</b></div>`;
        html += `<div class="cashier-actions">
            <button onclick="openStationCashierOrder(${o.order_id}, ${o.order_number})">Öffnen</button>
        </div>`;
        card.innerHTML = html;
        div.appendChild(card);
    });
}

async function redirectIfTerminalMode() {
    try {
        const res = await fetch(API + "/features", { cache: "no-store" });
        const data = await res.json();
        if (data && data.single_terminal_mode) {
            window.location.href = "terminal.html";
        }
    } catch (_) {}
}

setInterval(() => {
    if (mode === "display") load();
    if (mode === "cashier") loadCashierOrders();
    if (mode !== "display") refreshQueueWarningOnly();
    syncHeaderStatusFromBadge();
}, 3000);
redirectIfTerminalMode();
applyKitchenSlotsLayout();
setMode("display");
