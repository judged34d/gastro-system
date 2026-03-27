const API = "http://192.168.0.165:8000";

const userId = localStorage.getItem("user_id");
const userName = localStorage.getItem("user_name");

document.getElementById("username").innerText = userName;

async function loadTables() {
    const res = await fetch(API + "/waiter/" + userId + "/tables");
    const tables = await res.json();

    const container = document.getElementById("tables");

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

loadTables();
