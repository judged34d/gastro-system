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

function itemsPreview(items) {
    return (items || [])
        .filter((i) => Number(i.quantity_open) > 0)
        .map((i) => i.quantity_open + "× " + i.name)
        .join(", ");
}

async function loadColleagueOrders() {
    const res = await fetch(API + "/waiter/" + userId + "/orders/colleagues", {
        cache: "no-store",
    });
    const orders = await res.json();
    const container = document.getElementById("orders");
    container.innerHTML = "";

    if (!Array.isArray(orders) || orders.length === 0) {
        container.innerHTML =
            '<div class="order-meta" style="padding:12px">Keine offenen Bestellungen anderer Bedienungen.</div>';
        return;
    }

    for (const order of orders) {
        const preview = itemsPreview(order.items) || "—";
        const card = document.createElement("div");
        card.classList.add("order-card");
        card.dataset.orderId = String(order.order_id);

        const ownerLabel = order.waiter_name || "Unbekannt";
        const guest = order.waiter_id == null;
        const btnLabel = guest ? "Übernehmen" : "Übernahme anfragen";

        card.innerHTML = `
            <div class="order-title">${order.table_name || "Tisch"} · #${order.order_number || order.order_id}</div>
            <div class="order-meta">
                Von: <strong>${ownerLabel}</strong><br>
                ${preview}
            </div>
            <button type="button" class="claim-btn">${btnLabel}</button>
            <div class="claim-status" hidden></div>
        `;

        const btn = card.querySelector(".claim-btn");
        const statusEl = card.querySelector(".claim-status");
        btn.onclick = () => requestClaim(order, btn, statusEl);
        container.appendChild(card);
    }
}

async function requestClaim(order, btn, statusEl) {
    btn.disabled = true;
    statusEl.hidden = true;
    try {
        const res = await fetch(
            API + "/waiter/" + userId + "/orders/" + order.order_id + "/claim-request",
            { method: "POST", cache: "no-store" }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            statusEl.textContent = data.error || "Anfrage fehlgeschlagen";
            statusEl.hidden = false;
            btn.disabled = false;
            return;
        }
        if (data.mode === "direct") {
            btn.textContent = "Übernommen";
            btn.classList.add("claimed-direct");
            statusEl.textContent = "Jetzt unter deinen Bestellungen.";
            statusEl.hidden = false;
            return;
        }
        btn.textContent = "Anfrage gesendet";
        statusEl.textContent = "Wartet auf Bestätigung von " + (order.waiter_name || "Kollege");
        statusEl.hidden = false;
    } catch (_) {
        statusEl.textContent = "Netzwerkfehler";
        statusEl.hidden = false;
        btn.disabled = false;
    }
}

function goBack() {
    window.location.href = "tables.html";
}

loadColleagueOrders();
