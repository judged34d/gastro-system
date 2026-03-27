const API = "http://192.168.0.165:8000";
const STATION_ID = 1;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

async function load() {
    const res = await fetch(API + "/station/" + STATION_ID + "/display");
    const data = await res.json();

    const grid = document.getElementById("grid");
    const warning = document.getElementById("warning");

    grid.innerHTML = "";

    // Warning
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

        // HEADER
        html += "<div class='tile-header'>" + slot.table_name + "</div>";
        html += "<div class='waiter'>" + slot.waiter_name + "</div>";
        html += "<div class='order-id'>#" + slot.order_number + "</div>";

        // TABLE HEADER
        html += "<div class='table'>";
        html += "<div class='row header-row'>";
        html += "<div>Artikel</div><div>Preis</div><div>Summe</div>";
        html += "</div>";

        // ITEMS
        slot.items.forEach(i => {
            html += "<div class='row'>";
            html += "<div>" + i.quantity_open + "x " + i.name + "</div>";
            html += "<div>" + formatPrice(i.unit_price) + "</div>";
            html += "<div>" + formatPrice(i.line_total) + "</div>";
            html += "</div>";
        });

        html += "</div>";

        // TOTAL
        html += "<div class='total'>Gesamt: " + formatPrice(slot.order_total) + "</div>";

        div.innerHTML = html;

        // Klick
        div.onclick = async () => {
            await fetch(API + "/station/" + STATION_ID + "/orders/" + slot.order_id + "/status", {
                method: "POST"
            });
            load();
        };

        grid.appendChild(div);
    });
}

setInterval(load, 3000);
load();
