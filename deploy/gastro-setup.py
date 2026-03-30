#!/usr/bin/env python3
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


API_PORT = int(os.environ.get("GASTRO_SETUP_PORT", "9090"))
WIFI_DEV = os.environ.get("GASTRO_WIFI_DEV", "wlan0")
CREDS_PATH = os.environ.get("GASTRO_SETUP_CREDS", "/opt/gastro-system/data/gastro-setup.json")


HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
  <title>Gastro-Setup</title>
  <style>
    body{margin:0;background:#111;color:#fff;font-family:Arial,sans-serif}
    header{background:#1c1c1c;padding:14px 12px;text-align:center}
    h1{margin:0;font-size:20px}
    .wrap{padding:12px;display:flex;flex-direction:column;gap:12px}
    .card{background:#1c1c1c;border-radius:14px;padding:12px}
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
    @media (min-width:680px){.grid{grid-template-columns:repeat(3,1fr)}}
    button{border:none;border-radius:12px;padding:14px 12px;font-size:16px;font-weight:700;color:#fff;background:#2ecc71;cursor:pointer}
    button.secondary{background:#333}
    input{width:100%;box-sizing:border-box;border:1px solid #333;border-radius:12px;background:#111;color:#fff;padding:14px 12px;font-size:16px}
    .row{display:flex;gap:10px}
    .row > *{flex:1}
    .small{font-size:13px;color:#ddd;line-height:1.35}
    .net{background:#121212;border:1px solid #2a2a2a}
    .net b{display:block;font-size:16px}
    .net span{display:block;color:#ddd;font-size:13px;margin-top:6px}
  </style>
</head>
<body>
  <header><h1>Gastro-Setup</h1></header>
  <div class="wrap">
    <div class="card small">
      Hier kannst du den Pi mit einem WLAN verbinden. Danach startet das Gastro-System automatisch (Backend/Frontend/Tunnel).
      <br/>Hinweis: Wenn du dich hier verbunden hast, öffne diese Seite erneut, falls dein Handy automatisch auf Mobilfunk wechselt.
    </div>

    <div class="card">
      <div class="row">
        <button class="secondary" onclick="scan()">WLANs suchen</button>
        <button class="secondary" onclick="location.reload()">Neu laden</button>
      </div>
    </div>

    <div class="card">
      <div id="nets" class="grid"></div>
    </div>

    <div class="card">
      <div class="small" style="margin-bottom:8px">Manuell verbinden</div>
      <input id="ssid" placeholder="SSID" />
      <div style="height:8px"></div>
      <input id="psk" placeholder="Passwort" type="password" />
      <div style="height:10px"></div>
      <div class="row">
        <button onclick="connectManual()">Verbinden</button>
        <button class="secondary" onclick="restartGastro()">Gastro neu starten</button>
      </div>
      <div id="msg" class="small" style="margin-top:10px"></div>
    </div>
  </div>

<script>
async function api(path, body){
  const opts = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)} : {};
  const r = await fetch(path, opts);
  const t = await r.text();
  try { return {ok:r.ok, data: JSON.parse(t)} } catch { return {ok:r.ok, data:t} }
}
function setMsg(s){ document.getElementById('msg').textContent = s || ''; }

async function scan(){
  setMsg('Suche WLANs...');
  const r = await api('/api/scan');
  if(!r.ok){ setMsg('Scan fehlgeschlagen'); return; }
  const nets = Array.isArray(r.data) ? r.data : [];
  const wrap = document.getElementById('nets');
  wrap.innerHTML = '';
  nets.forEach(n => {
    const b = document.createElement('button');
    b.className = 'net';
    b.style.background = '#121212';
    b.style.border = '1px solid #2a2a2a';
    b.onclick = () => { document.getElementById('ssid').value = n.ssid; document.getElementById('psk').focus(); };
    b.innerHTML = `<b>${n.ssid || '(ohne Name)'}</b><span>Signal: ${n.signal}%</span>`;
    wrap.appendChild(b);
  });
  setMsg(nets.length ? 'WLANs geladen. Tippe eins an, um SSID zu übernehmen.' : 'Keine WLANs gefunden.');
}

async function connectManual(){
  const ssid = document.getElementById('ssid').value.trim();
  const psk = document.getElementById('psk').value;
  if(!ssid){ alert('SSID fehlt'); return; }
  setMsg('Verbinde...');
  const r = await api('/api/connect', {ssid, psk});
  setMsg(r.ok ? 'Verbunden. Starte Gastro...' : ('Fehler: ' + (r.data && r.data.error ? r.data.error : 'connect failed')));
}

async function restartGastro(){
  setMsg('Starte Gastro neu...');
  const r = await api('/api/restart', {});
  setMsg(r.ok ? 'Restart ausgelöst.' : 'Restart fehlgeschlagen.');
}

scan();
</script>
</body>
</html>
"""


def sh(cmd: list[str], timeout: int = 25) -> tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
    return p.returncode, p.stdout, p.stderr


def has_nmcli() -> bool:
    return sh(["/usr/bin/env", "bash", "-lc", "command -v nmcli >/dev/null 2>&1"])[0] == 0


def scan_wifi() -> list[dict]:
    if not has_nmcli():
        return []
    code, out, _ = sh(["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list", "ifname", WIFI_DEV], timeout=25)
    if code != 0:
        return []
    nets = []
    for line in out.splitlines():
        if not line.strip():
            continue
        ssid, signal = (line.split(":", 1) + ["0"])[:2]
        ssid = ssid.strip()
        if not ssid:
            continue
        try:
            sig = int(signal.strip() or "0")
        except Exception:
            sig = 0
        nets.append({"ssid": ssid, "signal": sig})
    # dedupe by ssid with best signal
    best = {}
    for n in nets:
        s = n["ssid"]
        if s not in best or n["signal"] > best[s]["signal"]:
            best[s] = n
    return sorted(best.values(), key=lambda x: x["signal"], reverse=True)[:30]


def connect_wifi(ssid: str, psk: str) -> tuple[bool, str]:
    if not has_nmcli():
        return False, "nmcli not installed"
    if not ssid:
        return False, "ssid required"
    con_name = f"gastro-{ssid}"
    # try to connect (will create/update connection)
    cmd = ["nmcli", "dev", "wifi", "connect", ssid, "password", psk, "name", con_name]
    code, out, err = sh(cmd, timeout=40)
    if code != 0:
        # attempt without password (open wifi)
        cmd2 = ["nmcli", "dev", "wifi", "connect", ssid, "name", con_name]
        code2, out2, err2 = sh(cmd2, timeout=40)
        if code2 != 0:
            return False, (err2.strip() or err.strip() or "connect failed")
    # ensure autoconnect
    sh(["nmcli", "con", "modify", con_name, "connection.autoconnect", "yes", "connection.autoconnect-priority", "0"], timeout=20)
    return True, "ok"


def restart_gastro() -> bool:
    code, _, _ = sh(["/usr/bin/env", "bash", "-lc", "sudo systemctl restart gastro-backend.service gastro-frontend.service gastro-cloudflared.service"], timeout=30)
    return code == 0


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict | list):
        b = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/" or p == "/index.html":
            b = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if p == "/api/scan":
            self._json(200, scan_wifi())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        ln = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(ln) if ln > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}

        if p == "/api/connect":
            ssid = str(data.get("ssid") or "").strip()
            psk = str(data.get("psk") or "")
            ok, msg = connect_wifi(ssid, psk)
            if not ok:
                self._json(400, {"error": msg})
                return
            # give NM a moment, then restart gastro
            time.sleep(2.0)
            restart_gastro()
            self._json(200, {"status": "ok"})
            return

        if p == "/api/restart":
            ok = restart_gastro()
            self._json(200 if ok else 500, {"status": "ok" if ok else "error"})
            return

        self._json(404, {"error": "not found"})


def main():
    srv = HTTPServer(("0.0.0.0", API_PORT), Handler)
    print(f"gastro-setup listening on :{API_PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()

