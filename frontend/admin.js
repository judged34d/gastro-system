const API = "http://192.168.0.165:8000";
const ADMIN_PASSWORD = "Passwort";

let categories = [];
let products = [];
let users = [];
let tables = [];
let assignments = [];

/* ============================================================
FORMAT
============================================================ */
function formatPrice(v) {
    return parseFloat(v).toFixed(2).replace(".", ",");
}

/* ============================================================
LOGIN
============================================================ */
function checkLogin() {
    const input = document.getElementById("adminPass").value;

    if (input === ADMIN_PASSWORD) {
        document.getElementById("loginOverlay").style.display = "none";
        document.getElementById("adminContent").style.display = "block";
        load();
    } else {
        document.getElementById("loginError").innerText = "Falsches Passwort";
    }
}

/* ============================================================
LOAD
============================================================ */
async function load() {
    categories = await fetch(API + "/admin/categories").then(r=>r.json());
    products = await fetch(API + "/admin/products").then(r=>r.json());

    const u = await fetch(API + "/admin/users").then(r=>r.json());
    users = u.users;
    tables = u.tables;
    assignments = u.assignments;

    renderCategories();
    renderProducts();
    renderTables();
    renderUsers();
}

/* ============================================================
KATEGORIEN
============================================================ */
function renderCategories() {
    const tbody = document.getElementById("categories");
    tbody.innerHTML = "";

    categories.forEach(c => {
        tbody.innerHTML += `
            <tr>
                <td>${c.id}</td>
                <td>${c.name}</td>
                <td>
                    <button class="deleteBtn" onclick="deleteCategory(${c.id})">Löschen</button>
                </td>
            </tr>
        `;
    });
}

async function addCategory() {
    const name = document.getElementById("cat_name").value;

    if (!name) return alert("Name fehlt");

    await fetch(API + "/admin/categories", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({name})
    });

    load();
}

async function deleteCategory(id) {
    await fetch(API + "/admin/categories/delete", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({id})
    });

    load();
}

/* ============================================================
PRODUKTE
============================================================ */
function renderProducts() {
    const tbody = document.getElementById("products");
    tbody.innerHTML = "";

    products.forEach(p => {

        let options = "";

        categories.forEach(c => {
            options += `
                <option value="${c.id}" ${c.id === p.category_id ? "selected" : ""}>
                    ${c.name}
                </option>
            `;
        });

        tbody.innerHTML += `
            <tr>
                <td>${p.id}</td>
                <td><input id="name_${p.id}" value="${p.name}"></td>
                <td><input id="price_${p.id}" value="${formatPrice(p.price)}"></td>
                <td><select id="cat_${p.id}">${options}</select></td>
                <td>
                    <button onclick="saveProduct(${p.id})">Speichern</button>
                    <button class="deleteBtn" onclick="deleteProduct(${p.id})">Löschen</button>
                </td>
            </tr>
        `;
    });
}

async function addProduct() {
    let price = document.getElementById("prod_price").value.replace(",", ".");
    const name = document.getElementById("prod_name").value;
    const category_id = parseInt(document.getElementById("prod_cat").value);

    if (!name || !price || !category_id) return alert("Alle Felder ausfüllen");

    await fetch(API + "/admin/products", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            name,
            price: parseFloat(price),
            category_id
        })
    });

    load();
}

async function saveProduct(id) {
    let price = document.getElementById("price_" + id).value.replace(",", ".");
    const name = document.getElementById("name_" + id).value;
    const category_id = parseInt(document.getElementById("cat_" + id).value);

    await fetch(API + "/admin/products/update", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            id,
            name,
            price: parseFloat(price),
            category_id
        })
    });

    load();
}

async function deleteProduct(id) {
    await fetch(API + "/admin/products/delete", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({id})
    });

    load();
}

/* ============================================================
TISCHE
============================================================ */
function renderTables() {
    const tbody = document.getElementById("tables");
    tbody.innerHTML = "";

    tables.forEach(t => {
        tbody.innerHTML += `
            <tr>
                <td>${t.id}</td>
                <td>${t.name}</td>
                <td><button class="deleteBtn" onclick="deleteTable(${t.id})">Löschen</button></td>
            </tr>
        `;
    });
}

async function addTable() {
    const name = document.getElementById("table_name").value;

    if (!name) return alert("Tischname fehlt");

    await fetch(API + "/admin/tables", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({name})
    });

    load();
}

async function deleteTable(id) {
    await fetch(API + "/admin/tables/delete", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({id})
    });

    load();
}

/* ============================================================
BEDIENUNGEN
============================================================ */
function renderUsers() {
    const div = document.getElementById("users");
    div.innerHTML = "";

    users.forEach(u => {

        let assigned = assignments
            .filter(a => a.waiter_id === u.id)
            .map(a => a.table_id);

        let tableGrid = "";

        tables.forEach(t => {
            const active = assigned.includes(t.id);

            tableGrid += `
                <div class="tableBox ${active ? "active" : ""}"
                    onclick="toggleTable(${u.id}, ${t.id})">
                    ${t.name}
                </div>
            `;
        });

        div.innerHTML += `
            <div class="userCard">
                <div class="userHeader">
                    ${u.name}
                    <button class="deleteBtn" onclick="deleteUser(${u.id})">Löschen</button>
                </div>
                <div class="tableGrid">
                    ${tableGrid}
                </div>
            </div>
        `;
    });
}

async function addUser() {
    const name = document.getElementById("user_name").value;
    const pin = document.getElementById("user_pin").value;

    if (!name || !pin) return alert("Name + PIN erforderlich");

    await fetch(API + "/admin/users", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({name, pin})
    });

    load();
}

async function deleteUser(id) {
    await fetch(API + "/admin/users/delete", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({id})
    });

    load();
}

async function toggleTable(user_id, table_id) {
    let current = assignments
        .filter(a => a.waiter_id === user_id)
        .map(a => a.table_id);

    if (current.includes(table_id)) {
        current = current.filter(t => t !== table_id);
    } else {
        current.push(table_id);
    }

    await fetch(API + "/admin/users/assign", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            user_id,
            table_ids: current
        })
    });

    load();
}

/* ============================================================
START
============================================================ */
load();
