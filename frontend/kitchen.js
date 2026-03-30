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
let STATION_ID = localStorage.getItem("user_id") || 1;
let mode = "display";
let stationProducts = [];
let stationCart = [];
let stationCategories = [];
let activeStationCategory = null;

/** Max. Artikelzeilen in der Kachel; darüber Klick öffnet Detail-Modal */
const KITCHEN_TILE_MAX_ITEM_ROWS = 3;
let kitchenModalSlot = null;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

/* ============================================================
STATUS TEXT
============================================================ */
function getStatusText(status) {
    if (status === "new") return "Offen";
    if (status === "preparing") return "In Zubereitung";
    if (status === "ready") return "Bereit";
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

    modal.classList.add("is-open");
}

async function confirmKitchenModalStatus() {
    if (!kitchenModalSlot) return;
    const oid = kitchenModalSlot.order_id;
    await fetch(API + "/station/" + STATION_ID + "/orders/" + oid + "/status", {
        method: "POST"
    });
    closeKitchenOrderModal();
    load();
}

/* ============================================================
LOAD
============================================================ */
async function load() {
    if (mode !== "display") return;
    const res = await fetch(API + "/station/" + STATION_ID + "/display");
    const data = await res.json();

    const grid = document.getElementById("grid");
    const warning = document.getElementById("warning");

    grid.innerHTML = "";

    updateWarning(data.waiting);

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

        div.innerHTML = html;

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
        const res = await fetch(API + "/station/" + STATION_ID + "/display");
        const data = await res.json();
        updateWarning(data.waiting || 0);
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
            tile.innerHTML = `<b>${p.name}</b><br>${formatShortPrice(p.price)}`;
            tile.onclick = () => addStationItem(p.id);
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
}

function clearStationCart() {
    stationCart = [];
    renderStationCart();
}

async function submitStationOrder() {
    if (!stationCart.length) {
        alert("Warenkorb leer");
        return;
    }
    const res = await fetch(API + "/station/" + STATION_ID + "/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            items: stationCart.map(c => ({ product_id: c.product_id, quantity: c.quantity }))
        })
    });
    const data = await res.json();
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

setInterval(() => {
    if (mode === "display") load();
    if (mode === "cashier") loadCashierOrders();
    if (mode !== "display") refreshQueueWarningOnly();
    syncHeaderStatusFromBadge();
}, 3000);
setMode("display");
