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

const stationName = localStorage.getItem("user_name");
const stationEl = document.getElementById("stationName");
if (stationEl) stationEl.innerText = stationName || "Terminal";

let STATION_ID = Number(localStorage.getItem("user_id") || 1);
let mode = "home";
let stationProducts = [];
let stationCart = [];
let stationCategories = [];
let activeStationCategory = null;
let actionBusy = false;

function formatShortPrice(v) {
    return Number(v).toFixed(2).replace(".", ",") + " €";
}

function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const merged = Object.assign({}, options || {}, { signal: controller.signal });
    return fetch(url, merged).finally(() => clearTimeout(timer));
}

function setActionBusy(busy, text) {
    let overlay = document.getElementById("terminalBusyOverlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "terminalBusyOverlay";
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

function setMode(next) {
    mode = next;
    document.getElementById("modeHome").style.display = next === "home" ? "block" : "none";
    document.getElementById("modeOrder").style.display = next === "order" ? "block" : "none";
    document.getElementById("modeCashier").style.display = next === "cashier" ? "block" : "none";
    if (next === "order") {
        loadStationProducts();
    }
    if (next === "cashier") {
        loadCashierOrders();
    }
}

async function ensureTerminalMode() {
    try {
        const res = await fetch(API + "/features", { cache: "no-store" });
        const data = await res.json();
        if (!data || !data.single_terminal_mode) {
            window.location.href = "kitchen.html";
        }
    } catch (_) {}
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
    let items = stationProducts.filter(p => Number(p.category_id) === Number(activeStationCategory));
    if (!items.length && stationProducts.length) {
        items = stationProducts.slice();
    }
    if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "product";
        empty.innerHTML = "<b>Keine Produkte</b>";
        prodDiv.appendChild(empty);
        return;
    }
    items.forEach(p => {
        const tile = document.createElement("div");
        tile.className = "product";
        const iconHtml = typeof productIconHtml === "function" ? productIconHtml(p) : "";
        tile.innerHTML = `${iconHtml}<b>${p.name}</b><br>${formatShortPrice(p.price)}`;
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
    div.innerHTML = "<h3>Warenkorb</h3>";
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

async function submitTerminalOrder() {
    if (actionBusy) return;
    if (!stationCart.length) {
        alert("Warenkorb leer");
        return;
    }
    actionBusy = true;
    setActionBusy(true, "Bestellung wird gespeichert...");
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
        alert(data.error || data.message || "Fehler");
        return;
    }
    stationCart = [];
    renderStationCart();
    localStorage.setItem("order_manage_ctx", JSON.stringify({
        mode: "terminal_cashier_order",
        station_id: STATION_ID,
        order_id: Number(data.order_id || 0),
        order_number: Number(data.order_number || data.order_id || 0)
    }));
    window.location.href = "order_manage.html";
}

function openTabsOverview() {
    localStorage.setItem("tabs_overview_ctx", JSON.stringify({
        return_to: "terminal.html",
        role: "station",
        station_id: STATION_ID,
        user_id: null
    }));
    window.location.href = "tabs_overview.html";
}

function openTerminalCashierOrder(orderId, orderNumber) {
    localStorage.setItem("order_manage_ctx", JSON.stringify({
        mode: "terminal_cashier_order",
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
        div.innerHTML = "<div class='terminal-empty'>Keine offenen Bestellungen.</div>";
        return;
    }
    orders.forEach(o => {
        const card = document.createElement("div");
        card.className = "cashier-card";
        let html = `<div><b>#${o.order_number}</b> – ${o.table_name || "Theke"}</div>`;
        (o.items || []).forEach(i => {
            html += `<div class="cashier-row"><span>${i.quantity_open}x ${i.name}</span><span>${formatShortPrice(i.quantity_open * i.price)}</span></div>`;
        });
        html += `<div><b>Offen: ${formatShortPrice(o.total_open)}</b></div>`;
        html += `<div class="cashier-actions">
            <button type="button" onclick="openTerminalCashierOrder(${o.order_id}, ${o.order_number})">Kassieren</button>
        </div>`;
        card.innerHTML = html;
        div.appendChild(card);
    });
}

ensureTerminalMode();
setMode("home");

setInterval(() => {
    if (mode === "cashier") loadCashierOrders();
}, 5000);
