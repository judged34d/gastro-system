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

let users = [];

async function loadUsers() {
    const errEl = document.getElementById("error");
    if (errEl) errEl.innerText = "";
    let res;
    const fetchOpts = { cache: "no-store" };
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
        fetchOpts.signal = AbortSignal.timeout(20000);
    }
    try {
        res = await fetch(API + "/users", fetchOpts);
    } catch (e) {
        var hint = e && e.name === "AbortError" ? "Zeitüberschreitung (20s)" : "Netzwerkfehler";
        if (errEl) {
            errEl.innerText = hint + " (" + API + "/users). Bei :8000 auf mpbin: Strg+F5 oder Cache leeren.";
        }
        return;
    }
    if (!res.ok) {
        if (errEl) errEl.innerText = "Server-Fehler (" + res.status + ").";
        return;
    }
    try {
        users = await res.json();
    } catch (e) {
        if (errEl) errEl.innerText = "Ungültige Antwort vom Server.";
        return;
    }
    if (!Array.isArray(users)) {
        users = [];
    }

    const select = document.getElementById("user");
    select.innerHTML = "<option value=''>-- wählen --</option>";

    users
        .filter(u => (u.role !== "admin") && String(u.name || "").toLowerCase() !== "admin")
        .forEach(u => {
        const opt = document.createElement("option");
        opt.value = u.id;

        if (u.role === "waiter") {
            opt.text = u.name + " (Bedienung)";
        } else if (u.role === "station") {
            opt.text = u.name + " (Theke)";
        } else {
            opt.text = u.name;
        }

        select.add(opt);
    });
}

function login() {
    const userId = document.getElementById("user").value;
    const input = document.getElementById("pin").value;

    // NORMAL LOGIN
    const user = users.find(u => u.id == userId);

    if (!user || user.pin !== input) {
        document.getElementById("error").innerText = "Falsche PIN";
        return;
    }

    localStorage.setItem("user_id", user.id);
    localStorage.setItem("user_name", user.name);
    localStorage.setItem("role", user.role);

    if (user.role === "waiter") {
        window.location.href = "tables.html";
    } else {
        window.location.href = "kitchen.html";
    }
}

function goToAdmin() {
    window.location.assign("admin.html");
}

function openOrderStatusViewer() {
    window.location.assign("order_status.html");
}

loadUsers().catch(function () {});
