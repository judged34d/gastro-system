#!/usr/bin/env python3
"""
Standalone Telegram bot for Gastro system status commands.

Commands:
  /help
  /gastrostatus
  /services
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

TELEGRAM_TOKEN = (os.environ.get("GASTRO_TELEGRAM_TOKEN") or "").strip()
ALLOWED_CHAT_IDS_RAW = (os.environ.get("GASTRO_TELEGRAM_CHAT_IDS") or "").strip()
POLL_TIMEOUT_SEC = int(os.environ.get("GASTRO_TELEGRAM_POLL_TIMEOUT", "25"))
SLEEP_SEC = float(os.environ.get("GASTRO_TELEGRAM_SLEEP_SEC", "1.5"))

if ALLOWED_CHAT_IDS_RAW:
    ALLOWED_CHAT_IDS = {s.strip() for s in ALLOWED_CHAT_IDS_RAW.split(",") if s.strip()}
else:
    ALLOWED_CHAT_IDS = set()


def tg_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=35) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def send_message(chat_id: int, text: str) -> None:
    try:
        tg_api("sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as exc:
        print(f"sendMessage error: {exc}")


def run_cmd(cmd: list[str], timeout: int = 8) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode == 0:
            return True, out
        msg = out if out else err
        return False, msg or f"exit {p.returncode}"
    except Exception as exc:
        return False, str(exc)


def check_http(url: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=6) as resp:
            code = resp.status
            raw = resp.read().decode("utf-8", "replace").strip()
        if 200 <= code < 300:
            if len(raw) > 180:
                raw = raw[:180] + "..."
            return True, raw
        return False, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as exc:
        return False, str(exc)


def build_status_text() -> str:
    lines: list[str] = []
    lines.append("Gastro Status")

    ok_b, msg_b = check_http("http://127.0.0.1:8000/health")
    lines.append(f"- Backend: {'OK' if ok_b else 'FEHLER'} ({msg_b})")

    ok_f, msg_f = check_http("http://127.0.0.1:8080/health.json")
    lines.append(f"- Frontend: {'OK' if ok_f else 'FEHLER'} ({msg_f})")

    ok_s, msg_s = run_cmd(["systemctl", "is-active", "gastro-backend", "gastro-frontend", "gastro-cloudflared"])
    if ok_s:
        states = [s.strip() for s in msg_s.splitlines() if s.strip()]
        labels = ["backend", "frontend", "cloudflared"]
        svc = []
        for i, label in enumerate(labels):
            st = states[i] if i < len(states) else "unknown"
            svc.append(f"{label}:{st}")
        lines.append("- Services: " + ", ".join(svc))
    else:
        lines.append(f"- Services: unbekannt ({msg_s})")

    ok_ip, msg_ip = run_cmd(["hostname", "-I"])
    if ok_ip:
        lines.append("- Host IP(s): " + " ".join(msg_ip.split()))

    return "\n".join(lines)


def handle_text(chat_id: int, text: str) -> None:
    cmd = (text or "").strip().split(" ", 1)[0].lower()
    if cmd in ("/help", "/start"):
        send_message(
            chat_id,
            "Gastro Bot Befehle:\n"
            "/gastrostatus - Health + Servicezustand\n"
            "/services - nur systemd-States",
        )
        return
    if cmd == "/gastrostatus":
        send_message(chat_id, build_status_text())
        return
    if cmd == "/services":
        ok_s, msg_s = run_cmd(["systemctl", "is-active", "gastro-backend", "gastro-frontend", "gastro-cloudflared"])
        if ok_s:
            send_message(chat_id, "Services:\n" + msg_s)
        else:
            send_message(chat_id, "Services nicht lesbar:\n" + msg_s)
        return
    send_message(chat_id, "Unbekannter Befehl. /help")


def allowed_chat(chat_id: int) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return str(chat_id) in ALLOWED_CHAT_IDS


def main() -> int:
    if not TELEGRAM_TOKEN:
        print("Missing GASTRO_TELEGRAM_TOKEN. Exiting.")
        return 1

    # Ensure polling mode (remove webhook) to avoid 409 conflicts.
    try:
        tg_api("deleteWebhook", {"drop_pending_updates": False})
    except Exception as exc:
        print(f"deleteWebhook failed: {exc}")

    print("Gastro Telegram bot started.")
    offset: int | None = None
    while True:
        try:
            payload: dict[str, Any] = {"timeout": POLL_TIMEOUT_SEC}
            if offset is not None:
                payload["offset"] = offset
            res = tg_api("getUpdates", payload)
            for upd in res.get("result", []):
                offset = int(upd.get("update_id", 0)) + 1
                msg = upd.get("message") or {}
                text = msg.get("text") or ""
                chat = msg.get("chat") or {}
                chat_id = int(chat.get("id", 0))
                if not chat_id:
                    continue
                if not allowed_chat(chat_id):
                    send_message(chat_id, "Nicht freigeschaltet.")
                    continue
                handle_text(chat_id, text)
        except Exception as exc:
            print(f"poll error: {exc}")
            time.sleep(3)
        time.sleep(SLEEP_SEC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
