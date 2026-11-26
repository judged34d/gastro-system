#!/bin/bash
# Dauerhafte CUPS-Remote-Freigabe fuer Gastro-Host (ueberlebt Neustart + Energiesparen).
# Einmal am Ubuntu-Notebook ausfuehren:
#   bash ubuntu-cups-persist-remote.sh
# Optional:  bash ubuntu-cups-persist-remote.sh Gastro-System

set -euo pipefail
USER_NAME="${1:-Gastro-System}"

echo "==> 1) User in lpadmin"
id "$USER_NAME" >/dev/null 2>&1 && sudo usermod -aG lpadmin "$USER_NAME" || echo "Hinweis: User $USER_NAME nicht gefunden – ueberspringe usermod"

echo "==> 2) cupsd.conf Policy dauerhaft patchen"
CONF=/etc/cups/cupsd.conf
sudo cp -a "$CONF" "/etc/cups/cupsd.conf.bak.gastro.$(date +%s)"

sudo python3 - <<'PY'
from pathlib import Path
p = Path("/etc/cups/cupsd.conf")
text = p.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines(True)
out, buf, in_lim, has_print = [], [], False, False

def flush():
    global buf, has_print
    if not buf:
        return
    if not has_print:
        out.extend(buf)
        buf, has_print = [], False
        return
    fixed = []
    for ln in buf:
        s = ln.lstrip()
        if s.startswith("AuthType ") or s.startswith("Require user "):
            ind = ln[: len(ln) - len(ln.lstrip())]
            fixed.append(f"{ind}# gastro-persist: {s}")
        else:
            fixed.append(ln)
    body = "".join(fixed)
    if "Allow @LOCAL" not in body and "Allow all" not in body:
        fixed2 = []
        for ln in fixed:
            if ln.lstrip().startswith("</Limit>"):
                ind = ln[: len(ln) - len(ln.lstrip())]
                fixed2.append(f"{ind}  Order allow,deny\n")
                fixed2.append(f"{ind}  Allow @LOCAL\n")
            fixed2.append(ln)
        fixed = fixed2
    out.extend(fixed)
    buf, has_print = [], False

for ln in lines:
    if (not in_lim) and ln.lstrip().startswith("<Limit"):
        in_lim = True
        buf = [ln]
        has_print = "Print-Job" in ln
        continue
    if in_lim:
        buf.append(ln)
        if "Print-Job" in ln:
            has_print = True
        if ln.lstrip().startswith("</Limit>"):
            flush()
            in_lim = False
        continue
    out.append(ln)

# Sicherstellen: Listen auf allen Interfaces (nicht nur localhost)
joined = "".join(out)
if "Listen *:631" not in joined and "Port 631" not in joined:
    # nach bestehenden Listen-Zeilen einfuegen
    out2 = []
    inserted = False
    for ln in out:
        out2.append(ln)
        if (not inserted) and (ln.startswith("Listen ") or ln.startswith("Port ")):
            out2.append("Listen *:631\n")
            inserted = True
    if not inserted:
        out2.insert(0, "Listen *:631\n")
    out = out2

Path("/tmp/cupsd.conf.gastro-persist").write_text("".join(out), encoding="utf-8")
print("patched -> /tmp/cupsd.conf.gastro-persist")
PY

sudo cp /tmp/cupsd.conf.gastro-persist "$CONF"

echo "==> 3) Helper-Script"
sudo tee /usr/local/sbin/gastro-cups-remote.sh >/dev/null <<'EOS'
#!/bin/bash
# Von systemd / Sleep-Hook aufgerufen
/usr/sbin/cupsctl --share-printers --remote-any 2>/dev/null || true
/bin/systemctl reload cups 2>/dev/null || /bin/systemctl try-restart cups 2>/dev/null || true
EOS
sudo chmod 755 /usr/local/sbin/gastro-cups-remote.sh

echo "==> 4) systemd Service (nach jedem Boot / cups-Start)"
sudo tee /etc/systemd/system/gastro-cups-remote.service >/dev/null <<'EOS'
[Unit]
Description=Gastro: CUPS remote print allow (LAN)
After=cups.service network-online.target
Wants=cups.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/gastro-cups-remote.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target cups.service
EOS

echo "==> 5) Sleep/Resume-Hook (nach Energiesparmodus)"
sudo tee /usr/lib/systemd/system-sleep/gastro-cups-remote >/dev/null <<'EOS'
#!/bin/bash
# $1 = pre|post , $2 = suspend|hibernate|hybrid-sleep
if [ "$1" = "post" ]; then
  sleep 2
  /usr/local/sbin/gastro-cups-remote.sh
fi
EOS
sudo chmod 755 /usr/lib/systemd/system-sleep/gastro-cups-remote

echo "==> 6) aktivieren + jetzt anwenden"
sudo systemctl daemon-reload
sudo systemctl enable gastro-cups-remote.service
sudo systemctl restart cups
sleep 1
sudo /usr/local/sbin/gastro-cups-remote.sh
sudo systemctl start gastro-cups-remote.service
sudo systemctl is-active cups
echo "FERTIG – Remote-Druck bleibt nach Boot und Energiesparen aktiv."
