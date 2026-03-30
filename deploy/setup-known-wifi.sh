#!/bin/bash
set -euo pipefail

# Adds/updates known WiFi networks using NetworkManager.
# Does NOT hardcode credentials; prompts interactively.
#
# Usage on Pi:
#   /opt/gastro-system/deploy/setup-known-wifi.sh "SSID1" "SSID2"
#
# Then the autoswitch timer will prefer the strongest known SSID.

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli not found. Please enable NetworkManager on Raspberry Pi OS." >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Usage: $0 <SSID...>" >&2
  exit 1
fi

for SSID in "$@"; do
  echo "Configuring SSID: $SSID"
  read -rsp "Password for '$SSID': " PSK
  echo

  CON_NAME="gastro-$SSID"

  if nmcli -t -f NAME con show | grep -Fxq "$CON_NAME"; then
    nmcli con modify "$CON_NAME" 802-11-wireless.ssid "$SSID" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "$PSK" connection.autoconnect yes connection.autoconnect-priority 0
  else
    nmcli dev wifi connect "$SSID" password "$PSK" name "$CON_NAME" || true
    nmcli con modify "$CON_NAME" connection.autoconnect yes connection.autoconnect-priority 0
  fi
done

echo "Done. Known networks installed."

