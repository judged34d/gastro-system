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

async function loadTables() {
    const res = await fetch(API + "/waiter/" + userId + "/tables");
    const tables = await res.json();

    const container = document.getElementById("tables");
    container.innerHTML = "";

    tables.forEach(t => {
        const div = document.createElement("div");
        div.classList.add("table-btn");
        div.innerText = t.name;

        div.onclick = () => {
            localStorage.setItem("table_id", t.id);
            localStorage.setItem("table_name", t.name);
            window.location.href = "order.html";
        };

        container.appendChild(div);
    });
}

function goToMyOrders() {
    window.location.href = "my_orders.html";
}

function openTabs() {
    localStorage.setItem("tabs_overview_ctx", JSON.stringify({
        return_to: "tables.html",
        role: "waiter",
        user_id: localStorage.getItem("user_id") || null
    }));
    window.location.href = "tabs_overview.html";
}

function confirmLogout() {
    if (window.confirm("Willst du wirklich ausloggen?")) {
        localStorage.removeItem("user_id");
        localStorage.removeItem("user_name");
        localStorage.removeItem("role");
        localStorage.removeItem("table_id");
        localStorage.removeItem("table_name");
        window.location.href = "login.html";
    }
}

loadTables();
