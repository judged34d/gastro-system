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

const isTerminalCashier = !!(manageCtx && manageCtx.mode === "terminal_cashier_order");
const isStationCashier = !!(manageCtx && manageCtx.mode === "station_cashier_order");
const isStationMode = isTerminalCashier || isStationCashier;
const stationId = isStationMode ? Number(manageCtx.station_id || 0) : 0;
const stationOrderId = isStationMode ? Number(manageCtx.order_id || 0) : 0;
const userId = Number(localStorage.getItem("user_id") || 0);

document.getElementById("table").innerText = isStationMode
    ? ("Theke Order #" + (manageCtx.order_number || stationOrderId))
    : ("Tisch: " + tableName);

let items = {};
let selection = {};
let givenCents = 0;
let betaCashCalculatorEnabled = false;
let cashCalcOpen = false;
let actionBusy = false;

function formatPrice(v) {
    return v.toFixed(2).replace(".", ",") + " €";
}

function toCents(v) {
    return Math.round(Number(v || 0) * 100);
}

function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const merged = Object.assign({}, options || {}, { signal: controller.signal });
    return fetch(url, merged).finally(() => clearTimeout(timer));
}

function setActionBusy(busy, text) {
    let overlay = document.getElementById("manageBusyOverlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "manageBusyOverlay";
        overlay.style.position = "fixed";
        overlay.style.inset = "0";
        overlay.style.zIndex = "1200";
        overlay.style.display = "none";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.background = "rgba(0,0,0,0.55)";
        overlay.style.fontSize = "20px";
        overlay.style.fontWeight = "bold";
        overlay.style.textAlign = "center";
        overlay.style.padding = "20px";
        document.body.appendChild(overlay);
    }
    overlay.innerText = text || "Bitte warten...";
    overlay.style.display = busy ? "flex" : "none";
}

function currentPayTotal() {
    let payTotal = 0;
    Object.values(items).forEach(i => {
        payTotal += Number(selection[i.name] || 0) * Number(i.price || 0);
    });
    return payTotal;
}

function updateCashCalc(payTotal) {
    if (!betaCashCalculatorEnabled) return;
    const payCents = toCents(payTotal);
    const changeCents = givenCents - payCents;
    const givenEl = document.getElementById("givenAmount");
    const changeEl = document.getElementById("changeAmount");
    if (givenEl) givenEl.innerText = formatPrice(givenCents / 100);
    if (changeEl) changeEl.innerText = formatPrice(changeCents / 100);
}

function syncCashCalcVisibility() {
    const box = document.getElementById("cashCalc");
    const toggleBtn = document.getElementById("cashCalcToggleBtn");
    if (toggleBtn) {
        toggleBtn.style.display = betaCashCalculatorEnabled ? "block" : "none";
        toggleBtn.textContent = cashCalcOpen ? "Rechner ausblenden" : "Rechner";
        toggleBtn.setAttribute("aria-expanded", cashCalcOpen ? "true" : "false");
    }
    if (box) {
        box.style.display = betaCashCalculatorEnabled && cashCalcOpen ? "block" : "none";
    }
}

function toggleCashCalculator(forceOpen) {
    if (!betaCashCalculatorEnabled) return;
    if (forceOpen === true) {
        cashCalcOpen = true;
    } else if (forceOpen === false) {
        cashCalcOpen = false;
    } else {
        cashCalcOpen = !cashCalcOpen;
    }
    syncCashCalcVisibility();
    if (cashCalcOpen) {
        updateCashCalc(currentPayTotal());
    }
}

async function loadFeatureFlags() {
    try {
        const res = await fetch(API + "/features", { cache: "no-store" });
        const data = await res.json();
        const flags = data && data.features ? data.features : {};
        betaCashCalculatorEnabled = !!flags.beta_cash_calculator;
    } catch (_) {
        betaCashCalculatorEnabled = false;
    }
    if (!betaCashCalculatorEnabled) {
        cashCalcOpen = false;
    }
    syncCashCalcVisibility();
}

function addGiven(amount) {
    givenCents += toCents(amount);
    updateCashCalc(currentPayTotal());
}

function setGivenToPayTotal() {
    givenCents = toCents(currentPayTotal());
    updateCashCalc(currentPayTotal());
}

function clearGiven() {
    givenCents = 0;
    updateCashCalc(currentPayTotal());
}

async function load() {
    await loadFeatureFlags();
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
    updateCashCalc(payTotal);
}

function collectSelectedEntries() {
    let hasSelection = false;
    const entries = [];
    for (const name in items) {
        let qty = Number(selection[name] || 0);
        if (qty <= 0) continue;
        const src = items[name].entries || [];
        for (const e of src) {
            if (qty <= 0) break;
            const useQty = Math.min(qty, e.qty);
            if (useQty <= 0) continue;
            hasSelection = true;
            entries.push({
                order_id: e.order_id,
                order_item_id: e.id,
                quantity: useQty
            });
            qty -= useQty;
        }
    }
    return { hasSelection, entries };
}

async function pay() {
    if (actionBusy) return;
    let hasPayment = false;
    actionBusy = true;
    setActionBusy(true, "Zahlung wird verbucht...");

    for (const name in items) {
        let qtyToPay = selection[name];

        if (qtyToPay <= 0) continue;

        const entries = items[name].entries;

        for (const e of entries) {
            if (qtyToPay <= 0) break;

            const payQty = Math.min(qtyToPay, e.qty);

            if (payQty > 0) {
                hasPayment = true;

                const pres = await fetchWithTimeout(API + "/orders/" + e.order_id + "/pay-item", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        order_item_id: e.id,
                        quantity: payQty,
                        payment_type: "paid"
                    })
                }, 12000).catch(() => null);
                if (!pres) {
                    alert("Zahlung fehlgeschlagen (Verbindung unterbrochen).");
                    actionBusy = false;
                    setActionBusy(false);
                    return;
                }
                const pdata = await pres.json().catch(() => ({}));
                if (!pres.ok) {
                    alert(pdata.message || pdata.error || ("Zahlung fehlgeschlagen (" + pres.status + ")"));
                    actionBusy = false;
                    setActionBusy(false);
                    load();
                    return;
                }

                qtyToPay -= payQty;
            }
        }
    }

    if (!hasPayment) {
        actionBusy = false;
        setActionBusy(false);
        alert("Keine Auswahl getroffen");
        return;
    }

    actionBusy = false;
    setActionBusy(false);
    alert("Zahlung erfolgreich");
    clearGiven();
    load();
}

function payToTab() {
    const selected = collectSelectedEntries();
    const hasPayment = selected.hasSelection;
    const entriesToPay = selected.entries;
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

async function cancelItems() {
    if (actionBusy) return;
    const reasonEl = document.getElementById("cancelReason");
    const reason = (reasonEl && reasonEl.value) ? String(reasonEl.value) : "";
    if (!reason) {
        alert("Bitte einen Storno-Grund auswählen.");
        return;
    }
    const selected = collectSelectedEntries();
    if (!selected.hasSelection) {
        alert("Keine Auswahl getroffen");
        return;
    }
    if (!confirm("Ausgewählte Positionen wirklich stornieren?")) {
        return;
    }
    actionBusy = true;
    setActionBusy(true, "Storno wird verbucht...");

    for (const e of selected.entries) {
        const body = {
            order_item_id: e.order_item_id,
            quantity: e.quantity,
            reason: reason,
            created_by_role: isStationMode ? "station" : "waiter",
            created_by_user_id: isStationMode ? null : (userId || null),
            created_by_station_id: isStationMode ? (stationId || null) : null
        };
        const res = await fetchWithTimeout(API + "/orders/" + e.order_id + "/cancel-item", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        }, 12000).catch(() => null);
        if (!res) {
            alert("Storno fehlgeschlagen (Verbindung unterbrochen).");
            actionBusy = false;
            setActionBusy(false);
            return;
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            alert(data.message || data.error || ("Storno fehlgeschlagen (" + res.status + ")"));
            actionBusy = false;
            setActionBusy(false);
            load();
            return;
        }
    }

    actionBusy = false;
    setActionBusy(false);
    alert("Storno erfolgreich verbucht");
    if (reasonEl) reasonEl.value = "";
    load();
}

async function payPersonal() {
    if (actionBusy) return;
    const selected = collectSelectedEntries();
    actionBusy = true;
    setActionBusy(true, "Personal wird verbucht...");

    if (isStationMode) {
        if (!selected.hasSelection) {
            const res = await fetchWithTimeout(API + "/station/" + stationId + "/orders/" + stationOrderId + "/settle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ payment_type: "internal" })
            }, 12000).catch(() => null);
            actionBusy = false;
            setActionBusy(false);
            if (!res) {
                alert("Verbuchung fehlgeschlagen (Verbindung).");
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.message || data.error || "Personal-Verbuchung fehlgeschlagen");
                load();
                return;
            }
            alert("Als Personal verbucht (0 €)");
            localStorage.removeItem("order_manage_ctx");
            window.location.href = isTerminalCashier ? "terminal.html" : "kitchen.html";
            return;
        }
        for (const e of selected.entries) {
            const res = await fetchWithTimeout(API + "/orders/" + e.order_id + "/pay-item", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_item_id: e.order_item_id,
                    quantity: e.quantity,
                    payment_type: "internal"
                })
            }, 12000).catch(() => null);
            if (!res) {
                alert("Verbuchung fehlgeschlagen (Verbindung).");
                actionBusy = false;
                setActionBusy(false);
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.message || data.error || "Personal-Verbuchung fehlgeschlagen");
                actionBusy = false;
                setActionBusy(false);
                load();
                return;
            }
        }
    } else {
        if (!selected.hasSelection) {
            const orderIds = new Set();
            Object.values(items).forEach(i => {
                (i.entries || []).forEach(e => orderIds.add(e.order_id));
            });
            if (orderIds.size !== 1) {
                actionBusy = false;
                setActionBusy(false);
                alert("Bitte Positionen auswählen oder nur eine offene Order haben.");
                return;
            }
            const oid = [...orderIds][0];
            const res = await fetchWithTimeout(API + "/orders/" + oid + "/pay-internal", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            }, 12000).catch(() => null);
            actionBusy = false;
            setActionBusy(false);
            if (!res) {
                alert("Verbuchung fehlgeschlagen (Verbindung).");
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.message || data.error || "Personal-Verbuchung fehlgeschlagen");
                load();
                return;
            }
            alert("Als Personal verbucht (0 €)");
            load();
            return;
        }
        for (const e of selected.entries) {
            const res = await fetchWithTimeout(API + "/orders/" + e.order_id + "/pay-item", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_item_id: e.order_item_id,
                    quantity: e.quantity,
                    payment_type: "internal"
                })
            }, 12000).catch(() => null);
            if (!res) {
                alert("Verbuchung fehlgeschlagen (Verbindung).");
                actionBusy = false;
                setActionBusy(false);
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.message || data.error || "Personal-Verbuchung fehlgeschlagen");
                actionBusy = false;
                setActionBusy(false);
                load();
                return;
            }
        }
    }

    actionBusy = false;
    setActionBusy(false);
    alert("Als Personal verbucht (0 €)");
    load();
}

function cancel() {
    if (isTerminalCashier) {
        localStorage.removeItem("order_manage_ctx");
        window.location.href = "terminal.html";
    } else if (isStationCashier) {
        localStorage.removeItem("order_manage_ctx");
        window.location.href = "kitchen.html";
    } else {
        window.location.href = "my_orders.html";
    }
}

load();
