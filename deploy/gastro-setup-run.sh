#!/bin/bash
set -euo pipefail

DATA_DIR="/opt/gastro-system/data"
CREDS="$DATA_DIR/gastro-setup.json"
DESKTOP_DIR="/home/bestellung/Desktop"
DESKTOP_TXT="$DESKTOP_DIR/Gastro-Setup Zugangsdaten.txt"

if ! command -v nmcli >/dev/null 2>&1; then
  echo "NetworkManager (nmcli) not installed; setup hotspot disabled." >&2
  sleep 30
  exit 0
fi

mkdir -p "$DATA_DIR"

if [ ! -f "$CREDS" ]; then
  /usr/bin/python3 - <<'PY'
import json, os, secrets, string
path = "/opt/gastro-system/data/gastro-setup.json"
ssid = "Gastro-Setup"
alphabet = string.ascii_letters + string.digits
pw = "".join(secrets.choice(alphabet) for _ in range(12))
with open(path, "w", encoding="utf-8") as f:
    json.dump({"ssid": ssid, "password": pw, "port": 9090}, f)
print("created", path)
PY
  chmod 600 "$CREDS" || true
fi

SSID="$(/usr/bin/python3 -c 'import json;print(json.load(open("/opt/gastro-system/data/gastro-setup.json"))["ssid"])')"
PASS="$(/usr/bin/python3 -c 'import json;print(json.load(open("/opt/gastro-system/data/gastro-setup.json"))["password"])')"
PORT="$(/usr/bin/python3 -c 'import json;print(json.load(open("/opt/gastro-system/data/gastro-setup.json")).get("port",9090))')"

# If we already have a WiFi connection, do nothing (exit quickly).
ACTIVE_STATE="$(nmcli -t -f DEVICE,STATE dev status | awk -F: '$1=="wlan0"{print $2}')"
if [ "$ACTIVE_STATE" = "connected" ]; then
  exit 0
fi

# Create desktop "router sticker" (best effort).
if [ -d "$DESKTOP_DIR" ]; then
  cat > "$DESKTOP_TXT" <<EOF
Gastro-Setup Hotspot

SSID: $SSID
Passwort: $PASS

Setup-Seite:
http://10.42.0.1:$PORT

Hinweis:
Der Hotspot startet automatisch, wenn kein bekanntes WLAN verbunden ist.
EOF
  chown bestellung:bestellung "$DESKTOP_TXT" || true
  chmod 600 "$DESKTOP_TXT" || true
fi

# Start hotspot (NetworkManager "shared" mode uses 10.42.0.1 by default).
CON_NAME="gastro-setup-hotspot"
nmcli con down "$CON_NAME" >/dev/null 2>&1 || true
nmcli dev wifi hotspot ifname wlan0 ssid "$SSID" password "$PASS" name "$CON_NAME" >/dev/null 2>&1 || true

# Start setup web UI
export GASTRO_SETUP_PORT="$PORT"
exec /usr/bin/python3 /opt/gastro-system/deploy/gastro-setup.py

