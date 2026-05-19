"""Erzeugt nach der Installation die Nutzungsanleitung (HTML)."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path


def _e(s: object) -> str:
    return escape(str(s) if s is not None else "")


def build_handbook_html(ctx: dict) -> str:
    root = _e(ctx.get("install_dir", ""))
    lan = _e(ctx.get("lan_ip", "127.0.0.1"))
    fp = int(ctx.get("frontend_port", 8081))
    bp = int(ctx.get("backend_port", 8000))
    cf = ctx.get("cloudflare") or {}
    cf_on = bool(cf.get("enabled"))
    app_h = _e(cf.get("app_hostname", ""))
    api_h = _e(cf.get("api_hostname", ""))
    dt = _e(ctx.get("installed_at", datetime.now().strftime("%d.%m.%Y %H:%M")))
    autostart = "Ja" if ctx.get("autostart") else "Nein"
    shortcut = "Ja" if ctx.get("desktop_shortcut") else "Nein"
    panel = _e(ctx.get("control_panel_cmd", ""))

    lan_fe = f"http://{lan}:{fp}"
    lan_api = f"http://{lan}:{bp}"
    local_fe = f"http://127.0.0.1:{fp}"
    local_api = f"http://127.0.0.1:{bp}"

    cf_block = ""
    if cf_on and app_h and api_h:
        cf_block = f"""
    <h2>Internet (Cloudflare Tunnel)</h2>
    <table>
      <tr><th>Zweck</th><th>URL</th></tr>
      <tr><td>Bedienoberfläche (HTTPS)</td><td><a href="https://{app_h}">https://{app_h}</a></td></tr>
      <tr><td>API (HTTPS)</td><td><a href="https://{api_h}/health">https://{api_h}/health</a></td></tr>
    </table>
    <p class="note">Tunnel-Name: {_e(cf.get('tunnel_name', ''))}. Tunnel im Control Panel mit „Tunnel verbinden“ starten, falls nicht per Autostart aktiv.</p>
"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gastro-System – Nutzungsanleitung</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; background: #f4f4f4; color: #222; margin: 0; padding: 24px 28px; line-height: 1.55; max-width: 920px; }}
  h1 {{ color: #2a6f2a; margin-top: 0; font-size: 1.75rem; }}
  h2 {{ color: #1f6fb2; margin-top: 1.75rem; font-size: 1.2rem; border-bottom: 2px solid #ddd; padding-bottom: 6px; }}
  h3 {{ font-size: 1.05rem; margin-top: 1.2rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; background: #fff; }}
  th, td {{ border: 1px solid #ccc; padding: 10px 12px; text-align: left; vertical-align: top; }}
  th {{ background: #e8e8e8; width: 28%; }}
  a {{ color: #1f6fb2; word-break: break-all; }}
  .meta {{ background: #fff; border: 1px solid #ccc; border-radius: 8px; padding: 14px 16px; margin-bottom: 20px; }}
  .note {{ background: #fff9e6; border-left: 4px solid #e6a700; padding: 10px 12px; margin: 12px 0; }}
  ol li {{ margin-bottom: 0.45rem; }}
  code {{ background: #eee; padding: 2px 6px; border-radius: 4px; }}
  @media print {{ body {{ background: #fff; }} a {{ color: #000; text-decoration: none; }} }}
</style>
</head>
<body>
<h1>Gastro-System – Nutzungsanleitung</h1>
<div class="meta">
  <strong>Installation:</strong> {dt}<br>
  <strong>Installationsordner:</strong> {root}<br>
  <strong>LAN-IP dieses PCs:</strong> {lan}<br>
  <strong>Desktop-Verknüpfung:</strong> {shortcut}<br>
  <strong>Autostart nach Anmeldung:</strong> {autostart}<br>
  <strong>Control Panel:</strong> <code>{panel}</code>
</div>

<h2>Adressen (URLs)</h2>
<h3>Lokal an diesem PC</h3>
<table>
  <tr><th>Zweck</th><th>URL</th></tr>
  <tr><td>Bedienoberfläche</td><td><a href="{local_fe}/">{local_fe}/</a></td></tr>
  <tr><td>API Gesundheitscheck</td><td><a href="{local_api}/health">{local_api}/health</a></td></tr>
</table>

<h3>Im WLAN (Tablets / Handys im gleichen Netz)</h3>
<table>
  <tr><th>Zweck</th><th>URL</th></tr>
  <tr><td>Bedienoberfläche</td><td><a href="{lan_fe}/">{lan_fe}/</a></td></tr>
  <tr><td>API Gesundheitscheck</td><td><a href="{lan_api}/health">{lan_api}/health</a></td></tr>
</table>
<p class="note">Die LAN-IP muss auf dem Gerät erreichbar sein (gleiches WLAN, keine Gast-Isolation am Router).</p>
{cf_block}

<h2>Wichtige Seiten der Software</h2>
<table>
  <tr><th>Bereich</th><th>Pfad (an Frontend-URL anhängen)</th><th>Beschreibung</th></tr>
  <tr><td>Login / Start</td><td><code>index.html</code></td><td>Kellner-Login mit PIN, Einstieg in den Betrieb</td></tr>
  <tr><td>Mein Bereich</td><td><code>tables.html</code></td><td>Tische wählen, Bestellungen aufnehmen</td></tr>
  <tr><td>Bestellung</td><td><code>order.html?table=…</code></td><td>Artikelkacheln, Warenkorb, Bestellung senden</td></tr>
  <tr><td>Theke</td><td><code>kitchen.html</code></td><td>Theken-/Stationsmodus, Übersicht und Bestellaufnahme</td></tr>
  <tr><td>Terminal</td><td><code>terminal.html</code></td><td>Vereinfachte Oberfläche für Terminal/Kasse</td></tr>
  <tr><td>Deckel</td><td><code>tabs_overview.html</code></td><td>Offene Deckel / Rechnungen</td></tr>
  <tr><td>Admin</td><td><code>admin.html</code></td><td>Artikel, Kategorien, Benutzer, Einstellungen</td></tr>
  <tr><td>Bestellstatus</td><td><code>order_status.html</code></td><td>Anzeige für Gäste/Küche (Statusmonitor)</td></tr>
</table>
<p>Beispiel Theke im WLAN: <a href="{lan_fe}/kitchen.html">{lan_fe}/kitchen.html</a></p>

<h2>Erster Start nach der Installation</h2>
<ol>
  <li><strong>Control Panel öffnen</strong> – Desktop-Link „Gastro-System“ oder <code>gastro-host\\run-control-panel.cmd</code>.</li>
  <li><strong>„Gastro starten“</strong> – startet Backend (Port {bp}) und Frontend (Port {fp}).</li>
  <li>Im Browser prüfen: <a href="{local_api}/health">{local_api}/health</a> sollte <code>ok</code> melden.</li>
  <li>Bedienung testen: <a href="{local_fe}/">{local_fe}/</a> – Login mit im Admin angelegtem Benutzer.</li>
  <li>Bei Cloudflare-Tunnel: im Control Panel <strong>„Tunnel verbinden“</strong>, danach die HTTPS-URLs oben testen.</li>
</ol>

<h2>Tägliche Nutzung</h2>
<h3>Kellner</h3>
<ol>
  <li>Am Tablet im WLAN die Adresse <strong>{lan_fe}/</strong> öffnen (Lesezeichen setzen).</li>
  <li>Einloggen → Tisch wählen → Artikel antippen (Menge links oben an der Kachel, Mülltonne rechts zum Entfernen).</li>
  <li>Bestellung absenden – erscheint in Küche/Theke und Verwaltung.</li>
</ol>
<h3>Theke / Station</h3>
<ol>
  <li><code>kitchen.html</code> öffnen, Station wählen.</li>
  <li>„Bestellung aufnehmen“ – gleiche Kachelbedienung wie bei Kellnern.</li>
  <li>Offene Bestellungen in der Übersicht bearbeiten und abschließen.</li>
</ol>
<h3>Administration</h3>
<ol>
  <li><code>admin.html</code> – Speisekarte, Preise, Icons, Kellner und Tischplan pflegen.</li>
  <li>Änderungen sind sofort in der Bestelloberfläche sichtbar (ggf. Seite neu laden).</li>
</ol>

<h2>Control Panel – Funktionen</h2>
<ul>
  <li><strong>Gastro starten</strong> – Backend + Frontend</li>
  <li><strong>Tunnel verbinden</strong> – nur bei aktivem Cloudflare</li>
  <li><strong>Alles stoppen</strong> – beendet Dienste und Tunnel</li>
  <li>Statuszeilen zeigen, ob Backend, Datenbank, Frontend und Cloudflared laufen</li>
</ul>

<h2>Protokolle &amp; Daten</h2>
<ul>
  <li>Datenbank: <code>{root}\\data\\database.db</code></li>
  <li>Konfiguration: <code>{root}\\gastro-host\\config.cmd</code>, <code>{root}\\data\\host-config.json</code></li>
  <li>Logs: <code>{root}\\data\\backend.log</code>, <code>frontend.log</code>, ggf. <code>cloudflared.log</code></li>
</ul>

<h2>Häufige Probleme</h2>
<ul>
  <li><strong>Seite lädt nicht im WLAN</strong> – Gastro gestartet? Richtige LAN-IP? Firewall für Port {fp}/{bp} am Server-PC erlauben.</li>
  <li><strong>API offline</strong> – Backend prüfen (<code>{local_api}/health</code>), Log <code>backend.log</code> lesen.</li>
  <li><strong>Cloudflare nicht erreichbar</strong> – Tunnel läuft? DNS/CNAME in Cloudflare? Hostnames in <code>cloudflared\\config.yml</code> stimmen?</li>
</ul>

<p style="margin-top:2rem;color:#666;font-size:0.9rem">Dokument automatisch erzeugt vom Gastro-System Setup. Ausdruck über Browser: Strg+P.</p>
</body>
</html>
"""


def write_install_handbook(root: Path, ctx: dict) -> Path:
    """Schreibt HTML-Nutzungsanleitung nach data/ und gibt den Pfad zurück."""
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    out = data / "Gastro-System-Nutzungsanleitung.html"
    if "installed_at" not in ctx:
        ctx = {**ctx, "installed_at": datetime.now().strftime("%d.%m.%Y %H:%M")}
    out.write_text(build_handbook_html(ctx), encoding="utf-8")
    return out.resolve()
