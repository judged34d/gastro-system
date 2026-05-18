#!/bin/bash
set -euo pipefail

# Chooses the strongest known gastro-* connection and activates it.
# Designed to mimic "phone-like" behavior without static priorities.

if ! command -v nmcli >/dev/null 2>&1; then
  exit 0
fi

DEV="${DEV:-wlan0}"

active_ssid="$(nmcli -t -f DEVICE,STATE,CONNECTION dev status | awk -F: -v d="$DEV" '$1==d {print $3}')"

# scan visible WiFi networks and select best among SSIDs we have a gastro-* connection for
best=""
best_signal=-1

while IFS=: read -r ssid signal; do
  [ -z "$ssid" ] && continue
  con="gastro-$ssid"
  if nmcli -t -f NAME con show | grep -Fxq "$con"; then
    if [ "${signal:-0}" -gt "$best_signal" ]; then
      best_signal="${signal:-0}"
      best="$con"
    fi
  fi
done < <(nmcli -t -f SSID,SIGNAL dev wifi list ifname "$DEV" | sed 's/\\:/:/g')

if [ -n "$best" ] && [ "$best" != "$active_ssid" ]; then
  nmcli con up "$best" >/dev/null 2>&1 || true
fi

