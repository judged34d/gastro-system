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
}

async function loadMenu() {
    const res = await fetch(API + "/products", { cache: "no-store" });
    products = await res.json();

    const map = {};
    products.forEach(p => {
        map[p.category_id] = p.category_name;
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
        .filter(p => p.category_id === activeCategory)
        .forEach(p => {
            const el = document.createElement("div");
            el.classList.add("product");

            el.innerHTML = `
                <b>${p.name}</b><br>
                ${formatPrice(p.price)}
            `;

            el.onclick = () => addToCart(p);

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
}

async function sendOrder() {
    if (cart.length === 0) {
        alert("Warenkorb leer");
        return;
    }

    const body = guestMode
        ? { table_id: parseInt(tableId, 10), waiter_id: null, source: "guest_qr" }
        : { table_id: parseInt(tableId, 10), waiter_id: parseInt(userId, 10) };

    const res = await fetch(API + "/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });

    const raw = await res.text();
    let order;
    try {
        order = JSON.parse(raw);
    } catch (_) {
        alert("Serverfehler");
        return;
    }

    if (!res.ok) {
        alert(order.error || "Bestellung fehlgeschlagen");
        return;
    }

    for (const item of cart) {
        await fetch(API + "/orders/" + order.order_id + "/items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                product_id: item.id,
                quantity: item.qty
            })
        });
    }

    alert("Bestellung gesendet");

    cart = [];
    renderCart();
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
