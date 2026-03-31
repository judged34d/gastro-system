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
const ADMIN_PASSWORD = "Passwort";

let categories = [];
let products = [];
let users = [];
let tables = [];
let assignments = [];
let stationCategories = [];
let events = [];
let activeEvent = null;
let tabs = [];

/* ============================================================
[0000] HELPERS
============================================================ */
function formatPrice(v) {
    return parseFloat(v).toFixed(2).replace(".", ",");
}

function formatDate(v) {
    if (!v) return "";
    // SQLite CURRENT_TIMESTAMP -> "YYYY-MM-DD HH:MM:SS"
    return String(v).replace("T", " ").replace(".000", "");
}

/* ============================================================
[0100] LOGIN
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
[0200] LOAD
============================================================ */
async function load() {
    const e = await fetch(API + "/admin/events").then(r => r.json());
    events = e.events || [];
    activeEvent = e.active_event || null;

    categories = await fetch(API + "/admin/categories").then(r => r.json());
    products = await fetch(API + "/admin/products").then(r => r.json());

    const u = await fetch(API + "/admin/users").then(r => r.json());
    users = u.users;
    tables = u.tables;
    assignments = u.assignments;
    stationCategories = u.station_categories;
    tabs = await fetch(API + "/admin/tabs").then(r => r.json());

    renderCategoryOptions();
    renderCategories();
    renderProducts();
    renderTables();
    renderUsers();
    renderEvents();
    renderTabs();
}

/* ============================================================
[0500] EVENTS + STATS
============================================================ */
function renderEvents() {
    const tbody = document.getElementById("events");
    const activeDiv = document.getElementById("activeEvent");
    const templateSelect = document.getElementById("event_template");
    const statsSelect = document.getElementById("stats_event");

    if (activeDiv) {
        activeDiv.innerText = activeEvent
            ? `Aktiv: #${activeEvent.id} – ${activeEvent.name}`
            : "Aktiv: (kein Event aktiv)";
    }

    if (templateSelect) {
        templateSelect.innerHTML = "<option value=''>Vorlage (optional)</option>";
        events.forEach(ev => {
            templateSelect.innerHTML += `<option value=\"${ev.id}\">#${ev.id} – ${ev.name}</option>`;
        });
    }
    if (statsSelect) {
        statsSelect.innerHTML = "";
        events.forEach(ev => {
            statsSelect.innerHTML += `<option value=\"${ev.id}\">#${ev.id} – ${ev.name}</option>`;
        });
        if (activeEvent && activeEvent.id) {
            statsSelect.value = String(activeEvent.id);
        }
    }

    if (!tbody) return;
    tbody.innerHTML = "";

    events.forEach(ev => {
        tbody.innerHTML += `
            <tr>
                <td>${ev.id}</td>
                <td>
                    <input id="event_name_${ev.id}" value="${ev.name.replace(/\"/g, "&quot;")}">
                    <button class="inlineBtn" onclick="saveEventName(${ev.id})">Speichern</button>
                </td>
                <td>${ev.status}</td>
                <td>${ev.billing_status || "-"}</td>
                <td>${formatDate(ev.starts_at)}</td>
                <td>${formatDate(ev.ends_at)}</td>
                <td><button class="inlineBtn" onclick="activateEvent(${ev.id})">Aktivieren</button></td>
                <td><button class="deleteBtn" onclick="closeEvent(${ev.id})">Beenden</button></td>
                <td><button class="inlineBtn" onclick="duplicateEvent(${ev.id})">Duplizieren</button></td>
            </tr>
        `;
    });
}

async function saveEventName(event_id) {
    const input = document.getElementById("event_name_" + event_id);
    const name = input ? input.value.trim() : "";
    if (!name) {
        alert("Name fehlt");
        return;
    }
    await fetch(API + "/admin/events/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id, name })
    });
    load();
}

async function duplicateEvent(source_event_id) {
    const suggested = events.find(e => e.id === source_event_id)?.name || "";
    const name = prompt("Name für das neue Event:", suggested ? (suggested + " (neu)") : "");
    if (name === null) return;
    await fetch(API + "/admin/events/duplicate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_event_id, name: name.trim() })
    });
    load();
}

async function createNewEvent() {
    const name = document.getElementById("event_name").value.trim();
    const template = document.getElementById("event_template").value;

    if (!name) {
        alert("Eventname fehlt");
        return;
    }

    const res = await fetch(API + "/admin/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name,
            template_event_id: template ? parseInt(template, 10) : null
        })
    });
    const created = await res.json();

    document.getElementById("event_name").value = "";
    if (created && created.event_id) {
        await activateEvent(created.event_id);
    } else {
        load();
    }
}

async function activateEvent(event_id) {
    await fetch(API + "/admin/events/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id })
    });
    load();
}

async function closeEvent(event_id) {
    const res = await fetch(API + "/admin/events/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id })
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || "Event kann nicht geschlossen werden");
        return;
    }
    load();
}

async function closeActiveEvent() {
    const res = await fetch(API + "/admin/events/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || "Event kann nicht geschlossen werden");
        return;
    }
    load();
}

function openStatsPageFromAdmin() {
    const sel = document.getElementById("stats_event");
    const eventId = sel && sel.value ? parseInt(sel.value, 10) : null;
    if (!eventId) {
        alert("Bitte Event wählen");
        return;
    }
    window.location.href = "admin_stats.html?event_id=" + eventId;
}

// Legacy compatibility for cached/older admin.html variants.
function openStatsPage() {
    openStatsPageFromAdmin();
}

// Legacy compatibility: old button often calls loadStats() in admin.html.
function loadStats() {
    const oldStatsDiv = document.getElementById("stats");
    if (oldStatsDiv) oldStatsDiv.innerHTML = "";
    openStatsPageFromAdmin();
}

function renderTabs() {
    const div = document.getElementById("tabsList");
    if (!div) return;
    if (!tabs.length) {
        div.innerHTML = "<div>Keine Deckel vorhanden.</div>";
        return;
    }
    let html = `<table><thead><tr><th>Name</th><th>Offen</th></tr></thead><tbody>`;
    tabs.forEach(t => {
        html += `<tr><td>${t.name}</td><td>${formatPrice(t.balance || 0)} €</td></tr>`;
    });
    html += `</tbody></table>`;
    div.innerHTML = html;
}

async function addTab() {
    const name = document.getElementById("tab_name").value.trim();
    if (!name) {
        alert("Deckelname fehlt");
        return;
    }
    await fetch(API + "/admin/tabs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });
    document.getElementById("tab_name").value = "";
    load();
}

/* ============================================================
[0300] CATEGORY SELECT FOR NEW PRODUCT
============================================================ */
function renderCategoryOptions() {
    const select = document.getElementById("prod_cat");
    if (!select) return;

    select.innerHTML = '<option value="">Kategorie wählen</option>';

    categories.forEach(c => {
        select.innerHTML += `
            <option value="${c.id}">${c.name}</option>
        `;
    });
}

/* ============================================================
[1000] KATEGORIEN
============================================================ */
function renderCategories() {
    const tbody = document.getElementById("categories");
    if (!tbody) return;

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
    const name = document.getElementById("cat_name").value.trim();

    if (!name) {
        alert("Name fehlt");
        return;
    }

    await fetch(API + "/admin/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });

    document.getElementById("cat_name").value = "";
    load();
}

async function deleteCategory(id) {
    await fetch(API + "/admin/categories/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
    });

    load();
}

/* ============================================================
[1100] PRODUKTE
============================================================ */
function renderProducts() {
    const tbody = document.getElementById("products");
    if (!tbody) return;

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
                <td>
                    <select id="cat_${p.id}">
                        ${options}
                    </select>
                </td>
                <td>
                    <button class="inlineBtn" onclick="saveProduct(${p.id})">Speichern</button>
                    <button class="deleteBtn" onclick="deleteProduct(${p.id})">Löschen</button>
                </td>
            </tr>
        `;
    });
}

async function addProduct() {
    const name = document.getElementById("prod_name").value.trim();
    let price = document.getElementById("prod_price").value.trim().replace(",", ".");
    const category_id = parseInt(document.getElementById("prod_cat").value, 10);

    if (!name || !price || !category_id) {
        alert("Alle Felder ausfüllen");
        return;
    }

    await fetch(API + "/admin/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name,
            price: parseFloat(price),
            category_id
        })
    });

    document.getElementById("prod_name").value = "";
    document.getElementById("prod_price").value = "";
    document.getElementById("prod_cat").value = "";
    load();
}

async function saveProduct(id) {
    const name = document.getElementById("name_" + id).value.trim();
    let price = document.getElementById("price_" + id).value.trim().replace(",", ".");
    const category_id = parseInt(document.getElementById("cat_" + id).value, 10);

    await fetch(API + "/admin/products/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
    });

    load();
}

/* ============================================================
[1200] TISCHE
============================================================ */
function renderTables() {
    const tbody = document.getElementById("tables");
    if (!tbody) return;

    tbody.innerHTML = "";

    tables.forEach(t => {
        tbody.innerHTML += `
            <tr>
                <td>${t.id}</td>
                <td>${t.name}</td>
                <td>
                    <button onclick="openTableCard(${t.id}, ${JSON.stringify(t.name)})">Tischkarte erstellen</button>
                    <button class="deleteBtn" onclick="deleteTable(${t.id})">Löschen</button>
                </td>
            </tr>
        `;
    });
}

async function addTable() {
    const name = document.getElementById("table_name").value.trim();

    if (!name) {
        alert("Tischname fehlt");
        return;
    }

    await fetch(API + "/admin/tables", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });

    document.getElementById("table_name").value = "";
    load();
}

async function deleteTable(id) {
    await fetch(API + "/admin/tables/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
    });

    load();
}

/* ============================================================
[1300] BEDIENUNGEN + STATIONEN
============================================================ */
function renderUsers() {
    const div = document.getElementById("users");
    if (!div) return;

    div.innerHTML = "";

    users.forEach(u => {
        if (u.role === "waiter") {
            renderWaiterCard(div, u);
        }

        if (u.role === "station") {
            renderStationCard(div, u);
        }
    });
}

function renderWaiterCard(container, user) {
    const assignedTableIds = assignments
        .filter(a => a.waiter_id === user.id)
        .map(a => a.table_id);

    let tableGrid = "";

    tables.forEach(t => {
        const active = assignedTableIds.includes(t.id);

        tableGrid += `
            <div class="tableBox ${active ? "active" : ""}" onclick="toggleTable(${user.id}, ${t.id})">
                ${t.name}
            </div>
        `;
    });

    container.innerHTML += `
        <div class="userCard">
            <div class="userHeader">
                <span>${user.name}</span>
                <button class="deleteBtn" onclick="deleteUser(${user.id})">Löschen</button>
            </div>
            <div class="tableGrid">
                ${tableGrid}
            </div>
        </div>
    `;
}

function renderStationCard(container, user) {
    const assignedCategoryIds = stationCategories
        .filter(sc => sc.station_id === user.id)
        .map(sc => sc.category_id);

    let categoryGrid = "";

    categories.forEach(c => {
        const active = assignedCategoryIds.includes(c.id);

        categoryGrid += `
            <div class="tableBox ${active ? "active" : ""}" onclick="toggleStationCategory(${user.id}, ${c.id})">
                ${c.name}
            </div>
        `;
    });

    container.innerHTML += `
        <div class="userCard">
            <div class="userHeader">
                <span>${user.name} (Theke)</span>
                <button class="deleteBtn" onclick="deleteUser(${user.id})">Löschen</button>
            </div>
            <div class="tableGrid">
                ${categoryGrid}
            </div>
        </div>
    `;
}

async function addUser() {
    const name = document.getElementById("user_name").value.trim();
    const pin = document.getElementById("user_pin").value.trim();

    if (!name || !pin) {
        alert("Name + PIN erforderlich");
        return;
    }

    await fetch(API + "/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name,
            pin,
            role: "waiter"
        })
    });

    document.getElementById("user_name").value = "";
    document.getElementById("user_pin").value = "";
    load();
}

async function addStation() {
    const name = document.getElementById("station_name").value.trim();
    const pin = document.getElementById("station_pin").value.trim();

    if (!name || !pin) {
        alert("Name + PIN erforderlich");
        return;
    }

    await fetch(API + "/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name,
            pin,
            role: "station"
        })
    });

    document.getElementById("station_name").value = "";
    document.getElementById("station_pin").value = "";
    load();
}

async function deleteUser(id) {
    await fetch(API + "/admin/users/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id,
            table_ids: current
        })
    });

    load();
}

async function toggleStationCategory(station_id, category_id) {
    let current = stationCategories
        .filter(sc => sc.station_id === station_id)
        .map(sc => sc.category_id);

    if (current.includes(category_id)) {
        current = current.filter(c => c !== category_id);
    } else {
        current.push(category_id);
    }

    await fetch(API + "/admin/station/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            station_id,
            category_ids: current
        })
    });

    load();
}

/* ============================================================
[1250] TISCHKARTE (QR + Druck)
============================================================ */
function openTableCard(id, name) {
    const orderUrl = new URL("order.html", window.location.href);
    orderUrl.searchParams.set("table", String(id));
    const href = orderUrl.href;
    document.getElementById("tableCardTitle").textContent = name;
    document.getElementById("tableCardUrl").textContent = href;
    const mount = document.getElementById("tableCardQr");
    mount.innerHTML = "";
    if (typeof QRCode !== "undefined") {
        new QRCode(mount, { text: href, width: 200, height: 200 });
    } else {
        mount.textContent = href;
    }
    const ov = document.getElementById("tableCardOverlay");
    ov.classList.add("is-open");
    ov.style.display = "flex";
    ov.setAttribute("aria-hidden", "false");
}

function closeTableCard() {
    const ov = document.getElementById("tableCardOverlay");
    ov.classList.remove("is-open");
    ov.style.display = "none";
    ov.setAttribute("aria-hidden", "true");
}

function doPrintTableCard() {
    document.body.classList.add("table-card-print");
    window.print();
    setTimeout(function () {
        document.body.classList.remove("table-card-print");
    }, 500);
}

/* ============================================================
[9000] START
============================================================ */
load();
