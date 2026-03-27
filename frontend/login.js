const API = "http://192.168.0.165:8000";

async function loadUsers() {
    const res = await fetch(API + "/users");
    const users = await res.json();

    const select = document.getElementById("user");

    users
        .filter(u => u.role === "waiter")
        .forEach(u => {
            const opt = document.createElement("option");
            opt.value = u.id;
            opt.text = u.name;
            select.add(opt);
        });
}

async function login() {
    const userId = document.getElementById("user").value;
    const pin = document.getElementById("pin").value;

    const res = await fetch(API + "/users");
    const users = await res.json();

    const user = users.find(u => u.id == userId);

    if (!user || user.pin !== pin) {
        document.getElementById("error").innerText = "Falsche PIN";
        return;
    }

    // Login speichern
    localStorage.setItem("user_id", user.id);
    localStorage.setItem("user_name", user.name);

    window.location.href = "tables.html";
}

loadUsers();
