#!/bin/bash
set -euo pipefail

CF_BIN="$(command -v cloudflared || true)"
if [ -z "$CF_BIN" ]; then
  echo "cloudflared nicht im PATH gefunden. Bitte installieren oder PATH prüfen."
  exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$DIR/gastro-backend.service" /etc/systemd/system/
sudo cp "$DIR/gastro-frontend.service" /etc/systemd/system/

sudo sed "s|ExecStart=/usr/bin/cloudflared|ExecStart=$CF_BIN|" "$DIR/gastro-cloudflared.service" | sudo tee /etc/systemd/system/gastro-cloudflared.service >/dev/null

# helper scripts (used by systemd + desktop buttons)
sudo install -m 755 "$DIR/wait-for-internet.sh" /opt/gastro-system/deploy/wait-for-internet.sh
sudo install -m 755 "$DIR/restart-gastro.sh" /opt/gastro-system/deploy/restart-gastro.sh
sudo install -m 755 "$DIR/open-wifi-setup.sh" /opt/gastro-system/deploy/open-wifi-setup.sh
sudo install -m 755 "$DIR/setup-known-wifi.sh" /opt/gastro-system/deploy/setup-known-wifi.sh
sudo install -m 755 "$DIR/wifi-autoswitch.sh" /opt/gastro-system/deploy/wifi-autoswitch.sh
sudo cp "$DIR/gastro-wifi-autoswitch.service" /etc/systemd/system/
sudo cp "$DIR/gastro-wifi-autoswitch.timer" /etc/systemd/system/
sudo install -m 755 "$DIR/gastro-setup.py" /opt/gastro-system/deploy/gastro-setup.py
sudo install -m 755 "$DIR/gastro-setup-run.sh" /opt/gastro-system/deploy/gastro-setup-run.sh
sudo cp "$DIR/gastro-setup.service" /etc/systemd/system/

# desktop buttons (best effort)
if [ -d "/home/bestellung/Desktop" ] && [ -d "$DIR/desktop" ]; then
  sudo install -m 755 "$DIR/desktop/WLAN einstellen.desktop" "/home/bestellung/Desktop/WLAN einstellen.desktop" || true
  sudo install -m 755 "$DIR/desktop/Gastro System neu starten.desktop" "/home/bestellung/Desktop/Gastro System neu starten.desktop" || true
  sudo chown bestellung:bestellung "/home/bestellung/Desktop/WLAN einstellen.desktop" "/home/bestellung/Desktop/Gastro System neu starten.desktop" || true
fi

sudo systemctl daemon-reload
sudo systemctl enable gastro-backend.service gastro-frontend.service gastro-cloudflared.service
sudo systemctl enable gastro-wifi-autoswitch.timer
sudo systemctl enable gastro-setup.service
sudo systemctl restart gastro-backend.service gastro-frontend.service gastro-cloudflared.service
sudo systemctl start gastro-wifi-autoswitch.timer || true
sudo systemctl start gastro-setup.service || true

echo "Fertig. Status:"
sudo systemctl status gastro-backend.service --no-pager -l || true
sudo systemctl status gastro-frontend.service --no-pager -l || true
sudo systemctl status gastro-cloudflared.service --no-pager -l || true
