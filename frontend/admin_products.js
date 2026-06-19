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
let standardIcons = [];
let customIcons = [];
let previewCategories = [];
let activePreviewCategory = null;
let dragProductId = null;
let reorderBusy = false;
let sortOrderDirty = false;

function formatPrice(v) {
    return parseFloat(v).toFixed(2).replace(".", ",");
}

function formatPriceEuro(v) {
    return parseFloat(v).toFixed(2).replace(".", ",") + " €";
}

function checkLogin() {
    const input = document.getElementById("adminPass").value;
    if (input === ADMIN_PASSWORD) {
        document.getElementById("loginOverlay").style.display = "none";
        document.getElementById("productsContent").style.display = "block";
        sessionStorage.setItem("gastro_admin_ok", "1");
        load();
    } else {
        document.getElementById("loginError").innerText = "Falsches Passwort";
    }
}

document.addEventListener("DOMContentLoaded", function () {
    if (sessionStorage.getItem("gastro_admin_ok") === "1") {
        document.getElementById("loginOverlay").style.display = "none";
        document.getElementById("productsContent").style.display = "block";
        load();
    }
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

async function load() {
    await loadIconCatalogs();
    categories = await fetch(API + "/admin/categories").then(r => r.json());
    products = await fetch(API + "/admin/products").then(r => r.json());
    products.sort(function (a, b) {
        const sa = Number(a.sort_order != null ? a.sort_order : a.id);
        const sb = Number(b.sort_order != null ? b.sort_order : b.id);
        if (sa !== sb) return sa - sb;
        return String(a.name || "").localeCompare(String(b.name || ""), "de");
    });
    buildPreviewCategories();
    renderCategoryOptions();
    renderProducts();
    renderPreviewCategories();
    renderPreviewTiles();
    onProductIconTypeChange("prod");
    const status = document.getElementById("sortSaveStatus");
    if (status) delete status.dataset.savedMsg;
    setSortOrderDirty(false);
}

function setSortOrderDirty(dirty) {
    sortOrderDirty = !!dirty;
    const btn = document.getElementById("saveSortBtn");
    const status = document.getElementById("sortSaveStatus");
    if (btn) btn.disabled = !sortOrderDirty || reorderBusy;
    if (!status) return;
    status.classList.remove("is-dirty", "is-ok", "is-error");
    if (sortOrderDirty) {
        delete status.dataset.savedMsg;
        status.textContent = "Ungespeicherte Änderungen an der Reihenfolge";
        status.classList.add("is-dirty");
    } else if (!status.dataset.savedMsg) {
        status.textContent = "";
    }
}

function showSortSaveSuccess() {
    const status = document.getElementById("sortSaveStatus");
    if (status) {
        status.dataset.savedMsg = "1";
        status.classList.remove("is-dirty", "is-error");
        status.classList.add("is-ok");
        status.textContent = "Reihenfolge gespeichert.";
    }
    alert("Reihenfolge wurde gespeichert.");
}

function menuCategoryId(p) {
    return p.display_category_id != null ? p.display_category_id : p.category_id;
}

function menuCategoryName(p) {
    return p.display_category != null && p.display_category !== ""
        ? p.display_category
        : (p.category || "Ohne Kategorie");
}

function buildPreviewCategories() {
    const map = {};
    products.forEach(function (p) {
        const mid = menuCategoryId(p);
        map[mid] = menuCategoryName(p);
    });
    previewCategories = Object.keys(map).map(function (id) {
        return { id: parseInt(id, 10), name: map[id] };
    }).sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name), "de");
    });
    if (!previewCategories.length) {
        activePreviewCategory = null;
        return;
    }
    if (
        activePreviewCategory == null ||
        !previewCategories.some(function (c) { return Number(c.id) === Number(activePreviewCategory); })
    ) {
        activePreviewCategory = previewCategories[0].id;
    }
}

async function loadIconCatalogs() {
    const std = await fetch(API + "/icons/standard").then(r => r.json()).catch(() => ({}));
    standardIcons = std.icons || [];
    customIcons = await fetch(API + "/admin/icons").then(r => r.json()).catch(() => []);
    fillIconSelect("prod_icon_std", standardIcons.map(function (i) {
        return { value: i.id, label: (i.emoji || "") + " " + i.label };
    }));
    fillIconSelect("prod_icon_custom", customIcons.map(function (i) {
        return { value: String(i.id), label: i.name };
    }));
}

function fillIconSelect(id, options) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = options.map(function (o) {
        return '<option value="' + o.value + '">' + o.label + "</option>";
    }).join("");
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
    return { icon_type: icon_type, icon_ref: icon_ref };
}

function iconPickerCellHtml(p) {
    const t = p.icon_type || "none";
    const r = p.icon_ref || "";
    const stdOpts = standardIcons.map(function (i) {
        const sel = t === "standard" && r === i.id ? "selected" : "";
        return '<option value="' + i.id + '" ' + sel + ">" + i.emoji + " " + i.label + "</option>";
    }).join("");
    const custOpts = customIcons.map(function (i) {
        const sel = t === "custom" && String(r) === String(i.id) ? "selected" : "";
        return '<option value="' + i.id + '" ' + sel + ">" + i.name + "</option>";
    }).join("");
    const stdDisp = t === "standard" ? "inline-block" : "none";
    const custDisp = t === "custom" ? "inline-block" : "none";
    return (
        '<select id="icon_type_' + p.id + '" onchange="onProductIconTypeChange(' + p.id + ')">' +
        '<option value="none" ' + (t === "none" ? "selected" : "") + ">–</option>" +
        '<option value="standard" ' + (t === "standard" ? "selected" : "") + ">Standard</option>" +
        '<option value="custom" ' + (t === "custom" ? "selected" : "") + ">Eigen</option>" +
        "</select>" +
        '<select id="icon_std_' + p.id + '" style="display:' + stdDisp + ';max-width:140px;">' + stdOpts + "</select>" +
        '<select id="icon_custom_' + p.id + '" style="display:' + custDisp + ';max-width:140px;">' + custOpts + "</select>"
    );
}

function renderCategoryOptions() {
    const select = document.getElementById("prod_cat");
    const disp = document.getElementById("prod_display_cat");
    if (!select) return;

    select.innerHTML = '<option value="">Kategorie wählen</option>';
    categories.forEach(function (c) {
        select.insertAdjacentHTML("beforeend", '<option value="' + c.id + '">' + c.name + "</option>");
    });

    if (disp) {
        disp.innerHTML = '<option value="">Anzeige wie Station</option>';
        categories.forEach(function (c) {
            disp.insertAdjacentHTML("beforeend", '<option value="' + c.id + '">' + c.name + "</option>");
        });
    }
}

function renderProducts() {
    const tbody = document.getElementById("productTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    products.forEach(function (p) {
        let options = "";
        categories.forEach(function (c) {
            options += '<option value="' + c.id + '" ' + (c.id === p.category_id ? "selected" : "") + ">" + c.name + "</option>";
        });

        let dispOpts = '<option value="">– wie Station –</option>';
        categories.forEach(function (c) {
            const sel = p.display_category_id != null && Number(c.id) === Number(p.display_category_id) ? "selected" : "";
            dispOpts += '<option value="' + c.id + '" ' + sel + ">" + c.name + "</option>";
        });

        const vr = Number(p.vat_rate) === 7 ? 7 : 19;
        const vatSel7 = vr === 7 ? "selected" : "";
        const vatSel19 = vr === 19 ? "selected" : "";
        const safeName = String(p.name || "").replace(/"/g, "&quot;");

        tbody.insertAdjacentHTML("beforeend",
            "<tr>" +
            "<td>" + p.id + "</td>" +
            '<td><input id="name_' + p.id + '" value="' + safeName + '"></td>' +
            '<td><input id="price_' + p.id + '" value="' + formatPrice(p.price) + '"></td>' +
            '<td><select id="vat_' + p.id + '"><option value="7" ' + vatSel7 + '>7 %</option><option value="19" ' + vatSel19 + '>19 %</option></select></td>' +
            '<td><select id="cat_' + p.id + '">' + options + "</select></td>" +
            '<td><select id="display_cat_' + p.id + '">' + dispOpts + "</select></td>" +
            '<td class="icon-picker-cell">' + iconPickerCellHtml(p) + "</td>" +
            '<td class="actions-cell">' +
            '<button class="inlineBtn" onclick="saveProduct(' + p.id + ')">Speichern</button> ' +
            '<button class="deleteBtn" onclick="deleteProduct(' + p.id + ')">Löschen</button>' +
            "</td></tr>"
        );
    });
}

function renderPreviewCategories() {
    const div = document.getElementById("previewCategories");
    if (!div) return;
    div.innerHTML = "";
    previewCategories.forEach(function (c) {
        const btn = document.createElement("div");
        btn.className = "category" + (Number(c.id) === Number(activePreviewCategory) ? " active" : "");
        btn.textContent = c.name;
        btn.onclick = function () {
            activePreviewCategory = c.id;
            renderPreviewCategories();
            renderPreviewTiles();
        };
        div.appendChild(btn);
    });
}

function productsInActiveCategory() {
    return products.filter(function (p) {
        return Number(menuCategoryId(p)) === Number(activePreviewCategory);
    });
}

function renderPreviewTiles() {
    const div = document.getElementById("previewTiles");
    if (!div) return;
    div.innerHTML = "";

    if (activePreviewCategory == null) {
        div.textContent = "Noch keine Artikel vorhanden.";
        return;
    }

    productsInActiveCategory().forEach(function (p) {
        const el = document.createElement("div");
        el.className = "product";
        el.draggable = true;
        el.dataset.productId = String(p.id);

        el.innerHTML =
            (typeof productTileHtml === "function"
                ? productTileHtml(p, formatPriceEuro(p.price), 0)
                : "<b>" + p.name + "</b><br>" + formatPriceEuro(p.price)) +
            '<div class="drag-handle">⇅ Reihenfolge</div>';

        const iconSlot = el.querySelector(".product-icon-slot");
        if (iconSlot && typeof mountProductIcon === "function") {
            mountProductIcon(iconSlot, p);
        }

        el.addEventListener("dragstart", onTileDragStart);
        el.addEventListener("dragend", onTileDragEnd);
        el.addEventListener("dragover", onTileDragOver);
        el.addEventListener("dragleave", onTileDragLeave);
        el.addEventListener("drop", onTileDrop);

        div.appendChild(el);
    });
}

function onTileDragStart(ev) {
    dragProductId = Number(ev.currentTarget.dataset.productId);
    ev.currentTarget.classList.add("dragging");
    if (ev.dataTransfer) {
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(dragProductId));
    }
}

function onTileDragEnd(ev) {
    ev.currentTarget.classList.remove("dragging");
    document.querySelectorAll("#previewTiles .product.drag-over").forEach(function (el) {
        el.classList.remove("drag-over");
    });
    dragProductId = null;
}

function onTileDragOver(ev) {
    ev.preventDefault();
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
    ev.currentTarget.classList.add("drag-over");
}

function onTileDragLeave(ev) {
    ev.currentTarget.classList.remove("drag-over");
}

async function onTileDrop(ev) {
    ev.preventDefault();
    ev.currentTarget.classList.remove("drag-over");
    const targetId = Number(ev.currentTarget.dataset.productId);
    const sourceId = dragProductId != null ? dragProductId : Number(ev.dataTransfer.getData("text/plain"));
    if (!sourceId || !targetId || sourceId === targetId) return;

    const catProducts = productsInActiveCategory();
    const fromIdx = catProducts.findIndex(function (p) { return Number(p.id) === sourceId; });
    const toIdx = catProducts.findIndex(function (p) { return Number(p.id) === targetId; });
    if (fromIdx < 0 || toIdx < 0) return;

    const moved = catProducts.splice(fromIdx, 1)[0];
    catProducts.splice(toIdx, 0, moved);

    applyCategoryOrder(catProducts);
    renderPreviewTiles();
    setSortOrderDirty(true);
}

function applyCategoryOrder(reorderedCatProducts) {
    const byCat = {};
    products.forEach(function (p) {
        const mid = menuCategoryId(p);
        if (!byCat[mid]) byCat[mid] = [];
        byCat[mid].push(p);
    });
    byCat[activePreviewCategory] = reorderedCatProducts;

    const flat = [];
    let order = 0;
    previewCategories.forEach(function (c) {
        (byCat[c.id] || []).forEach(function (p) {
            p.sort_order = order;
            order += 1;
            flat.push(p);
        });
        delete byCat[c.id];
    });
    Object.keys(byCat).forEach(function (cid) {
        (byCat[cid] || []).forEach(function (p) {
            p.sort_order = order;
            order += 1;
            flat.push(p);
        });
    });
    products = flat;
}

function assignGlobalSortOrder() {
    const byCat = {};
    products.forEach(function (p) {
        const mid = menuCategoryId(p);
        if (!byCat[mid]) byCat[mid] = [];
        byCat[mid].push(p);
    });
    const flat = [];
    let order = 0;
    previewCategories.forEach(function (c) {
        (byCat[c.id] || []).forEach(function (p) {
            p.sort_order = order;
            order += 1;
            flat.push(p);
        });
    });
    products = flat;
}

async function savePreviewOrder() {
    if (!sortOrderDirty || reorderBusy) return;
    const ok = await saveSortOrder();
    if (ok) {
        setSortOrderDirty(false);
        showSortSaveSuccess();
    }
}

async function saveSortOrder() {
    if (reorderBusy) return false;
    reorderBusy = true;
    setSortOrderDirty(sortOrderDirty);
    const items = products.map(function (p, i) {
        return { id: p.id, sort_order: p.sort_order != null ? p.sort_order : i };
    });
    try {
        const res = await fetch(API + "/admin/products/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ items: items }),
        });
        if (!res.ok) {
            const data = await res.json().catch(function () { return {}; });
            const status = document.getElementById("sortSaveStatus");
            if (status) {
                status.classList.remove("is-dirty", "is-ok");
                status.classList.add("is-error");
                status.textContent = data.error || "Speichern fehlgeschlagen.";
            }
            alert(data.error || "Reihenfolge konnte nicht gespeichert werden.");
            await load();
            return false;
        }
        return true;
    } finally {
        reorderBusy = false;
        const btn = document.getElementById("saveSortBtn");
        if (btn) btn.disabled = !sortOrderDirty;
    }
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
        name: name,
        price: parseFloat(price),
        category_id: category_id,
        vat_rate: vat_rate,
    };
    if (rawDisp) body.display_category_id = parseInt(rawDisp, 10);
    Object.assign(body, readIconFields("prod"));

    await fetch(API + "/admin/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    document.getElementById("prod_name").value = "";
    document.getElementById("prod_price").value = "";
    document.getElementById("prod_cat").value = "";
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
        id: id,
        name: name,
        price: parseFloat(price),
        category_id: category_id,
        vat_rate: vat_rate,
    };
    body.display_category_id = rawDisp === "" ? null : parseInt(rawDisp, 10);
    Object.assign(body, readIconFields(String(id)));

    await fetch(API + "/admin/products/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    load();
}

async function deleteProduct(id) {
    if (!window.confirm("Artikel wirklich löschen?")) return;
    await fetch(API + "/admin/products/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: id }),
    });
    load();
}

async function applySuggestedIcons() {
    if (!window.confirm("Icons für alle Artikel des aktiven Events anhand der Namen zuordnen?")) return;
    const res = await fetch(API + "/admin/products/apply-icons", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        alert(data.error || "Zuordnung fehlgeschlagen.");
        return;
    }
    const n = data.updated_count || 0;
    const skipped = (data.skipped || []).length;
    alert("Icons zugeordnet: " + n + (skipped ? " (" + skipped + " ohne Treffer)" : "") + ".");
    load();
}

window.checkLogin = checkLogin;
window.applySuggestedIcons = applySuggestedIcons;
window.onProductIconTypeChange = onProductIconTypeChange;
window.addProduct = addProduct;
window.saveProduct = saveProduct;
window.deleteProduct = deleteProduct;
window.savePreviewOrder = savePreviewOrder;
