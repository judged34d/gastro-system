#!/bin/bash
# CUPS: Remote-Druck ohne Auth dauerhaft erlauben (LAN / Gastro).
# Einmal am Ubuntu-Terminal:
#   bash ubuntu-cups-disable-auth.sh
#
# Macht: Policy ohne AuthType/Require fuer Print-Job, Allow @LOCAL,
#        Listen *:631, Service + Sleep-Hook damit es nach Energiesparen bleibt.

set -euo pipefail

echo "==> CUPS stoppen"
sudo systemctl stop cups.service cups.socket cups.path 2>/dev/null || true
sudo systemctl stop cups 2>/dev/null || true

CONF=/etc/cups/cupsd.conf
BAK="/etc/cups/cupsd.conf.bak.gastro-noauth.$(date +%s)"
echo "==> Backup: $BAK"
sudo cp -a "$CONF" "$BAK"

echo "==> Neue cupsd.conf schreiben (Druck ohne Authentifizierung im LAN)"
sudo tee "$CONF" >/dev/null <<'EOF'
# Gastro: dauerhafte LAN-Freigabe fuer Bondruck (ohne Login)
LogLevel warn
PageLogFormat
MaxLogSize 0

# Auf allen Interfaces hoeren (nicht nur localhost)
Port 631
Listen /run/cups/cups.sock
Listen *:631

Browsing On
BrowseLocalProtocols dnssd
DefaultAuthType None
WebInterface Yes

<Location />
  Order allow,deny
  Allow @LOCAL
</Location>

<Location /admin>
  Order allow,deny
  Allow localhost
</Location>

<Location /admin/conf>
  AuthType Default
  Require user @SYSTEM
  Order allow,deny
  Allow localhost
</Location>

<Location /admin/log>
  AuthType Default
  Require user @SYSTEM
  Order allow,deny
  Allow localhost
</Location>

<Policy default>
  JobPrivateAccess default
  JobPrivateValues default
  SubscriptionPrivateAccess default
  SubscriptionPrivateValues default

  # Drucken: KEIN Auth, LAN erlaubt (ueberlebt Sleep/Reboot)
  <Limit Create-Job Print-Job Print-URI Validate-Job Send-Document Send-URI
         Release-Job Cancel-Job Cancel-My-Jobs Close-Job CUPS-Move-Job
         CUPS-Get-Document Hold-Job Restart-Job Purge-Jobs Set-Job-Attributes>
    Order allow,deny
    Allow @LOCAL
  </Limit>

  <Limit CUPS-Add-Modify-Printer CUPS-Delete-Printer CUPS-Add-Modify-Class
         CUPS-Delete-Class CUPS-Set-Default CUPS-Get-Devices>
    AuthType Default
    Require user @SYSTEM
    Order allow,deny
    Allow localhost
  </Limit>

  <Limit All>
    Order allow,deny
    Allow @LOCAL
  </Limit>
</Policy>

<Policy authenticated>
  JobPrivateAccess default
  JobPrivateValues default
  SubscriptionPrivateAccess default
  SubscriptionPrivateValues default
  <Limit Create-Job Print-Job Print-URI Validate-Job Send-Document Send-URI
         Release-Job Cancel-Job Cancel-My-Jobs Close-Job CUPS-Move-Job
         CUPS-Get-Document Hold-Job Restart-Job Set-Job-Attributes>
    Order allow,deny
    Allow @LOCAL
  </Limit>
  <Limit All>
    Order allow,deny
    Allow @LOCAL
  </Limit>
</Policy>
EOF

echo "==> Syntax pruefen"
if ! sudo cupsd -t 2>&1; then
  echo "FEHLER in cupsd.conf – stelle Backup wieder her"
  sudo cp -a "$BAK" "$CONF"
  sudo systemctl start cups
  exit 1
fi

echo "==> Persist-Helper + Sleep-Hook"
sudo tee /usr/local/sbin/gastro-cups-remote.sh >/dev/null <<'EOS'
#!/bin/bash
# Nach Boot/Sleep: sicherstellen dass Sharing an ist
/usr/sbin/cupsctl --share-printers --remote-any >/dev/null 2>&1 || true
EOS
sudo chmod 755 /usr/local/sbin/gastro-cups-remote.sh

sudo tee /etc/systemd/system/gastro-cups-remote.service >/dev/null <<'EOS'
[Unit]
Description=Gastro CUPS LAN print without auth
After=cups.service
Wants=cups.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/gastro-cups-remote.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOS

sudo tee /usr/lib/systemd/system-sleep/gastro-cups-remote >/dev/null <<'EOS'
#!/bin/bash
if [ "${1:-}" = "post" ]; then
  sleep 2
  /usr/local/sbin/gastro-cups-remote.sh
  /bin/systemctl try-restart cups.service >/dev/null 2>&1 || true
fi
EOS
sudo chmod 755 /usr/lib/systemd/system-sleep/gastro-cups-remote

echo "==> CUPS starten"
sudo systemctl daemon-reload
sudo systemctl enable gastro-cups-remote.service
sudo systemctl enable --now cups.service
sleep 1
sudo /usr/local/sbin/gastro-cups-remote.sh

# Drucker freigeben falls vorhanden
for q in A795 A798; do
  sudo lpadmin -p "$q" -o printer-is-shared=true 2>/dev/null || true
  sudo cupsenable "$q" 2>/dev/null || true
  sudo cupsaccept "$q" 2>/dev/null || true
done

echo "==> Status"
sudo systemctl is-active cups
lpstat -p -v 2>/dev/null || true
hostname -I
echo "FERTIG – Druck im LAN ohne Passwort-Freigabe. Bitte Gastro-Testbon."
