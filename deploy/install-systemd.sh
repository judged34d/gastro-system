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

sudo systemctl daemon-reload
sudo systemctl enable gastro-backend.service gastro-frontend.service gastro-cloudflared.service
sudo systemctl restart gastro-backend.service gastro-frontend.service gastro-cloudflared.service

echo "Fertig. Status:"
sudo systemctl status gastro-backend.service --no-pager -l || true
sudo systemctl status gastro-frontend.service --no-pager -l || true
sudo systemctl status gastro-cloudflared.service --no-pager -l || true
