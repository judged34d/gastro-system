const API = "http://192.168.0.165:8000";

const tableId = localStorage.getItem("table_id");
const tableName = localStorage.getItem("table_name");

document.getElementById("table").innerText = "Tisch: " + tableName;

let items = {};
let selection = {};

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

async function load() {
    const res = await fetch(API + "/table/" + tableId + "/orders");
    const orders = await res.json();

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
                        quantity: payQty
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

function cancel() {
    window.location.href = "my_orders.html";
}

load();
