#!/bin/bash
set -euo pipefail

sudo systemctl restart gastro-backend.service gastro-frontend.service gastro-cloudflared.service
sleep 1
sudo systemctl --no-pager -l status gastro-backend.service gastro-frontend.service gastro-cloudflared.service || true

