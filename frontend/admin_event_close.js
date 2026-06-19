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

let checklist = null;
let eventId = null;

function euro(v) {
    return Number(v || 0).toFixed(2).replace(".", ",") + " €";
}

function parseMoneyInput(raw) {
    const s = String(raw ?? "").trim();
    if (!s) return null;
    const v = parseFloat(s.replace(",", "."));
    if (!Number.isFinite(v) || v < 0) return null;
    return v;
}

function formatMoneyInput(v) {
    if (v === null || v === undefined || v === "") return "";
    return Number(v).toFixed(2).replace(".", ",");
}

function goBack() {
    window.location.href = "admin.html";
}

function getEventIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("event_id");
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
}

function showError(msg) {
    const el = document.getElementById("loadError");
    if (!el) return;
    el.style.display = "block";
    el.className = "close-alert close-alert-error";
    el.textContent = msg;
}

function renderBlockers() {
    const el = document.getElementById("blockers");
    if (!el || !checklist) return;

    if (checklist.event_status !== "active") {
        el.innerHTML =
            '<div class="close-alert close-alert-warn">Event ist bereits beendet. Schlussbestände können hier noch nachtragen werden.</div>';
        return;
    }

    if (checklist.can_close) {
        el.innerHTML = '<div class="close-alert close-alert-ok">Alles erledigt – das Event kann beendet werden.</div>';
        return;
    }

    const items = (checklist.blockers || [])
        .map(function (b) {
            return "<li>" + String(b.message || b) + "</li>";
        })
        .join("");
    el.innerHTML =
        '<div class="close-alert close-alert-warn">' +
        "<strong>Noch offen vor dem Abschluss:</strong>" +
        "<ul style=\"margin:8px 0 0 18px\">" + items + "</ul>" +
        "</div>";
}

function renderCashiers() {
    const wrap = document.getElementById("cashiersList");
    const section = document.getElementById("sectionCashiers");
    if (!wrap || !checklist) return;

    const rows = (checklist.cashiers || []).filter(function (c) {
        return c.needs_closing_cash;
    });

    if (!rows.length) {
        section.style.display = "none";
        return;
    }
    section.style.display = "block";
    wrap.innerHTML = "";

    rows.forEach(function (c) {
        const diff =
            c.closing_cash != null
                ? Number(c.cash_difference || 0)
                : null;
        const diffLine =
            diff !== null
                ? '<div class="cashier-meta">Differenz (Ist − Soll): <strong>' +
                  euro(diff) +
                  "</strong>" +
                  (Math.abs(diff) > 0.01
                      ? " <span>(z. B. Kartenzahlung oder Trinkgeld)</span>"
                      : "") +
                  "</div>"
                : "";

        const row = document.createElement("div");
        row.className = "cashier-row";
        row.innerHTML =
            '<div class="cashier-row-head">' +
            "<strong>" + String(c.cashier_name || "-") + "</strong>" +
            '<span class="cashier-badge ' + (c.missing_closing_cash ? "missing" : "ok") + '">' +
            (c.role === "station" ? "Theke" : "Bedienung") +
            (c.missing_closing_cash ? " · fehlt" : " · erfasst") +
            "</span></div>" +
            '<div class="cashier-meta">Wechselgeld Start: ' + euro(c.opening_cash) +
            " · Bar-Umsatz: " + euro(c.cash_total_amount) +
            (Number(c.card_total_amount || 0) > 0.0001
                ? " · Digital: " + euro(c.card_total_amount)
                : "") +
            "<br>Soll-Inhalt Kasse (Bar): <strong>" + euro(c.cash_should_amount) + "</strong></div>" +
            diffLine +
            '<div class="cashier-input-row">' +
            '<label for="closing_' + c.user_id + '">Schlussbestand (gezählt)</label>' +
            '<input id="closing_' + c.user_id + '" inputmode="decimal" placeholder="z. B. 698,50" value="' +
            formatMoneyInput(c.closing_cash) +
            '">' +
            "</div>";
        wrap.appendChild(row);
    });
}

function renderOpenOrders() {
    const wrap = document.getElementById("openOrdersList");
    const section = document.getElementById("sectionOrders");
    if (!wrap || !checklist) return;

    const rows = checklist.open_orders || [];
    if (!rows.length) {
        section.style.display = "none";
        return;
    }
    section.style.display = "block";

    let html =
        '<div class="close-list"><table><thead><tr>' +
        "<th>Order</th><th>Tisch</th><th>Bedienung</th><th>Offen</th>" +
        "</tr></thead><tbody>";
    rows.forEach(function (o) {
        html +=
            "<tr><td>#" + o.order_number + "</td>" +
            "<td>" + (o.table_name || "-") + "</td>" +
            "<td>" + (o.waiter_name || "-") + "</td>" +
            "<td>" + euro(o.open_amount) + "</td></tr>";
    });
    html += "</tbody></table></div>";
    wrap.innerHTML = html;
}

function renderOpenTabs() {
    const wrap = document.getElementById("openTabsList");
    const section = document.getElementById("sectionTabs");
    if (!wrap || !checklist) return;

    const rows = checklist.open_tabs || [];
    if (!rows.length) {
        section.style.display = "none";
        return;
    }
    section.style.display = "block";

    let html =
        '<div class="close-list"><table><thead><tr>' +
        "<th>Deckel</th><th>Offen</th>" +
        "</tr></thead><tbody>";
    rows.forEach(function (t) {
        html +=
            "<tr><td>" + String(t.name || "-") + "</td>" +
            "<td>" + euro(t.balance) + "</td></tr>";
    });
    html += "</tbody></table></div>";
    wrap.innerHTML = html;
}

function renderAll() {
    if (!checklist) return;
    document.getElementById("eventTitle").textContent =
        "Event #" + checklist.event_id + " – " + (checklist.event_name || "");
    const statsLink = document.getElementById("statsLink");
    if (statsLink) {
        statsLink.href = "admin_stats.html?event_id=" + checklist.event_id;
        statsLink.style.display = "inline-block";
    }
    renderBlockers();
    renderCashiers();
    renderOpenOrders();
    renderOpenTabs();
    const btn = document.getElementById("btnFinalize");
    if (btn) {
        if (checklist.event_status !== "active") {
            btn.disabled = true;
            btn.textContent = "Event bereits beendet";
        } else {
            btn.textContent = "Event jetzt beenden";
            btn.disabled = !checklist.can_close;
        }
    }
}

async function loadChecklist() {
    const qs = eventId ? ("?event_id=" + encodeURIComponent(eventId)) : "";
    const res = await fetch(API + "/admin/events/close-checklist" + qs);
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        throw new Error(data.error || ("Laden fehlgeschlagen (" + res.status + ")"));
    }
    checklist = data;
    eventId = data.event_id;
    renderAll();
}

async function saveClosingCash() {
    if (!checklist || !eventId) return;
    const payload = [];
    (checklist.cashiers || []).forEach(function (c) {
        if (!c.needs_closing_cash) return;
        const input = document.getElementById("closing_" + c.user_id);
        if (!input) return;
        const val = parseMoneyInput(input.value);
        if (val === null) return;
        payload.push({ user_id: c.user_id, closing_cash: val });
    });
    if (!payload.length) {
        alert("Bitte mindestens einen Schlussbestand eintragen.");
        return;
    }
    const res = await fetch(API + "/admin/events/close-cashiers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id: eventId, cashiers: payload }),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        alert(data.error || "Speichern fehlgeschlagen");
        return;
    }
    checklist = data.checklist || checklist;
    renderAll();
}

async function finalizeEvent() {
    if (!eventId || !checklist || !checklist.can_close) return;
    if (!confirm("Event wirklich beenden?")) return;

    const res = await fetch(API + "/admin/events/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id: eventId }),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
        if (data.checklist) {
            checklist = data.checklist;
            renderAll();
        }
        alert(data.error || "Event konnte nicht beendet werden");
        return;
    }
    alert("Event wurde beendet.");
    window.location.href = "admin.html";
}

eventId = getEventIdFromUrl();
loadChecklist().catch(function (e) {
    showError(e.message || String(e));
});
