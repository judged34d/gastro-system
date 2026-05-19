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

let guestMode = false;
let tableId = null;
let userId = null;
let tableName = "";
let userName = "";

let cart = [];
let products = [];
let categories = [];
let activeCategory = null;
const ORDER_OUTBOX_KEY = "gastro_order_outbox_v1";
let submitInProgress = false;
let flushInProgress = false;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

async function bootstrap() {
    const params = new URLSearchParams(window.location.search);
    const guestTableParam = params.get("table");

    if (guestTableParam) {
        guestMode = true;
        const r = await fetch(API + "/public/table/" + encodeURIComponent(guestTableParam), { cache: "no-store" });
        if (!r.ok) {
            document.getElementById("table").innerText = "Tisch";
            document.getElementById("user").innerText = "";
            alert("Tisch nicht gefunden oder kein aktives Event.");
            return;
        }
        const t = await r.json();
        tableId = String(t.id);
        tableName = t.name;
        document.getElementById("table").innerText = "Tisch: " + tableName;
        document.getElementById("user").innerText = "Gast (QR-Code)";
        const back = document.querySelector(".back-btn");
        if (back) back.style.display = "none";
    } else {
        userId = localStorage.getItem("user_id");
        tableId = localStorage.getItem("table_id");
        userName = localStorage.getItem("user_name");
        tableName = localStorage.getItem("table_name");
        if (!userId || !tableId) {
            alert("Bitte zuerst anmelden und einen Tisch wählen.");
            window.location.href = "login.html";
            return;
        }
        document.getElementById("table").innerText = "Tisch: " + tableName;
        document.getElementById("user").innerText = userName;
    }

    await loadMenu();
    renderOutboxHint();
    updateConnectionBadge();
    await flushOutbox();
}

async function loadMenu() {
    const res = await fetch(API + "/products", { cache: "no-store" });
    products = await res.json();

    const map = {};
    products.forEach(p => {
        const mid = p.menu_category_id != null ? p.menu_category_id : p.category_id;
        const mname = p.menu_category_name != null ? p.menu_category_name : p.category_name;
        map[mid] = mname;
    });

    categories = Object.keys(map).map(id => ({
        id: parseInt(id, 10),
        name: map[id]
    }));

    if (categories.length > 0) {
        activeCategory = categories[0].id;
    }

    renderCategories();
    renderProducts();
}

function renderCategories() {
    const div = document.getElementById("categories");
    div.innerHTML = "";

    categories.forEach(c => {
        const btn = document.createElement("div");
        btn.classList.add("category");
        btn.innerText = c.name;

        btn.onclick = () => {
            activeCategory = c.id;
            renderProducts();
        };

        div.appendChild(btn);
    });
}

function renderProducts() {
    const div = document.getElementById("products");
    div.innerHTML = "";

    products
        .filter(p => {
            const mid = p.menu_category_id != null ? p.menu_category_id : p.category_id;
            return Number(mid) === Number(activeCategory);
        })
        .forEach(p => {
            const el = document.createElement("div");
            el.classList.add("product");

            const line = cart.find(i => i.id === p.id);
            const qty = line ? line.qty : 0;
            el.innerHTML =
                typeof productTileHtml === "function"
                    ? productTileHtml(p, formatPrice(p.price), qty)
                    : `<b>${p.name}</b><br>${formatPrice(p.price)}`;

            if (typeof bindProductTile === "function") {
                bindProductTile(el, p.id, () => addToCart(p), removeFromCart);
            } else {
                el.onclick = () => addToCart(p);
            }

            div.appendChild(el);
        });
}

function addToCart(product) {
    const existing = cart.find(i => i.id === product.id);

    if (existing) {
        existing.qty++;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            price: product.price,
            qty: 1
        });
    }

    renderCart();
}

function removeFromCart(productId) {
    const item = cart.find(i => i.id === productId);
    if (!item) return;

    item.qty--;

    if (item.qty <= 0) {
        cart = cart.filter(i => i.id !== productId);
    }

    renderCart();
}

function renderCart() {
    const div = document.getElementById("cart");
    const totalDiv = document.getElementById("total");

    div.innerHTML = "";

    let total = 0;

    cart.forEach(i => {
        total += i.qty * i.price;

        div.innerHTML += `
            <div class="cart-row">
                <span>${i.qty}x ${i.name}</span>
                <span>${formatPrice(i.qty * i.price)}</span>
                <span class="minus" onclick="removeFromCart(${i.id})">-</span>
            </div>
        `;
    });

    totalDiv.innerText = "Gesamt: " + formatPrice(total);
    renderProducts();
}

async function sendOrder() {
    if (submitInProgress) return;
    if (cart.length === 0) {
        alert("Warenkorb leer");
        return;
    }

    const payload = guestMode
        ? { table_id: parseInt(tableId, 10), waiter_id: null, source: "guest_qr" }
        : { table_id: parseInt(tableId, 10), waiter_id: parseInt(userId, 10) };
    payload.items = cart.map(item => ({
        product_id: item.id,
        quantity: item.qty
    }));

    submitInProgress = true;
    updateConnectionBadge();
    setUiBusy(true, "Bestellung wird gesendet...");
    const result = await sendOrderPayload(payload);
    submitInProgress = false;
    setUiBusy(false);
    updateConnectionBadge();

    if (result.ok) {
        alert("Bestellung eingegangen (#" + result.orderId + ")");
        cart = [];
        renderCart();
        return;
    }

    if (result.queued) {
        queueOrder(payload);
        alert("Keine stabile Verbindung. Bestellung lokal gespeichert und wird automatisch gesendet.");
        cart = [];
        renderCart();
        return;
    }

    alert(result.message || "Bestellung fehlgeschlagen");
}

async function sendOrderPayload(payload) {
    try {
        const res = await fetchWithTimeout(API + "/orders/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        }, 12000);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            return { ok: false, queued: false, message: data.error || "Bestellung fehlgeschlagen" };
        }
        return { ok: true, orderId: data.order_id };
    } catch (_) {
        return { ok: false, queued: true };
    }
}

function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const merged = Object.assign({}, options || {}, { signal: controller.signal });
    return fetch(url, merged).finally(() => clearTimeout(timer));
}

function getOutbox() {
    try {
        const raw = localStorage.getItem(ORDER_OUTBOX_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
        return [];
    }
}

function saveOutbox(outbox) {
    localStorage.setItem(ORDER_OUTBOX_KEY, JSON.stringify(outbox));
    renderOutboxHint();
    updateConnectionBadge();
}

function queueOrder(payload) {
    const outbox = getOutbox();
    outbox.push({
        id: Date.now() + "-" + Math.random().toString(36).slice(2, 8),
        payload: payload,
        created_at: new Date().toISOString()
    });
    saveOutbox(outbox);
}

async function flushOutbox() {
    const outbox = getOutbox();
    if (!outbox.length || !navigator.onLine) return;
    if (flushInProgress) return;
    flushInProgress = true;
    updateConnectionBadge();

    const remaining = [];
    for (const item of outbox) {
        const result = await sendOrderPayload(item.payload);
        if (!result.ok) {
            remaining.push(item);
        }
    }
    saveOutbox(remaining);
    flushInProgress = false;
    updateConnectionBadge();
}

function renderOutboxHint() {
    let el = document.getElementById("sendState");
    if (!el) {
        el = document.createElement("div");
        el.id = "sendState";
        el.style.fontSize = "13px";
        el.style.color = "#f1c40f";
        el.style.marginBottom = "8px";
        const btnWrap = document.querySelector(".buttons");
        if (btnWrap && btnWrap.parentNode) {
            btnWrap.parentNode.insertBefore(el, btnWrap);
        }
    }
    const count = getOutbox().length;
    el.innerText = count > 0
        ? ("Offline-Warteschlange: " + count + " Bestellung(en), wird automatisch gesendet.")
        : "";
}

function updateConnectionBadge() {
    const badge = document.getElementById("orderStatusBadge");
    if (!badge) return;
    const queueCount = getOutbox().length;
    badge.className = "order-status-badge";

    if (submitInProgress || flushInProgress) {
        badge.classList.add("order-status-sending");
        badge.innerText = queueCount > 0 ? ("Sendet... (" + queueCount + " wartend)") : "Sendet...";
        return;
    }

    if (!navigator.onLine) {
        badge.classList.add("order-status-offline");
        badge.innerText = queueCount > 0 ? ("Offline (" + queueCount + " wartend)") : "Offline";
        return;
    }

    if (queueCount > 0) {
        badge.classList.add("order-status-sending");
        badge.innerText = "Online (" + queueCount + " wartend)";
        return;
    }

    badge.classList.add("order-status-online");
    badge.innerText = "Online";
}

function setUiBusy(busy, text) {
    let overlay = document.getElementById("orderBusyOverlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "orderBusyOverlay";
        overlay.style.position = "fixed";
        overlay.style.inset = "0";
        overlay.style.zIndex = "1200";
        overlay.style.display = "none";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.background = "rgba(0,0,0,0.6)";
        overlay.style.fontSize = "20px";
        overlay.style.fontWeight = "bold";
        overlay.style.textAlign = "center";
        overlay.style.padding = "20px";
        document.body.appendChild(overlay);
    }
    overlay.innerText = text || "Bitte warten...";
    overlay.style.display = busy ? "flex" : "none";
}

function goBack() {
    cart = [];
    renderCart();
    if (guestMode) {
        window.location.href = "order.html?table=" + encodeURIComponent(tableId);
    } else {
        window.location.href = "tables.html";
    }
}

function cancel() {
    cart = [];
    renderCart();
    if (guestMode) {
        window.location.href = "order.html?table=" + encodeURIComponent(tableId);
    } else {
        window.location.href = "tables.html";
    }
}

bootstrap().catch(function () {
    alert("Menü konnte nicht geladen werden.");
});
window.addEventListener("online", () => {
    updateConnectionBadge();
    flushOutbox();
});
window.addEventListener("offline", () => {
    updateConnectionBadge();
});
setInterval(() => {
    flushOutbox();
    updateConnectionBadge();
}, 10000);
