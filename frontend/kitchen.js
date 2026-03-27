const API = "http://192.168.0.165:8000";

/* ============================================================
STATION NAME AUS LOGIN
============================================================ */
const stationName = localStorage.getItem("user_name");
document.getElementById("stationName").innerText = stationName || "Theke";

/* ============================================================
STATION ID
============================================================ */
let STATION_ID = localStorage.getItem("user_id") || 1;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

/* ============================================================
STATUS TEXT
============================================================ */
function getStatusText(status) {
    if (status === "new") return "Neu";
    if (status === "preparing") return "In Arbeit";
    if (status === "ready") return "Bereit";
    return "";
}

function getStatusClass(status) {
    if (status === "new") return "status-new";
    if (status === "preparing") return "status-preparing";
    if (status === "ready") return "status-ready";
    return "";
}

/* ============================================================
LOAD
============================================================ */
async function load() {
    const res = await fetch(API + "/station/" + STATION_ID + "/display");
    const data = await res.json();

    const grid = document.getElementById("grid");
    const warning = document.getElementById("warning");

    grid.innerHTML = "";

    warning.innerHTML = data.waiting > 0
        ? "⚠ " + data.waiting + " warten"
        : "";

    data.slots.forEach(slot => {

        const div = document.createElement("div");
        div.classList.add("tile");

        if (!slot) {
            grid.appendChild(div);
            return;
        }

        div.classList.add(slot.status);

        let html = "";

        html += "<div class='tile-header'>" + slot.table_name + "</div>";
        html += "<div class='waiter'>" + slot.waiter_name + "</div>";
        html += "<div class='order-id'>#" + slot.order_number + "</div>";

        html += "<div class='table'>";
        html += "<div class='row header-row'>";
        html += "<div>Artikel</div><div>Preis</div><div>Summe</div>";
        html += "</div>";

        slot.items.forEach(i => {
            html += "<div class='row'>";
            html += "<div>" + i.quantity_open + "x " + i.name + "</div>";
            html += "<div>" + formatPrice(i.unit_price) + "</div>";
            html += "<div>" + formatPrice(i.line_total) + "</div>";
            html += "</div>";
        });

        html += "</div>";

        /* ====================================================
        TOTAL + STATUS BLOCK
        ==================================================== */
        html += "<div class='total-block'>";
        html += "<div class='line'></div>";
        html += "<div class='total'>Gesamt: " + formatPrice(slot.order_total) + "</div>";
        html += "<div class='line'></div>";
        html += "<div class='status-text " + getStatusClass(slot.status) + "'>" +
                getStatusText(slot.status) +
                "</div>";
        html += "</div>";

        div.innerHTML = html;

        div.onclick = async () => {
            await fetch(API + "/station/" + STATION_ID + "/orders/" + slot.order_id + "/status", {
                method: "POST"
            });
            load();
        };

        grid.appendChild(div);
    });
}

/* ============================================================
NAV
============================================================ */
function goToOrders() {
    alert("Platzhalter: Meine Bestellungen");
}

setInterval(load, 3000);
load();
