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
let printerStations = [];
let printerConfig = {};
let windowsPrinters = [];
let ticketAutoprint = false;

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
    await loadPrinterSettings();
    await loadTerminalHelp(false);

    customIcons = await fetch(API + "/admin/icons").then(r => r.json()).catch(() => []);
    renderIconLibrary();
}

function switchSettingsTab(name) {
    document.querySelectorAll(".settings-tab").forEach(btn => {
        btn.classList.toggle("is-active", btn.dataset.tab === name);
    });
    document.querySelectorAll(".settings-tab-panel").forEach(panel => {
        panel.classList.toggle("is-active", panel.id === "tab-" + name);
    });
    if (name === "terminal") loadTerminalHelp(true);
}

async function loadTerminalHelp(force) {
    const box = document.getElementById("terminalHelpSections");
    if (!box) return;
    const url = API + "/admin/terminal-help" + (force ? ("?t=" + Date.now()) : "");
    const data = await fetch(url, { cache: "no-store" }).then(r => r.json()).catch(() => null);
    if (!data) {
        box.innerHTML = "<p class='settings-hint'>Hilfe konnte nicht geladen werden.</p>";
        return;
    }
    const intro = document.getElementById("terminalHelpIntro");
    if (intro && data.intro) intro.textContent = data.intro;
    const upd = document.getElementById("terminalHelpUpdated");
    if (upd) upd.textContent = data.updated || "–";

    const sections = Array.isArray(data.sections) ? data.sections : [];
    box.innerHTML = "";
    sections.forEach((sec, si) => {
        const wrap = document.createElement("div");
        wrap.className = "term-help-section";
        wrap.innerHTML = "<h3></h3><p class='settings-hint'></p>";
        wrap.querySelector("h3").textContent = sec.title || ("Abschnitt " + (si + 1));
        wrap.querySelector("p").textContent = sec.hint || "";
        (sec.commands || []).forEach((cmd, ci) => {
            const block = document.createElement("div");
            block.className = "term-cmd-block";
            const label = document.createElement("div");
            label.className = "term-cmd-label";
            const span = document.createElement("span");
            span.textContent = cmd.label || "Befehl";
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "inlineBtn term-copy-btn";
            btn.textContent = "Kopieren";
            const pre = document.createElement("pre");
            pre.className = "term-cmd-pre";
            pre.textContent = cmd.code || "";
            btn.onclick = () => copyTerminalCommand(pre, btn);
            label.appendChild(span);
            label.appendChild(btn);
            block.appendChild(label);
            block.appendChild(pre);
            wrap.appendChild(block);
        });
        box.appendChild(wrap);
    });
}

async function copyTerminalCommand(preEl, btn) {
    const text = preEl ? preEl.textContent : "";
    if (!text) return;
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const range = document.createRange();
            range.selectNodeContents(preEl);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            document.execCommand("copy");
            sel.removeAllRanges();
        }
        const old = btn.textContent;
        btn.textContent = "Kopiert!";
        setTimeout(() => { btn.textContent = old; }, 1500);
    } catch (e) {
        alert("Kopieren fehlgeschlagen – Text manuell markieren.");
    }
}

async function loadPrinterSettings() {
    const data = await fetch(API + "/admin/printers").then(r => r.json()).catch(() => ({}));
    printerStations = Array.isArray(data.stations) ? data.stations : [];
    printerConfig = data.stations_config && typeof data.stations_config === "object"
        ? data.stations_config
        : {};
    windowsPrinters = Array.isArray(data.windows_printers) ? data.windows_printers : [];
    ticketAutoprint = !!data.autoprint;
    const ap = document.getElementById("ticket_autoprint");
    if (ap) ap.checked = ticketAutoprint;
    renderPrinterSettings();
}

function printerCfgFor(stationId) {
    const raw = printerConfig[String(stationId)] || {};
    return {
        enabled: !!raw.enabled,
        connection: raw.connection || "cups",
        host: raw.host || "",
        port: raw.port || (raw.connection === "cups" ? 631 : 9100),
        windows_name: raw.windows_name || "",
        queue_name: raw.queue_name || "",
        cups_user: raw.cups_user || "",
        cups_password: raw.cups_password || "",
        agent_url: raw.agent_url || "",
        copies: raw.copies || 1,
    };
}

function renderPrinterSettings() {
    const box = document.getElementById("printerStations");
    if (!box) return;
    if (!printerStations.length) {
        box.innerHTML = "<p class='settings-hint'>Keine Stationen im aktiven Event.</p>";
        return;
    }
    const winOpts = ['<option value="">– Windows-Drucker wählen –</option>']
        .concat(windowsPrinters.map(n =>
            `<option value="${String(n).replace(/"/g, "&quot;")}">${n}</option>`
        ))
        .join("");

    box.innerHTML = "";
    printerStations.forEach(st => {
        const cfg = printerCfgFor(st.id);
        const card = document.createElement("div");
        card.className = "printer-card";
        card.dataset.stationId = String(st.id);
        card.innerHTML = `
            <div class="printer-card-title">${st.name} <span class="settings-hint">(ID ${st.id})</span></div>
            <label class="settings-check">
                <input type="checkbox" class="p-enabled" ${cfg.enabled ? "checked" : ""}>
                Drucker für diese Station nutzen
            </label>
            <div class="row printer-row">
                <label>Verbindung:</label>
                <select class="p-connection">
                    <option value="cups">CUPS/Ubuntu freigegeben (Autodruck empfohlen)</option>
                    <option value="network">Netzwerk-Drucker (IP :9100)</option>
                    <option value="windows">Windows-Drucker am Host</option>
                    <option value="browser">Browser-Dialog (manuell, kein stiller Autodruck)</option>
                    <option value="file">Datei-Test (Host data/)</option>
                </select>
            </div>
            <div class="row printer-row p-agent" style="display:none">
                <label>Agent-URL:</label>
                <input class="p-agent-url" style="min-width:260px" value="${cfg.agent_url || ""}">
            </div>
            <div class="row printer-row p-cups">
                <label>Ubuntu-IP:</label>
                <input class="p-host" placeholder="192.168.0.50" value="${cfg.host || ""}">
                <label>Port:</label>
                <input class="p-port" type="number" style="width:70px" value="${cfg.port || 631}">
                <label>Warteschlange:</label>
                <input class="p-queue" placeholder="A795" value="${cfg.queue_name || ""}">
            </div>
            <div class="row printer-row p-cups">
                <label>Ubuntu-User:</label>
                <input class="p-cups-user" placeholder="(optional, gegen 0x0403)" value="${cfg.cups_user || ""}">
                <label>Passwort:</label>
                <input class="p-cups-pass" type="password" placeholder="(optional)" value="${cfg.cups_password || ""}">
            </div>
            <div class="row printer-row p-net">
                <label>IP:</label>
                <input class="p-host-net" placeholder="192.168.0.50" value="${cfg.connection === 'network' ? (cfg.host || '') : ''}">
                <label>Port:</label>
                <input class="p-port-net" type="number" style="width:80px" value="${cfg.connection === 'network' ? (cfg.port || 9100) : 9100}">
            </div>
            <div class="row printer-row p-win">
                <label>Windows:</label>
                <select class="p-windows">${winOpts}</select>
            </div>
            <div class="row printer-row">
                <label>Kopien:</label>
                <input class="p-copies" type="number" min="1" max="3" style="width:60px" value="${cfg.copies || 1}">
                <button type="button" class="inlineBtn p-test">Testbon</button>
            </div>
        `;
        const conn = card.querySelector(".p-connection");
        let cv = cfg.connection;
        if (cv === "station_agent" || cv === "agent" || cv === "local" || cv === "terminal") cv = "browser";
        conn.value = cv || "cups";
        const winSel = card.querySelector(".p-windows");
        if (cfg.windows_name) winSel.value = cfg.windows_name;
        const syncVis = () => {
            const v = conn.value;
            card.querySelector(".p-agent").style.display = "none";
            card.querySelector(".p-cups").style.display = v === "cups" ? "flex" : "none";
            card.querySelector(".p-net").style.display = v === "network" ? "flex" : "none";
            card.querySelector(".p-win").style.display = v === "windows" ? "flex" : "none";
        };
        conn.onchange = syncVis;
        syncVis();
        card.querySelector(".p-test").onclick = () => testPrinter(st.id, card);
        box.appendChild(card);
    });
}

function collectPrinterSettings() {
    const stations = {};
    document.querySelectorAll("#printerStations .printer-card").forEach(card => {
        const sid = card.dataset.stationId;
        const connection = card.querySelector(".p-connection")?.value || "cups";
        const host = connection === "network"
            ? (card.querySelector(".p-host-net")?.value || "").trim()
            : (card.querySelector(".p-host")?.value || "").trim();
        const port = connection === "network"
            ? Number(card.querySelector(".p-port-net")?.value || 9100)
            : Number(card.querySelector(".p-port")?.value || (connection === "cups" ? 631 : 9100));
        stations[sid] = {
            enabled: !!card.querySelector(".p-enabled")?.checked,
            connection,
            host,
            port,
            queue_name: (card.querySelector(".p-queue")?.value || "").trim(),
            cups_user: (card.querySelector(".p-cups-user")?.value || "").trim(),
            cups_password: card.querySelector(".p-cups-pass")?.value || "",
            windows_name: card.querySelector(".p-windows")?.value || "",
            agent_url: (card.querySelector(".p-agent-url")?.value || "").trim(),
            copies: Number(card.querySelector(".p-copies")?.value || 1),
        };
    });
    return {
        autoprint: !!document.getElementById("ticket_autoprint")?.checked,
        stations,
    };
}

async function savePrinterSettings() {
    const body = collectPrinterSettings();
    const res = await fetch(API + "/admin/printers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.error || "Speichern fehlgeschlagen");
        return;
    }
    printerConfig = data.stations_config || body.stations;
    ticketAutoprint = !!data.autoprint;
    const ap = document.getElementById("ticket_autoprint");
    if (ap) ap.checked = ticketAutoprint;
    alert("Drucker-Einstellungen gespeichert.");
}

async function testPrinter(stationId, card) {
    const connection = card.querySelector(".p-connection")?.value || "cups";
    const cfg = {
        enabled: true,
        connection,
        host: connection === "network"
            ? (card.querySelector(".p-host-net")?.value || "").trim()
            : (card.querySelector(".p-host")?.value || "").trim(),
        port: connection === "network"
            ? Number(card.querySelector(".p-port-net")?.value || 9100)
            : Number(card.querySelector(".p-port")?.value || (connection === "cups" ? 631 : 9100)),
        queue_name: (card.querySelector(".p-queue")?.value || "").trim(),
        cups_user: (card.querySelector(".p-cups-user")?.value || "").trim(),
        cups_password: card.querySelector(".p-cups-pass")?.value || "",
        windows_name: card.querySelector(".p-windows")?.value || "",
        agent_url: (card.querySelector(".p-agent-url")?.value || "").trim(),
        copies: 1,
    };
    if (cfg.connection === "browser") {
        // Testdruck über System-Druckdialog (Standarddrucker dieses Geraets)
        const w = window.open("", "_blank", "width=320,height=480");
        if (!w) {
            alert("Popup blockiert – bitte erlauben und erneut testen.");
            return;
        }
        w.document.open();
        w.document.write(
            "<!DOCTYPE html><html><head><title>Testbon</title><style>" +
            "@page{size:80mm auto;margin:4mm}" +
            "body{font-family:monospace;font-size:14px;width:72mm;margin:0;color:#000;background:#fff}" +
            "h1{font-size:22px;text-align:center;margin:8px 0}" +
            ".muted{color:#444;font-size:11px;text-align:center}" +
            "</style></head><body>" +
            "<div class='muted'>TEST GASTRO</div><h1>TEST BEDIENUNG</h1>" +
            "<div>Tisch: Test</div><div>Order: #0</div><hr>" +
            "<div>1x Testdruck OK</div><hr>" +
            "<div class='muted'>Laufzettel – kein Kassenbon</div>" +
            "</body></html>"
        );
        w.document.close();
        w.focus();
        // print() vom Opener aus – zuverlässiger als Script im Popup
        setTimeout(function () {
            try {
                w.print();
            } catch (e) {
                alert("Druckdialog konnte nicht geöffnet werden: " + e);
            }
        }, 300);
        return;
    }
    const res = await fetch(API + "/admin/printers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ station_id: stationId, config: cfg }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
        alert(data.error || data.hint || "Testdruck fehlgeschlagen");
        return;
    }
    alert("Testdruck OK → " + (data.target || data.hint || ""));
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
