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

const ADMIN_PASSWORD = "Passwort";
let featureFlags = {};
let singleTerminalMode = false;
let customIcons = [];

function checkLogin() {
    const input = document.getElementById("adminPass").value;
    if (input === ADMIN_PASSWORD) {
        document.getElementById("loginOverlay").style.display = "none";
        document.getElementById("settingsContent").style.display = "block";
        sessionStorage.setItem("gastro_admin_ok", "1");
        load();
    } else {
        document.getElementById("loginError").innerText = "Falsches Passwort";
    }
}

document.addEventListener("DOMContentLoaded", function () {
    if (sessionStorage.getItem("gastro_admin_ok") === "1") {
        document.getElementById("loginOverlay").style.display = "none";
        document.getElementById("settingsContent").style.display = "block";
        load();
    }
    const pw = document.getElementById("adminPass");
    if (pw) {
        pw.addEventListener("keydown", function (ev) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                checkLogin();
            }
        });
    }
});

async function load() {
    const f = await fetch(API + "/admin/features").then(r => r.json()).catch(() => ({}));
    featureFlags = (f && f.features) ? f.features : {};
    singleTerminalMode = !!(f && f.single_terminal_mode);
    renderAppSettings();
    renderBetaSettings();
    renderLayoutSettings();

    customIcons = await fetch(API + "/admin/icons").then(r => r.json()).catch(() => []);
    renderIconLibrary();
}

function renderAppSettings() {
    const cb = document.getElementById("single_terminal_mode");
    if (cb) cb.checked = !!singleTerminalMode;
}

function renderBetaSettings() {
    const cb = document.getElementById("beta_cash_calculator");
    if (cb) cb.checked = !!featureFlags.beta_cash_calculator;
}

function renderLayoutSettings() {
    const sel = document.getElementById("layout_preset");
    const preset = (window.GastroLayout && window.GastroLayout.getStoredPreset)
        ? window.GastroLayout.getStoredPreset()
        : "auto";
    if (sel) sel.value = preset;
    const labels = { auto: "Automatisch", phone: "Handy", tablet: "Tablet", wall: "Wanddisplay" };
    const eff = (window.GastroLayout && window.GastroLayout.getEffectiveLayout)
        ? window.GastroLayout.getEffectiveLayout()
        : "–";
    const effEl = document.getElementById("layout_effective_label");
    const preEl = document.getElementById("layout_preset_label");
    if (effEl) effEl.textContent = labels[eff] || eff;
    if (preEl) preEl.textContent = labels[preset] || preset;
}

function saveLayoutSettings() {
    const sel = document.getElementById("layout_preset");
    const value = sel ? sel.value : "auto";
    if (window.GastroLayout && window.GastroLayout.setPreset) {
        window.GastroLayout.setPreset(value);
    } else {
        try {
            localStorage.setItem("gastro_layout_preset", value);
        } catch (_) {}
    }
    renderLayoutSettings();
    alert("Layout-Preset für dieses Gerät gespeichert.");
}

async function saveAppSettings() {
    const body = {
        single_terminal_mode: !!(document.getElementById("single_terminal_mode")?.checked),
        features: featureFlags
    };
    const res = await fetch(API + "/admin/features", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Einstellungen konnten nicht gespeichert werden.");
        return;
    }
    singleTerminalMode = !!data.single_terminal_mode;
    featureFlags = data.features || featureFlags;
    renderAppSettings();
    alert("Betriebs-Einstellungen gespeichert.");
}

async function saveBetaSettings() {
    const body = {
        single_terminal_mode: singleTerminalMode,
        features: {
            beta_cash_calculator: !!(document.getElementById("beta_cash_calculator")?.checked)
        }
    };
    const res = await fetch(API + "/admin/features", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Beta-Einstellungen konnten nicht gespeichert werden.");
        return;
    }
    featureFlags = data.features || body.features;
    renderBetaSettings();
    alert("Beta-Einstellungen gespeichert.");
}

function iconFullUrl(url) {
    if (!url) return "";
    if (/^https?:\/\//i.test(url)) return url;
    return API.replace(/\/$/, "") + (url.startsWith("/") ? url : "/" + url);
}

function renderIconLibrary() {
    const box = document.getElementById("iconLibrary");
    if (!box) return;
    if (!customIcons.length) {
        box.innerHTML = "<p class='settings-hint'>Noch keine eigenen Icons hochgeladen.</p>";
        return;
    }
    box.innerHTML = "";
    customIcons.forEach(icon => {
        const card = document.createElement("div");
        card.className = "icon-card";
        card.innerHTML = `
            <img src="${iconFullUrl(icon.url)}" alt="">
            <div class="icon-card-name">${icon.name}</div>
            <button type="button" class="deleteBtn" data-id="${icon.id}">Löschen</button>
        `;
        card.querySelector("button").onclick = () => deleteCustomIcon(icon.id);
        box.appendChild(card);
    });
}

async function uploadCustomIcon() {
    const name = document.getElementById("icon_upload_name").value.trim();
    const fileInput = document.getElementById("icon_upload_file");
    const file = fileInput && fileInput.files && fileInput.files[0];
    if (!file) {
        alert("Bitte eine Bilddatei wählen.");
        return;
    }
    const fd = new FormData();
    fd.append("name", name || file.name);
    fd.append("file", file);
    const res = await fetch(API + "/admin/icons/upload", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Upload fehlgeschlagen");
        return;
    }
    document.getElementById("icon_upload_name").value = "";
    if (fileInput) fileInput.value = "";
    alert("Icon gespeichert.");
    load();
}

async function deleteCustomIcon(id) {
    if (!confirm("Icon wirklich löschen? (Nur möglich, wenn kein Artikel es nutzt.)")) return;
    const res = await fetch(API + "/admin/icons/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Löschen fehlgeschlagen");
        return;
    }
    load();
}
