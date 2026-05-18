#!/bin/bash
set -euo pipefail

# Wait until we have a working default route and can reach the internet.
# Must work without root privileges (ExecStartPre runs as User=bestellung).

MAX_SECONDS="${MAX_SECONDS:-90}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"

end=$((SECONDS + MAX_SECONDS))

while [ $SECONDS -lt $end ]; do
  if ip route show default >/dev/null 2>&1 && ip route show default | grep -q "default"; then
    # No DNS dependency: TCP connect to 1.1.1.1:443 (no raw sockets).
    if /usr/bin/python3 - <<'PY' >/dev/null 2>&1
import socket
s = socket.socket()
s.settimeout(2.0)
s.connect(("1.1.1.1", 443))
s.close()
PY
    then
        exit 0
    fi
  fi
  sleep "$SLEEP_SECONDS"
done

echo "No internet connectivity after ${MAX_SECONDS}s" >&2
exit 1

