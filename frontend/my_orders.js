const API = "http://192.168.0.165:8000";

const userId = localStorage.getItem("user_id");
const userName = localStorage.getItem("user_name");

document.getElementById("username").innerText = userName || "";

async function loadMyOrders() {
    const tablesRes = await fetch(API + "/waiter/" + userId + "/tables");
    const tables = await tablesRes.json();

    const container = document.getElementById("orders");
    container.innerHTML = "";

    for (const table of tables) {
        const ordersRes = await fetch(API + "/table/" + table.id + "/orders");
        const orders = await ordersRes.json();

        if (!orders || orders.length === 0) {
            continue;
        }

        let openItems = 0;
        orders.forEach(order => {
            order.items.forEach(item => {
                openItems += item.quantity_open;
            });
        });

        const card = document.createElement("div");
        card.classList.add("order-card");

        card.innerHTML = `
            <div class="order-title">${table.name}</div>
            <div class="order-meta">
                Offene Bestellungen: ${orders.length}<br>
                Offene Positionen: ${openItems}
            </div>
            <button class="open-btn" onclick="openManage(${table.id}, '${table.name.replace(/'/g, "\\'")}')">Öffnen</button>
        `;

        container.appendChild(card);
    }
}

function openManage(tableId, tableName) {
    localStorage.setItem("table_id", tableId);
    localStorage.setItem("table_name", tableName);
    window.location.href = "order_manage.html";
}

function goBack() {
    window.location.href = "tables.html";
}

loadMyOrders();
