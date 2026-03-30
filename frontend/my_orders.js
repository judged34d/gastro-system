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
        const statusRows = [];
        orders.forEach(order => {
            order.items.forEach(item => {
                openItems += item.quantity_open;
            });
            statusRows.push(order);
        });

        const statusByOrder = {};
        for (const o of statusRows) {
            try {
                const sr = await fetch(API + "/orders/" + o.order_id + "/status", { cache: "no-store" });
                statusByOrder[o.order_id] = await sr.json();
            } catch (_) {
                statusByOrder[o.order_id] = { status: "Offen", status_key: "open" };
            }
        }

        let orderLines = "<div class='order-list'>";
        orders.forEach(o => {
            const s = statusByOrder[o.order_id] || { status: "Offen", status_key: "open" };
            const cls = s.status_key === "ready"
                ? "status-ready"
                : s.status_key === "preparing"
                    ? "status-preparing"
                    : s.status_key === "partial"
                        ? "status-partial"
                        : "status-open";
            orderLines += `
                <div class="order-line">
                    <div>Order #${o.order_number}</div>
                    <div class="status-pill ${cls}">${s.status}</div>
                </div>
            `;
        });
        orderLines += "</div>";

        const card = document.createElement("div");
        card.classList.add("order-card");

        card.innerHTML = `
            <div class="order-title">${table.name}</div>
            <div class="order-meta">
                Offene Bestellungen: ${orders.length}<br>
                Offene Positionen: ${openItems}
            </div>
            ${orderLines}
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
