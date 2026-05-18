#!/bin/bash
set -euo pipefail

# Minimal GUI entry point for configuring WiFi on Raspberry Pi OS Desktop.
# Prefers NetworkManager editor; falls back to wpa_gui if installed.

if command -v nm-connection-editor >/dev/null 2>&1; then
  nm-connection-editor
  exit 0
fi

if command -v wpa_gui >/dev/null 2>&1; then
  wpa_gui
  exit 0
fi

echo "Kein WLAN-GUI Tool gefunden. Bitte NetworkManager installieren (nm-connection-editor) oder wpa_gui." >&2
exit 1

