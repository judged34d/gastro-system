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

const tableId = localStorage.getItem("table_id");
const tableName = localStorage.getItem("table_name");
let manageCtx = null;

try {
    manageCtx = JSON.parse(localStorage.getItem("order_manage_ctx") || "null");
} catch (_) {
    manageCtx = null;
}

const isStationMode = !!(manageCtx && manageCtx.mode === "station_cashier_order");
const stationId = isStationMode ? Number(manageCtx.station_id || 0) : 0;
const stationOrderId = isStationMode ? Number(manageCtx.order_id || 0) : 0;

document.getElementById("table").innerText = isStationMode
    ? ("Theke Order #" + (manageCtx.order_number || stationOrderId))
    : ("Tisch: " + tableName);

let items = {};
let selection = {};

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

async function load() {
    let orders = [];
    if (isStationMode) {
        const res = await fetch(API + "/station/" + stationId + "/orders/open", { cache: "no-store" });
        const all = await res.json();
        const found = (Array.isArray(all) ? all : []).find(o => Number(o.order_id) === stationOrderId);
        if (found) {
            orders = [found];
        } else {
            orders = [];
        }
    } else {
        const res = await fetch(API + "/table/" + tableId + "/orders", { cache: "no-store" });
        orders = await res.json();
    }

    items = {};
    selection = {};

    orders.forEach(o => {
        o.items.forEach(i => {
            if (i.quantity_open <= 0) return;

            if (!items[i.name]) {
                items[i.name] = {
                    entries: [],
                    name: i.name,
                    price: i.price,
                    quantity_open: 0
                };
            }

            items[i.name].entries.push({
                id: i.id,
                qty: i.quantity_open,
                order_id: o.order_id
            });

            items[i.name].quantity_open += i.quantity_open;
        });
    });

    Object.keys(items).forEach(k => {
        selection[k] = 0;
    });

    render();
}

function add(name) {
    if (selection[name] < items[name].quantity_open) {
        selection[name]++;
    }
    render();
}

function selectAll(name) {
    selection[name] = items[name].quantity_open;
    render();
}

function remove(name) {
    if (selection[name] > 0) {
        selection[name]--;
    }
    render();
}

function render() {
    const container = document.getElementById("orders");
    container.innerHTML = "";

    let payTotal = 0;
    let restTotal = 0;

    Object.values(items).forEach(i => {
        const selectedQty = selection[i.name];
        const remainingQty = i.quantity_open - selectedQty;

        payTotal += selectedQty * i.price;
        restTotal += remainingQty * i.price;

        const div = document.createElement("div");
        div.classList.add("item");

        div.innerHTML = `
            <div>${remainingQty}x ${i.name}</div>
            <div>${formatPrice(i.price)}</div>
            <div>${formatPrice(remainingQty * i.price)}</div>
            <div class="selector">
                <button class="plus-btn" onclick="add('${i.name.replace(/'/g, "\\'")}')">+</button>
                <span class="selector-value">${selectedQty}</span>
                <button class="minus-btn" onclick="remove('${i.name.replace(/'/g, "\\'")}')">−</button>
                <button class="all-btn" onclick="selectAll('${i.name.replace(/'/g, "\\'")}')">Alle</button>
            </div>
        `;

        container.appendChild(div);
    });

    document.getElementById("total").innerText =
        "Zu zahlen: " + formatPrice(payTotal) +
        " | Rest: " + formatPrice(restTotal);
}

async function pay() {
    let hasPayment = false;

    for (const name in items) {
        let qtyToPay = selection[name];

        if (qtyToPay <= 0) continue;

        const entries = items[name].entries;

        for (const e of entries) {
            if (qtyToPay <= 0) break;

            const payQty = Math.min(qtyToPay, e.qty);

            if (payQty > 0) {
                hasPayment = true;

                await fetch(API + "/orders/" + e.order_id + "/pay-item", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        order_item_id: e.id,
                        quantity: payQty,
                        payment_type: "paid"
                    })
                });

                qtyToPay -= payQty;
            }
        }
    }

    if (!hasPayment) {
        alert("Keine Auswahl getroffen");
        return;
    }

    alert("Zahlung erfolgreich");
    load();
}

function payToTab() {
    let hasPayment = false;
    const entriesToPay = [];
    for (const name in items) {
        let qtyToPay = selection[name];
        if (qtyToPay <= 0) continue;
        const entries = items[name].entries;
        for (const e of entries) {
            if (qtyToPay <= 0) break;
            const payQty = Math.min(qtyToPay, e.qty);
            if (payQty > 0) {
                hasPayment = true;
                entriesToPay.push({
                    order_id: e.order_id,
                    order_item_id: e.id,
                    quantity: payQty
                });
                qtyToPay -= payQty;
            }
        }
    }
    if (!hasPayment) {
        alert("Keine Auswahl getroffen");
        return;
    }

    localStorage.setItem("tab_ctx", JSON.stringify({
        mode: isStationMode ? "station_pay_items" : "waiter_pay_items",
        entries: entriesToPay,
        station_id: isStationMode ? stationId : null
    }));
    window.location.href = "tab_select.html";
}

function cancel() {
    if (isStationMode) {
        localStorage.removeItem("order_manage_ctx");
        window.location.href = "kitchen.html";
    } else {
        window.location.href = "my_orders.html";
    }
}

load();
