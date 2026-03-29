const API = "https://api.mpbin.de";

const userId = localStorage.getItem("user_id");
const tableId = localStorage.getItem("table_id");

const userName = localStorage.getItem("user_name");
const tableName = localStorage.getItem("table_name");

document.getElementById("table").innerText = "Tisch: " + tableName;
document.getElementById("user").innerText = userName;

let cart = [];
let products = [];
let categories = [];
let activeCategory = null;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

async function init() {
    const res = await fetch(API + "/products");
    products = await res.json();

    const map = {};
    products.forEach(p => {
        map[p.category_id] = p.category_name;
    });

    categories = Object.keys(map).map(id => ({
        id: parseInt(id),
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

    const res = await fetch(API + "/orders", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            table_id: tableId,
            waiter_id: userId
        })
    });

    const order = await res.json();

    for (const item of cart) {
        await fetch(API + "/orders/" + order.order_id + "/items", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
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
    window.location.href = "tables.html";
}

function cancel() {
    cart = [];
    renderCart();
    window.location.href = "tables.html";
}

init();
