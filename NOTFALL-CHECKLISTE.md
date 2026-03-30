# Gastro System - Notfall Checkliste (Pi)

## 1) Schnellcheck in 60 Sekunden

1. Strom am Pi an, 60-90 Sekunden warten.
2. Auf Smartphone/PC `https://app.mpbin.de` aufrufen.
3. Wenn Seite nicht erreichbar:
   - lokal prüfen: `http://<pi-ip>:8080`
   - wenn lokal geht, ist meist Tunnel/Internet das Thema.

## 2) WLAN Notfall (ohne bekanntes WLAN)

1. Mit dem Handy auf WLAN `Gastro-Setup` verbinden.
2. Browser aufrufen: `http://10.42.0.1:9090`
3. Ziel-WLAN auswählen oder SSID/Passwort manuell eintragen.
4. Verbinden klicken, dann 20-60 Sekunden warten.
5. `https://app.mpbin.de` erneut testen.

## 3) Vor Ort mit Monitor/Tastatur

1. Desktop Button `WLAN einstellen` oeffnen.
2. Richtiges WLAN verbinden.
3. Desktop Button `Gastro-System neu starten` klicken.
4. Erneut testen:
   - `https://app.mpbin.de`
   - lokal: `http://127.0.0.1:8080/health.json`
   - backend: `http://127.0.0.1:8000/health`

## 4) Service-Status (Terminal am Pi)

```bash
sudo systemctl is-active gastro-backend gastro-frontend gastro-cloudflared
sudo systemctl status gastro-backend gastro-frontend gastro-cloudflared --no-pager -l
sudo journalctl -u gastro-cloudflared -n 80 --no-pager
```

Soll: alle drei Services `active`.

## 5) Feste WLANs einmalig einlernen

Damit Ortswechsel ohne Monitor klappt:

```bash
sudo /opt/gastro-system/deploy/setup-known-wifi.sh "Lokis Habitat" "Schwarze11"
```

Danach verbindet der Pi automatisch mit bekannten Netzen und waehlt per Autoswitch das staerkere bekannte Signal.

## 6) Gastro-Setup Zugangsdaten (fuer Aufkleber)

- SSID: `Gastro-Setup`
- Passwort: `iIDGca7GIQLY`
- URL: `http://10.42.0.1:9090`

## 7) Wenn gar nichts mehr geht

1. Pi neu starten.
2. 2 Minuten warten.
3. Erst lokal (`http://<pi-ip>:8080`) pruefen, dann Tunnel (`https://app.mpbin.de`).
4. Notfalls WLAN ueber `Gastro-Setup` neu setzen.

