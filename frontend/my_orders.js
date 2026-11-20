const API = (typeof window.getGastroApiBase === "function")
    ? window.getGastroApiBase()
    : (function () {
        const h = window.location.hostname || "";
        const p = window.location.protocol;
        if (/(^|\.)mpbin\.de$/i.test(h)) return "https://api.mpbin.de";
        if (p === "file:") return "http://localhost:8000";
        return p + "//" + (h || "localhost") + ":8000";
    })();

const userId = localStorage.getItem("user_id");
const userName = localStorage.getItem("user_name");

document.getElementById("username").innerText = userName || "";

async function loadMyOrders() {
    const res = await fetch(API + "/waiter/" + userId + "/orders/mine", { cache: "no-store" });
    const orders = await res.json();

    const container = document.getElementById("orders");
    container.innerHTML = "";

    if (!Array.isArray(orders) || orders.length === 0) {
        container.innerHTML = '<div class="order-meta" style="padding:12px">Keine eigenen offenen Bestellungen.</div>';
        return;
    }

    // Nach Tisch gruppieren – nur eigene Orders
    const byTable = new Map();
    for (const order of orders) {
        const key = String(order.table_id);
        if (!byTable.has(key)) {
            byTable.set(key, {
                table_id: order.table_id,
                table_name: order.table_name || ("Tisch " + order.table_id),
                orders: [],
            });
        }
        byTable.get(key).orders.push(order);
    }

    for (const group of byTable.values()) {
        let openItems = 0;
        group.orders.forEach((order) => {
            (order.items || []).forEach((item) => {
                openItems += Number(item.quantity_open) || 0;
            });
        });

        const card = document.createElement("div");
        card.classList.add("order-card");
        card.innerHTML = `
            <div class="order-title">${group.table_name}</div>
            <div class="order-meta">
                Meine offenen Bestellungen: ${group.orders.length}<br>
                Offene Positionen: ${openItems}
            </div>
            <button class="open-btn" type="button">Öffnen</button>
        `;
        card.querySelector(".open-btn").onclick = () =>
            openManage(group.table_id, group.table_name);
        container.appendChild(card);
    }
}

function openManage(tableId, tableName) {
    localStorage.setItem("table_id", tableId);
    localStorage.setItem("table_name", tableName);
    localStorage.setItem(
        "order_manage_ctx",
        JSON.stringify({
            mode: "waiter_mine",
            mine_only: true,
            waiter_id: Number(userId) || 0,
            return_to: "my_orders.html",
        })
    );
    window.location.href = "order_manage.html";
}

function goBack() {
    window.location.href = "tables.html";
}

loadMyOrders();
