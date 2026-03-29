const API = "https://api.mpbin.de";

let users = [];

async function loadUsers() {
    const res = await fetch(API + "/users");
    users = await res.json();

    const select = document.getElementById("user");
    select.innerHTML = "<option value=''>-- wählen --</option>";

    // Admin fest hinzufügen
    const adminOpt = document.createElement("option");
    adminOpt.value = "admin";
    adminOpt.text = "Admin";
    select.add(adminOpt);

    users.forEach(u => {
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

    // ADMIN LOGIN
    if (userId === "admin") {
        if (input !== "Passwort") {
            document.getElementById("error").innerText = "Falsches Passwort";
            return;
        }

        window.location.href = "admin.html";
        return;
    }

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

loadUsers();
