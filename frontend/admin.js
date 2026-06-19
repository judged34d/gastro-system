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
let standardIcons = [];
let customIcons = [];

/* ============================================================
[0000] HELPERS
============================================================ */
function formatPrice(v) {
    return parseFloat(v).toFixed(2).replace(".", ",");
}

function parseMoneyInput(raw, allowEmpty = false) {
    if (allowEmpty) {
        const s = String(raw ?? "").trim();
        if (!s) return null;
    }
    const v = parseFloat(String(raw || "0").trim().replace(",", "."));
    if (!Number.isFinite(v) || v < 0) return allowEmpty ? null : 0;
    return v;
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
        sessionStorage.setItem("gastro_admin_ok", "1");
        load();
    } else {
        document.getElementById("loginError").innerText = "Falsches Passwort";
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const pw = document.getElementById("adminPass");
    if (pw) {
        pw.addEventListener("keydown", function (ev) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                checkLogin();
            }
        });
    }
});

/* ============================================================
[0200] LOAD
============================================================ */
async function load() {
    await loadIconCatalogs();

    const e = await fetch(API + "/admin/events").then(r => r.json());
    events = e.events || [];
    activeEvent = e.active_event || null;

    categories = await fetch(API + "/admin/categories").then(r => r.json());

    const u = await fetch(API + "/admin/users").then(r => r.json());
    users = u.users;
    tables = u.tables;
    assignments = u.assignments;
    stationCategories = u.station_categories;
    tabs = await fetch(API + "/admin/tabs").then(r => r.json());

    renderCategoryOptions();
    renderCategories();
    renderTables();
    renderUsers();
    renderEvents();
    renderTabs();
}

async function loadIconCatalogs() {
    const std = await fetch(API + "/icons/standard").then(r => r.json()).catch(() => ({}));
    standardIcons = std.icons || [];
    customIcons = await fetch(API + "/admin/icons").then(r => r.json()).catch(() => []);
    fillIconSelect("prod_icon_std", standardIcons.map(i => ({
        value: i.id,
        label: (i.emoji || "") + " " + i.label
    })));
    fillIconSelect("prod_icon_custom", customIcons.map(i => ({
        value: String(i.id),
        label: i.name
    })));
}

function fillIconSelect(id, options) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = options.map(o =>
        `<option value="${o.value}">${o.label}</option>`
    ).join("");
}

function onProductIconTypeChange(prefix) {
    const typeId = prefix === "prod" ? "prod_icon_type" : ("icon_type_" + prefix);
    const stdId = prefix === "prod" ? "prod_icon_std" : ("icon_std_" + prefix);
    const customId = prefix === "prod" ? "prod_icon_custom" : ("icon_custom_" + prefix);
    const t = document.getElementById(typeId);
    const std = document.getElementById(stdId);
    const cust = document.getElementById(customId);
    if (!t) return;
    const v = t.value;
    if (std) std.style.display = v === "standard" ? "inline-block" : "none";
    if (cust) cust.style.display = v === "custom" ? "inline-block" : "none";
}

function readIconFields(prefix) {
    const typeId = prefix === "prod" ? "prod_icon_type" : ("icon_type_" + prefix);
    const t = document.getElementById(typeId);
    const icon_type = t ? t.value : "none";
    let icon_ref = null;
    if (icon_type === "standard") {
        const el = document.getElementById(prefix === "prod" ? "prod_icon_std" : ("icon_std_" + prefix));
        icon_ref = el && el.value ? el.value : null;
    } else if (icon_type === "custom") {
        const el = document.getElementById(prefix === "prod" ? "prod_icon_custom" : ("icon_custom_" + prefix));
        icon_ref = el && el.value ? el.value : null;
    }
    return { icon_type, icon_ref };
}

function iconPickerCellHtml(p) {
    const t = p.icon_type || "none";
    const r = p.icon_ref || "";
    const stdOpts = standardIcons.map(i =>
        `<option value="${i.id}" ${t === "standard" && r === i.id ? "selected" : ""}>${i.emoji} ${i.label}</option>`
    ).join("");
    const custOpts = customIcons.map(i =>
        `<option value="${i.id}" ${t === "custom" && String(r) === String(i.id) ? "selected" : ""}>${i.name}</option>`
    ).join("");
    const stdDisp = t === "standard" ? "inline-block" : "none";
    const custDisp = t === "custom" ? "inline-block" : "none";
    return `
        <select id="icon_type_${p.id}" onchange="onProductIconTypeChange(${p.id})">
            <option value="none" ${t === "none" ? "selected" : ""}>–</option>
            <option value="standard" ${t === "standard" ? "selected" : ""}>Standard</option>
            <option value="custom" ${t === "custom" ? "selected" : ""}>Eigen</option>
        </select>
        <select id="icon_std_${p.id}" style="display:${stdDisp};max-width:140px;">${stdOpts}</select>
        <select id="icon_custom_${p.id}" style="display:${custDisp};max-width:140px;">${custOpts}</select>
    `;
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
        const demoActive = activeEvent && Number(activeEvent.is_demo);
        activeDiv.innerText = activeEvent
            ? `Aktiv: #${activeEvent.id} – ${activeEvent.name}${demoActive ? " (Demo)" : ""}`
            : "Aktiv: (kein Event aktiv)";
    }

    if (templateSelect) {
        templateSelect.innerHTML = "<option value=''>Vorlage (optional)</option>";
        events.forEach(ev => {
            const demoTag = Number(ev.is_demo) ? " (Demo)" : "";
            templateSelect.innerHTML += `<option value=\"${ev.id}\">#${ev.id} – ${ev.name}${demoTag}</option>`;
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
        const isDemo = Number(ev.is_demo);
        const demoBadge = isDemo ? ' <span class="demo-badge">Demo</span>' : "";
        tbody.innerHTML += `
            <tr>
                <td>${ev.id}</td>
                <td>
                    <input id="event_name_${ev.id}" value="${ev.name.replace(/\"/g, "&quot;")}">
                    <button class="inlineBtn" onclick="saveEventName(${ev.id})">Speichern</button>
                    ${demoBadge}
                </td>
                <td>${ev.status}</td>
                <td>${ev.billing_status || "-"}</td>
                <td>${formatDate(ev.starts_at)}</td>
                <td>${formatDate(ev.ends_at)}</td>
                <td><button class="inlineBtn" onclick="activateEvent(${ev.id})">Aktivieren</button></td>
                <td><button class="deleteBtn" onclick="closeEvent(${ev.id})">Abschließen…</button></td>
                <td><button class="inlineBtn" onclick="duplicateEvent(${ev.id})">Duplizieren</button></td>
                <td>${
                    isDemo
                        ? '<span style="color:#888;font-size:12px" title="Demo nur zurücksetzen">—</span>'
                        : ev.status === "active"
                        ? '<span style="color:#888;font-size:12px">—</span>'
                        : '<button class="deleteBtn" onclick="deleteEventPermanent(' + ev.id + ')">Dauerhaft löschen</button>'
                }</td>
            </tr>
        `;
    });

    renderDemoPanel();
}

function renderDemoPanel() {
    const statusEl = document.getElementById("demoStatus");
    if (!statusEl) return;

    const demo = events.find(function (e) { return Number(e.is_demo); });
    if (!demo) {
        statusEl.textContent = "Demo-Event wird beim Backend-Start angelegt.";
        return;
    }

    const demoActive = activeEvent && Number(activeEvent.id) === Number(demo.id);
    statusEl.innerHTML = demoActive
        ? `Demo „${demo.name}“ (#${demo.id}) ist <strong>aktiv</strong>.`
        : `Demo „${demo.name}“ (#${demo.id}) ist bereit – „Demo starten“ schaltet um.`;
}

async function activateDemoEvent() {
    const demo = events.find(function (e) { return Number(e.is_demo); });
    if (!demo) {
        alert("Kein Demo-Event vorhanden.");
        return;
    }
    if (
        activeEvent &&
        Number(activeEvent.id) !== Number(demo.id) &&
        !confirm(
            "Demo-Event aktivieren?\n\nDas aktuell aktive Event wird geschlossen."
        )
    ) {
        return;
    }
    if (activeEvent && Number(activeEvent.id) === Number(demo.id)) {
        alert("Demo ist bereits aktiv.");
        return;
    }

    const res = await fetch(API + "/admin/demo/activate", { method: "POST" });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        alert(data.error || "Demo konnte nicht gestartet werden");
        return;
    }
    load();
}

async function resetDemoEvent() {
    const demo = events.find(function (e) { return Number(e.is_demo); });
    if (!demo) {
        alert("Kein Demo-Event vorhanden.");
        return;
    }
    if (
        !confirm(
            "Demo zurücksetzen?\n\n" +
            "Alle Bestellungen und Deckel werden gelöscht.\n" +
            "Artikel, Tische und Demo-Nutzer werden auf den Ausgangszustand gesetzt."
        )
    ) {
        return;
    }

    const res = await fetch(API + "/admin/demo/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id: demo.id }),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        alert(data.error || "Demo-Reset fehlgeschlagen");
        return;
    }
    alert("Demo wurde zurückgesetzt.");
    load();
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
    const qs = event_id ? ("?event_id=" + encodeURIComponent(event_id)) : "";
    window.location.href = "admin_event_close.html" + qs;
}

async function closeActiveEvent() {
    window.location.href = "admin_event_close.html";
}

async function deleteEventPermanent(event_id) {
    const ev = events.find(function (e) { return Number(e.id) === Number(event_id); });
    if (!ev) return;
    if (ev.status === "active") {
        alert("Aktives Event zuerst abschließen.");
        return;
    }
    const warning =
        "Event „" + ev.name + "“ (#" + ev.id + ") DAUERHAFT löschen?\n\n" +
        "Unwiderruflich gelöscht werden:\n" +
        "• alle Bestellungen und Zahlungen\n" +
        "• alle Deckel\n" +
        "• Artikel, Kategorien, Tische\n" +
        "• Bedienungen und Theken-Konten\n" +
        "• das Event selbst";
    if (!confirm(warning)) return;

    const nameConfirm = prompt(
        "Zur Bestätigung den exakten Event-Namen eingeben:\n\n" + ev.name
    );
    if (nameConfirm === null) return;
    if (nameConfirm.trim() !== String(ev.name || "").trim()) {
        alert("Der eingegebene Name stimmt nicht überein.");
        return;
    }

    const phrase = prompt('Zur Bestätigung „LÖSCHEN“ eingeben (Großbuchstaben):');
    if (phrase === null) return;
    const phraseNorm = phrase.trim().toUpperCase().replace("Ö", "OE");
    if (phraseNorm !== "LOESCHEN" && phrase.trim() !== "LÖSCHEN") {
        alert("Bestätigung fehlgeschlagen (erwartet: LÖSCHEN).");
        return;
    }

    const res = await fetch(API + "/admin/events/delete-permanent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            event_id: event_id,
            confirm_name: nameConfirm.trim(),
            confirm_phrase: phrase.trim(),
        }),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        alert(data.error || "Löschen fehlgeschlagen");
        return;
    }
    alert(
        "Event gelöscht: " + (data.event_name || ev.name) +
        (data.deleted_orders != null ? "\n(" + data.deleted_orders + " Bestellungen entfernt)" : "")
    );
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
    const sorted = typeof sortTabsAlpha === "function" ? sortTabsAlpha(tabs) : tabs.slice();
    let html = `<table><thead><tr><th>Name</th><th>Offen</th><th>Aktionen</th></tr></thead><tbody>`;
    sorted.forEach(t => {
        const bal = Number(t.balance || 0);
        const canDelete = bal <= 0.0001;
        html += `<tr>
            <td><input id="tab_name_${t.id}" value="${String(t.name || "").replace(/"/g, "&quot;")}"></td>
            <td>${formatPrice(bal)} €</td>
            <td>
                <button class="inlineBtn" onclick="saveTabName(${t.id})">Speichern</button>
                ${canDelete ? `<button class="deleteBtn" onclick="deleteTab(${t.id})">Löschen</button>` : `<span style="opacity:0.6">Offen</span>`}
            </td>
        </tr>`;
    });
    html += `</tbody></table>`;
    div.innerHTML = html;
}

async function saveTabName(id) {
    const el = document.getElementById("tab_name_" + id);
    const name = el ? el.value.trim() : "";
    if (!name) {
        alert("Name fehlt");
        return;
    }
    const res = await fetch(API + "/admin/tabs/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Speichern fehlgeschlagen");
        return;
    }
    load();
}

async function deleteTab(id) {
    if (!window.confirm("Deckel wirklich löschen? (nur bei Saldo 0)")) return;
    const res = await fetch(API + "/admin/tabs/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || data.hint || "Löschen fehlgeschlagen");
        return;
    }
    load();
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
    const disp = document.getElementById("prod_display_cat");
    if (!select) return;

    select.innerHTML = '<option value="">Kategorie wählen</option>';

    categories.forEach(c => {
        select.innerHTML += `
            <option value="${c.id}">${c.name}</option>
        `;
    });

    if (disp) {
        disp.innerHTML = '<option value="">Anzeige wie Station</option>';
        categories.forEach(c => {
            disp.innerHTML += `<option value="${c.id}">${c.name}</option>`;
        });
    }
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

        let dispOpts = '<option value="">– wie Station –</option>';
        categories.forEach(c => {
            const sel =
                p.display_category_id != null && Number(c.id) === Number(p.display_category_id)
                    ? "selected"
                    : "";
            dispOpts += `<option value="${c.id}" ${sel}>${c.name}</option>`;
        });

        const vr = Number(p.vat_rate) === 7 ? 7 : 19;
        const vatSel7 = vr === 7 ? "selected" : "";
        const vatSel19 = vr === 19 ? "selected" : "";

        const rowHtml = `
            <tr>
                <td>${p.id}</td>
                <td><input id="name_${p.id}" value="${p.name}"></td>
                <td><input id="price_${p.id}" value="${formatPrice(p.price)}"></td>
                <td>
                    <select id="vat_${p.id}">
                        <option value="7" ${vatSel7}>7 %</option>
                        <option value="19" ${vatSel19}>19 %</option>
                    </select>
                </td>
                <td>
                    <select id="cat_${p.id}">
                        ${options}
                    </select>
                </td>
                <td>
                    <select id="display_cat_${p.id}">
                        ${dispOpts}
                    </select>
                </td>
                <td class="icon-picker-cell">${iconPickerCellHtml(p)}</td>
                <td>
                    <button class="inlineBtn" onclick="saveProduct(${p.id})">Speichern</button>
                    <button class="deleteBtn" onclick="deleteProduct(${p.id})">Löschen</button>
                </td>
            </tr>
        `;
        tbody.insertAdjacentHTML("beforeend", rowHtml);
    });
}

async function addProduct() {
    const name = document.getElementById("prod_name").value.trim();
    let price = document.getElementById("prod_price").value.trim().replace(",", ".");
    const category_id = parseInt(document.getElementById("prod_cat").value, 10);
    const rawDisp = document.getElementById("prod_display_cat")
        ? document.getElementById("prod_display_cat").value
        : "";

    if (!name || !price || !category_id) {
        alert("Alle Felder ausfüllen");
        return;
    }

    const pv = document.getElementById("prod_vat");
    const rawVat = pv ? pv.value : "19";
    const vat_rate = Number(rawVat) === 7 ? 7 : 19;

    const body = {
        name,
        price: parseFloat(price),
        category_id,
        vat_rate
    };
    if (rawDisp) {
        body.display_category_id = parseInt(rawDisp, 10);
    }
    Object.assign(body, readIconFields("prod"));

    await fetch(API + "/admin/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });

    document.getElementById("prod_name").value = "";
    document.getElementById("prod_price").value = "";
    document.getElementById("prod_cat").value = "";
    if (pv) pv.value = "19";
    const pd = document.getElementById("prod_display_cat");
    if (pd) pd.value = "";
    load();
}

async function saveProduct(id) {
    const name = document.getElementById("name_" + id).value.trim();
    let price = document.getElementById("price_" + id).value.trim().replace(",", ".");
    const category_id = parseInt(document.getElementById("cat_" + id).value, 10);
    const rawDisp = document.getElementById("display_cat_" + id)
        ? document.getElementById("display_cat_" + id).value
        : "";

    const rawVat = document.getElementById("vat_" + id)
        ? document.getElementById("vat_" + id).value
        : "19";
    const vat_rate = Number(rawVat) === 7 ? 7 : 19;

    const body = {
        id,
        name,
        price: parseFloat(price),
        category_id,
        vat_rate
    };
    body.display_category_id = rawDisp === "" ? null : parseInt(rawDisp, 10);
    Object.assign(body, readIconFields(String(id)));

    await fetch(API + "/admin/products/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
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
            <div class="row">
                <input id="uname_${user.id}" value="${(user.name || "").replace(/"/g, "&quot;")}" placeholder="Name">
                <input id="upin_${user.id}" value="${(user.pin || "").replace(/"/g, "&quot;")}" placeholder="PIN">
                <input id="ucash_${user.id}" value="${formatPrice(user.opening_cash || 0)}" placeholder="Wechselgeld Start">
                <input id="uclosing_${user.id}" value="${user.closing_cash == null ? "" : formatPrice(user.closing_cash)}" placeholder="Schlussbestand (gezählt)">
                <button class="inlineBtn" onclick="saveUser(${user.id})">Speichern</button>
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
            <div class="row">
                <input id="uname_${user.id}" value="${(user.name || "").replace(/"/g, "&quot;")}" placeholder="Name">
                <input id="upin_${user.id}" value="${(user.pin || "").replace(/"/g, "&quot;")}" placeholder="PIN">
                <input id="ucash_${user.id}" value="${formatPrice(user.opening_cash || 0)}" placeholder="Wechselgeld Start">
                <input id="uclosing_${user.id}" value="${user.closing_cash == null ? "" : formatPrice(user.closing_cash)}" placeholder="Schlussbestand (gezählt)">
                <button class="inlineBtn" onclick="saveUser(${user.id})">Speichern</button>
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
    const opening_cash = parseMoneyInput(document.getElementById("user_opening_cash").value);

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
            role: "waiter",
            opening_cash
        })
    });

    document.getElementById("user_name").value = "";
    document.getElementById("user_pin").value = "";
    document.getElementById("user_opening_cash").value = "";
    load();
}

async function addStation() {
    const name = document.getElementById("station_name").value.trim();
    const pin = document.getElementById("station_pin").value.trim();
    const opening_cash = parseMoneyInput(document.getElementById("station_opening_cash").value);

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
            role: "station",
            opening_cash
        })
    });

    document.getElementById("station_name").value = "";
    document.getElementById("station_pin").value = "";
    document.getElementById("station_opening_cash").value = "";
    load();
}

async function saveUser(id) {
    const name = document.getElementById("uname_" + id).value.trim();
    const pin = document.getElementById("upin_" + id).value.trim();
    const opening_cash = parseMoneyInput(document.getElementById("ucash_" + id).value);
    const closing_cash = parseMoneyInput(document.getElementById("uclosing_" + id).value, true);
    if (!name || !pin) {
        alert("Name + PIN erforderlich");
        return;
    }
    const res = await fetch(API + "/admin/users/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name, pin, opening_cash, closing_cash })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Speichern fehlgeschlagen");
        return;
    }
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

/* Daten erst nach erfolgreichem Login (checkLogin → load). */
