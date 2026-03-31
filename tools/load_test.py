#!/usr/bin/env python3
"""
Lasttest für das Gastro-Backend (Flask + SQLite).

Simuliert:
  - 25 Bedienungen mit je 2 Tischen (Bestellungen mit realistischen Pausen)
  - 4 Theken-Terminals + 3 zusätzliche Polls auf „Getränke“ (6 Display-Poller gesamt)
  - GET /station/<id>/display im Küchen-Intervall (~3 s + Jitter)
  - Nach der Lastphase: alle offenen Orders durchlaufen (Stationen -> Zubereitet, dann pay-item),
    sodass die Bestellungen am Ende bezahlt sind (Orderstatus-Viewer leer)

Voraussetzung: Backend erreichbar (z. B. http://127.0.0.1:8000).

  pip install requests

Beispiele:
  # Sauberer Lauf: Orders leeren, neues leeres Event aktivieren, [LT]-Daten anlegen
  python tools/load_test.py --base-url ... --clear-orders --event-name "LT Lasttest 2026-03-31" --seed
  python tools/load_test.py --base-url ... --clear-orders --duration 120 --poll-station-substring Getränke

  # Live-Start nach Tests: DB leeren + neues Event + Seed ([LT]-Stationen)
  python tools/load_test.py --base-url ... --live-reset --event-name "Live-Start 2026" --seed

  # Nur Orders im aktiven Event loeschen (Kacheln/DB, HTTP POST /admin/events/clear-orders)
  python tools/load_test.py --base-url ... --clear-orders

  # Demo: eine Order, Theken nacheinander (gruene Haken im Orderstatus), dann Kasse;
  # danach optional kurzer Lasttest + Drain:
  python tools/load_test.py --base-url ... --demo --demo-delay 2.5 --demo-then-load --duration 45

Hinweis: --seed legt markierte Datensätze im AKTIVEN Event an ([LT] …).
         --live-reset loescht ALLE Stammdaten/Events und legt genau ein neues aktives Event an (--event-name = Name).
         Vor Produktions-DB Backup anlegen oder gegen Kopie/Staging testen.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

try:
    import requests
except ImportError:
    print("Bitte installieren: pip install requests", file=sys.stderr)
    sys.exit(1)


# --- Konfiguration Lastprofil -------------------------------------------------

WAITERS = 25
TABLES = 50  # 25 × 2
STATION_POLLERS = 6  # 1+1+3+1 Terminals (Station „Getränke“ 3× parallel)

# Zeit zwischen zwei kompletten Bestellungen pro Kellner (Sekunden) – nicht „5 Orders in 2 s“
ORDER_INTERVAL_MIN = 18.0
ORDER_INTERVAL_MAX = 55.0

# Vorbereitung: Zeit pro Position „eintippen“ (nur Wartezeit im Client)
PER_ITEM_PREP_DELAY = (0.4, 1.8)

# Wie viele Positionen pro Bestellung (Tisch ~12 Personen → große Runden eher selten)
ITEMS_PER_ORDER_MIN = 1
ITEMS_PER_ORDER_MAX = 8

DISPLAY_POLL_BASE = 3.0
DISPLAY_POLL_JITTER = 0.45

# Pro Display-Poll: zufaellig eine sichtbare Kachel um einen Status-Schritt weitersetzen
# (new -> preparing -> ready). Nicht jede Runde, damit es realistischer wirkt.
STATUS_ADVANCE_PROB = 0.38

PREFIX = "[LT]"


@dataclass
class Metrics:
    lat_ms: list[float] = field(default_factory=list)
    errors: int = 0
    requests: int = 0
    orders_ok: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, elapsed_s: float, ok: bool) -> None:
        with self.lock:
            self.requests += 1
            self.lat_ms.append(elapsed_s * 1000.0)
            if not ok:
                self.errors += 1

    def order_ok(self) -> None:
        with self.lock:
            self.orders_ok += 1


def _req(
    session: requests.Session,
    method: str,
    base: str,
    path: str,
    *,
    json_body: Any = None,
    metrics: Metrics | None = None,
    timeout: float = 60.0,
) -> requests.Response:
    url = base.rstrip("/") + path
    t0 = time.perf_counter()
    ok = False
    try:
        if method == "GET":
            r = session.get(url, timeout=timeout)
        else:
            r = session.post(url, json=json_body, timeout=timeout)
        ok = r.ok
        return r
    except Exception:
        ok = False
        raise
    finally:
        if metrics is not None:
            metrics.record(time.perf_counter() - t0, ok)


def health(base: str) -> None:
    r = requests.get(base.rstrip("/") + "/health", timeout=10)
    r.raise_for_status()
    print("Health:", r.json())


def clear_orders_api(base: str) -> None:
    """Alle Orders des aktiven Events inkl. Theken-Display (POST /admin/events/clear-orders)."""
    r = requests.post(
        base.rstrip("/") + "/admin/events/clear-orders",
        json={},
        timeout=120,
    )
    if not r.ok:
        print("FEHLER clear-orders", r.status_code, r.text[:500], file=sys.stderr)
        r.raise_for_status()
    j = r.json()
    print(
        f"Orders geloescht: {j.get('deleted_orders', '?')} Stueck "
        f"(event_id={j.get('event_id')})",
    )


def live_reset_api(base: str, new_event_name: str) -> dict:
    """
    Live-Vorbereitung: alle Orders + Stammdaten aller Events, ein neues leeres aktives Event.
    """
    r = requests.post(
        base.rstrip("/") + "/admin/events/clear-orders",
        json={"live_reset": True, "new_event_name": new_event_name},
        timeout=180,
    )
    if not r.ok:
        print("FEHLER live_reset", r.status_code, r.text[:500], file=sys.stderr)
        r.raise_for_status()
    j = r.json()
    print(
        f"Live-Reset: {j.get('deleted_orders', '?')} Orders geloescht, "
        f"neues Event id={j.get('event_id')} ({j.get('event_name', new_event_name)!r})",
    )
    return j


def ensure_active_event(base: str, name: str) -> int:
    """
    Event mit genau diesem Namen finden (höchste id bei Duplikaten) oder neu anlegen,
    danach aktivieren (schließt das zuvor aktive Event).
    """
    base = base.rstrip("/")
    s = requests.Session()
    r = s.get(f"{base}/admin/events", timeout=60)
    r.raise_for_status()
    data = r.json()
    events = data.get("events") or []
    needle = name.strip()
    matches = [e for e in events if (e.get("name") or "").strip() == needle]
    if matches:
        eid = max(int(e["id"]) for e in matches)
        print(f"Event vorhanden (id={eid}): {needle!r} -> aktiv setzen ...")
    else:
        r = s.post(f"{base}/admin/events", json={"name": needle}, timeout=60)
        if not r.ok:
            print("FEHLER POST /admin/events", r.status_code, r.text[:500])
            r.raise_for_status()
        body = r.json()
        eid = int(body["event_id"])
        print(f"Event angelegt (id={eid}): {needle!r} -> aktiv setzen ...")

    r = s.post(f"{base}/admin/events/activate", json={"event_id": eid}, timeout=60)
    if not r.ok:
        print("FEHLER POST /admin/events/activate", r.status_code, r.text[:500])
        r.raise_for_status()
    print("Aktives Event:", needle)
    return eid


def seed_data(base: str) -> None:
    """Legt Kategorien, Artikel, Tische, Kellner, Stationen und Zuordnungen an."""
    s = requests.Session()

    def post(path: str, body: dict) -> Any:
        r = s.post(base.rstrip("/") + path, json=body, timeout=60)
        if not r.ok:
            print("FEHLER", path, r.status_code, r.text[:500])
            r.raise_for_status()
        return r.json() if r.text else {}

    def getj(path: str) -> Any:
        r = s.get(base.rstrip("/") + path, timeout=60)
        r.raise_for_status()
        return r.json()

    print("Seed: Kategorien ...")
    cat_names = [
        (f"{PREFIX} Speisen", "speisen"),
        (f"{PREFIX} Biere", "biere"),
        (f"{PREFIX} Getränke", "getraenke"),
        (f"{PREFIX} Sekt", "sekt"),
    ]
    for name, _key in cat_names:
        post("/admin/categories", {"name": name})

    cats = {c["name"]: c["id"] for c in getj("/admin/categories")}
    cid = {k: cats[n] for n, k in cat_names}

    products_spec = [
        # Speisen
        ("Schnitzel", 14.90, "speisen"),
        ("Pommes", 4.50, "speisen"),
        ("Beilagensalat", 3.90, "speisen"),
        ("Kartoffelsalat", 4.20, "speisen"),
        ("Suppe", 5.50, "speisen"),
        ("Kinderportion", 7.50, "speisen"),
        # Biere
        ("Pils 0,5l", 4.20, "biere"),
        ("Weizen 0,5l", 4.50, "biere"),
        ("Radler", 4.00, "biere"),
        ("Alkoholfrei 0,5l", 4.00, "biere"),
        # Getränke
        ("Cola", 3.80, "getraenke"),
        ("Wasser", 2.50, "getraenke"),
        ("Apfelsaft", 3.50, "getraenke"),
        ("Sprudel", 3.20, "getraenke"),
        # Sekt
        ("Sekt Glas", 4.50, "sekt"),
        ("Sekt Flasche", 22.00, "sekt"),
        ("Prosecco", 5.50, "sekt"),
    ]

    print("Seed: Artikel ...")
    for pname, price, ck in products_spec:
        post(
            "/admin/products",
            {"name": f"{PREFIX} {pname}", "price": price, "category_id": cid[ck]},
        )

    print(f"Seed: {TABLES} Tische ...")
    for i in range(1, TABLES + 1):
        post("/admin/tables", {"name": f"{PREFIX} Tisch {i:02d}"})

    print(f"Seed: {WAITERS} Kellner + 4 Stationen ...")
    for i in range(1, WAITERS + 1):
        post(
            "/admin/users",
            {"name": f"{PREFIX} Kellner {i:02d}", "pin": str(5000 + i), "role": "waiter"},
        )
    station_labels = ["Speisen", "Biere", "Getränke", "Sekt"]
    for i, lab in enumerate(station_labels, start=1):
        post(
            "/admin/users",
            {"name": f"{PREFIX} Station {lab}", "pin": str(6000 + i), "role": "station"},
        )

    data = getj("/admin/users")
    users = data["users"]
    tables = sorted(data["tables"], key=lambda t: t["id"])
    waiters = [u for u in users if u["role"] == "waiter" and u["name"].startswith(PREFIX)]
    stations = [u for u in users if u["role"] == "station" and u["name"].startswith(PREFIX)]
    waiters.sort(key=lambda u: u["name"])
    stations.sort(key=lambda u: u["name"])

    if len(waiters) < WAITERS or len(tables) < TABLES or len(stations) < 4:
        print(
            "Seed unvollständig: Kellner/Tische/Stationen fehlen.",
            len(waiters),
            len(tables),
            len(stations),
        )
        sys.exit(1)

    print("Seed: Tischzuordnungen Kellner ...")
    for idx, w in enumerate(waiters[:WAITERS]):
        t1 = tables[2 * idx]["id"]
        t2 = tables[2 * idx + 1]["id"]
        post("/admin/users/assign", {"user_id": w["id"], "table_ids": [t1, t2]})

    # Station → Kategorie (Reihenfolge Stationen: Speisen, Biere, Getränke, Sekt)
    smap = {
        f"{PREFIX} Station Speisen": cid["speisen"],
        f"{PREFIX} Station Biere": cid["biere"],
        f"{PREFIX} Station Getränke": cid["getraenke"],
        f"{PREFIX} Station Sekt": cid["sekt"],
    }
    print("Seed: Station -> Kategorien ...")
    for st in stations:
        key = st["name"]
        if key in smap:
            post(
                "/admin/station/categories",
                {"station_id": st["id"], "category_ids": [smap[key]]},
            )

    print("Seed abgeschlossen.")
    print("  Kellner-PINs: 5001-5025, Station-PINs: 6001-6004")


def fetch_stations_for_poll(base: str, name_substring: str | None) -> list[dict]:
    """Station-User fuer Display-Polling: entweder [LT]-Praefix oder Namens-Teilstring (z. B. Getränke)."""
    users = requests.get(base.rstrip("/") + "/users", timeout=30).json()
    stations = [u for u in users if u.get("role") == "station"]
    if name_substring:
        needle = name_substring.strip().lower()
        stations = [u for u in stations if needle in (u.get("name") or "").lower()]
    else:
        stations = [u for u in stations if (u.get("name") or "").startswith(PREFIX)]
    stations.sort(key=lambda u: (u.get("name") or ""))
    return stations


def fetch_runtime_ids(base: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Lädt Kellner, Tische, Produkte für [LT]-Datensätze."""
    s = requests.Session()
    users = s.get(base.rstrip("/") + "/users", timeout=30).json()
    waiters = [u for u in users if u["role"] == "waiter" and u["name"].startswith(PREFIX)]
    stations = [u for u in users if u["role"] == "station" and u["name"].startswith(PREFIX)]
    waiters.sort(key=lambda x: x["name"])
    stations.sort(key=lambda x: x["name"])

    tables = s.get(base.rstrip("/") + "/admin/tables", timeout=30).json()
    tables = [t for t in tables if t["name"].startswith(PREFIX)]
    tables.sort(key=lambda t: t["id"])

    products = s.get(base.rstrip("/") + "/products", timeout=30).json()
    products = [p for p in products if p["name"].startswith(PREFIX)]

    return waiters, tables, products


def waiter_loop(
    base: str,
    waiter: dict,
    table_ids: list[int],
    product_ids: list[int],
    duration: float,
    metrics: Metrics,
    rng: random.Random,
) -> None:
    session = requests.Session()
    end = time.perf_counter() + duration
    while time.perf_counter() < end:
        gap = rng.uniform(ORDER_INTERVAL_MIN, ORDER_INTERVAL_MAX)
        time.sleep(min(gap, max(0.0, end - time.perf_counter())))
        if time.perf_counter() >= end:
            break

        table_id = rng.choice(table_ids)
        n_items = rng.randint(ITEMS_PER_ORDER_MIN, min(ITEMS_PER_ORDER_MAX, len(product_ids)))
        picks = rng.sample(product_ids, n_items)

        try:
            r = _req(
                session,
                "POST",
                base,
                "/orders",
                json_body={"table_id": table_id, "waiter_id": waiter["id"]},
                metrics=metrics,
            )
            if not r.ok:
                continue
            order = r.json()
            oid = order["order_id"]

            for pid in picks:
                time.sleep(rng.uniform(*PER_ITEM_PREP_DELAY))
                _req(
                    session,
                    "POST",
                    base,
                    f"/orders/{oid}/items",
                    json_body={"product_id": pid, "quantity": rng.randint(1, 3)},
                    metrics=metrics,
                )
            metrics.order_ok()
        except Exception:
            # _req hat bei HTTP-/Netzfehlern bereits gezählt; hier nur Abbruch der Runde
            pass


def display_poller(
    base: str,
    station_id: int,
    duration: float,
    metrics: Metrics,
    rng: random.Random,
    *,
    advance_status: bool = True,
) -> None:
    session = requests.Session()
    end = time.perf_counter() + duration
    while time.perf_counter() < end:
        try:
            r = _req(
                session,
                "GET",
                base,
                f"/station/{station_id}/display",
                metrics=metrics,
            )
            if r.ok and advance_status:
                try:
                    data = r.json()
                    candidates: list[int] = []
                    for sl in data.get("slots") or []:
                        if not sl:
                            continue
                        st = sl.get("status")
                        if st in ("new", "preparing"):
                            candidates.append(int(sl["order_id"]))
                    if candidates and rng.random() < STATUS_ADVANCE_PROB:
                        oid = rng.choice(candidates)
                        _req(
                            session,
                            "POST",
                            base,
                            f"/station/{station_id}/orders/{oid}/status",
                            json_body={},
                            metrics=metrics,
                        )
                except (TypeError, ValueError, KeyError):
                    pass
        except Exception:
            pass  # Fehler bereits in _req gezählt
        time.sleep(DISPLAY_POLL_BASE + rng.uniform(0, DISPLAY_POLL_JITTER))


def _post_station_status(
    session: requests.Session,
    base: str,
    station_id: int,
    order_id: int,
    metrics: Metrics | None,
) -> str:
    """
    POST /station/.../status einmal.
    Rueckgabe: 'not_found' (404, Order hat diese Station nicht),
    'ready', 'continue' (weiter klicken), 'error'.
    """
    url = base.rstrip("/") + f"/station/{station_id}/orders/{order_id}/status"
    t0 = time.perf_counter()
    ok = False
    try:
        r = session.post(url, json={}, timeout=60)
        if r.status_code == 404:
            ok = True
            return "not_found"
        ok = r.ok
        if not r.ok:
            return "error"
        j = r.json()
        if str(j.get("status") or "").lower() == "ready":
            return "ready"
        return "continue"
    finally:
        if metrics is not None:
            metrics.record(time.perf_counter() - t0, ok)


def advance_one_station_until_ready(
    session: requests.Session,
    base: str,
    order_id: int,
    station_id: int,
    metrics: Metrics | None,
) -> None:
    """Eine Station fuer diese Order bis Zubereitet (ready) durchklicken."""
    for _ in range(8):
        st = _post_station_status(session, base, station_id, order_id, metrics)
        if st in ("not_found", "ready"):
            return
        if st == "error":
            return


def advance_order_at_all_stations(
    session: requests.Session,
    base: str,
    order_id: int,
    station_ids: list[int],
    metrics: Metrics | None,
) -> None:
    """Alle betroffenen Stationen fuer diese Order auf 'ready' bringen."""
    for sid in station_ids:
        advance_one_station_until_ready(session, base, order_id, sid, metrics)


def fetch_all_station_users(base: str) -> list[dict]:
    """Alle Station-User (Namen fuer Sortierung Speisen/Biere/...)."""
    users = requests.get(base.rstrip("/") + "/users", timeout=30).json()
    return [u for u in users if u.get("role") == "station"]


def station_ids_for_order(
    session: requests.Session,
    base: str,
    order_id: int,
    metrics: Metrics | None,
) -> list[int]:
    """Tatsaechliche Station-IDs aus order_station_status (wie in der DB)."""
    r = _req(session, "GET", base, f"/orders/{order_id}/station-status", metrics=metrics)
    if not r.ok:
        return []
    data = r.json() or {}
    out: list[int] = []
    for s in data.get("stations") or []:
        try:
            out.append(int(s["station_id"]))
        except (TypeError, KeyError, ValueError):
            continue
    return out


def sort_station_ids_by_kitchen_order(station_ids: list[int], station_users: list[dict]) -> list[int]:
    """Reihenfolge Speisen, Biere, Getränke, Sekt; Rest hinten."""
    id_to_name = {int(u["id"]): (u.get("name") or "").strip() for u in station_users}
    order_labels = ["Speisen", "Biere", "Getränke", "Sekt"]
    seq: list[int] = []
    for lab in order_labels:
        key = f"{PREFIX} Station {lab}"
        for sid in station_ids:
            if id_to_name.get(sid) == key:
                seq.append(sid)
                break
    for sid in station_ids:
        if sid not in seq:
            seq.append(sid)
    return seq


def pick_demo_product_ids(products: list[dict]) -> list[int]:
    """Je ein Artikel pro Kategorie (Speisen, Biere, Getränke, Sekt)."""
    needles = ["Schnitzel", "Pils", "Cola", "Sekt Glas"]
    ids: list[int] = []
    for needle in needles:
        found = None
        for p in products:
            name = (p.get("name") or "")
            if name.startswith(PREFIX) and needle in name:
                found = int(p["id"])
                break
        if found is None:
            print(f"WARN: Demo-Artikel mit Kennung '{needle}' nicht gefunden.", file=sys.stderr)
        else:
            ids.append(found)
    return ids


def run_demo_sequence(base: str, delay_s: float) -> None:
    """
    Eine Bestellung mit 4 Positionen (je eine Station), Theken nacheinander bis Zubereitet,
    danach Kasse. Zum Beobachten im Orderstatus-Viewer (gruene Haken nacheinander).
    """
    session = requests.Session()
    m = Metrics()
    waiters, tables, products = fetch_runtime_ids(base)
    if len(waiters) < 1 or len(tables) < 1:
        print("Demo: mindestens einen Kellner und einen Tisch noetig (--seed).", file=sys.stderr)
        sys.exit(1)
    pids = pick_demo_product_ids(products)
    if len(pids) < 4:
        print("Demo: vier Artikel (Schnitzel, Pils, Cola, Sekt Glas) fehlen — bitte --seed.", file=sys.stderr)
        sys.exit(1)
    station_users = fetch_all_station_users(base)

    w0 = waiters[0]
    t0 = tables[0]["id"]
    r = _req(
        session,
        "POST",
        base,
        "/orders",
        json_body={"table_id": t0, "waiter_id": w0["id"]},
        metrics=m,
    )
    if not r.ok:
        print("Demo: POST /orders fehlgeschlagen", r.status_code, file=sys.stderr)
        sys.exit(1)
    oid = int(r.json()["order_id"])
    for pid in pids:
        _req(
            session,
            "POST",
            base,
            f"/orders/{oid}/items",
            json_body={"product_id": pid, "quantity": 1},
            metrics=m,
        )

    raw_sids = station_ids_for_order(session, base, oid, m)
    sids = sort_station_ids_by_kitchen_order(raw_sids, station_users)
    if not sids:
        print("Demo: keine order_station_status-Zeilen — Backend pruefen.", file=sys.stderr)
        sys.exit(1)

    print(f"Demo: Order id={oid} angelegt (4 Positionen). Orderstatus-Viewer offen halten.")
    print(f"Stationen laut DB (OSS): {raw_sids} -> Demo-Reihenfolge: {sids}")
    print("Theken nacheinander (Pause je Station) ...")
    id_to_name = {int(u["id"]): (u.get("name") or "").strip() for u in station_users}
    for sid in sids:
        time.sleep(max(0.0, delay_s))
        label = id_to_name.get(sid, f"id {sid}")
        print(f"  -> {label} (id={sid}) bis Zubereitet ...")
        advance_one_station_until_ready(session, base, oid, sid, m)

    time.sleep(max(0.2, min(0.5, delay_s * 0.2)))
    advance_order_at_all_stations(session, base, oid, sids, m)

    time.sleep(max(0.0, delay_s))
    print("  -> Kasse (alle Positionen) ...")
    pay_order_open_lines(session, base, oid, m)
    print("Demo fertig: Bestellung bezahlt (verschwindet in der Orderstatus-Ansicht).")
    print(f"HTTP: {m.requests} Requests, Fehler: {m.errors}")


def pay_order_open_lines(
    session: requests.Session,
    base: str,
    order_id: int,
    metrics: Metrics | None,
) -> None:
    """Alle noch offenen Mengen per pay-item begleichen."""
    r = _req(session, "GET", base, f"/orders/{order_id}", metrics=metrics)
    if not r.ok:
        return
    items = r.json()
    if not isinstance(items, list):
        return
    for it in items:
        try:
            oi_id = int(it["id"])
            qo = int(it.get("quantity_open") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        if qo <= 0:
            continue
        pr = _req(
            session,
            "POST",
            base,
            f"/orders/{order_id}/pay-item",
            json_body={
                "order_item_id": oi_id,
                "quantity": qo,
                "payment_type": "paid",
            },
            metrics=metrics,
        )
        if not pr.ok:
            print(
                f"WARN pay-item order={order_id} item={oi_id} qty={qo} -> {pr.status_code} {pr.text[:180]}",
                file=sys.stderr,
            )


def drain_open_orders_after_load(
    base: str,
    station_ids_fallback: list[int],
    metrics: Metrics,
    *,
    max_rounds: int = 800,
) -> int:
    """
    Alle laut status-board noch offenen Bestellungen: Stationen ready, dann Kasse.
    Station-IDs kommen aus GET /orders/<id>/station-status (OSS), Fallback: [LT]-Liste.
    """
    session = requests.Session()
    station_users = fetch_all_station_users(base)
    rounds = 0
    processed = 0
    while rounds < max_rounds:
        rounds += 1
        r = _req(session, "GET", base, "/orders/status-board", metrics=metrics)
        if not r.ok:
            break
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        for o in batch:
            try:
                oid = int(o["order_id"])
            except (TypeError, ValueError, KeyError):
                continue
            sids = station_ids_for_order(session, base, oid, metrics)
            if not sids:
                sids = list(station_ids_fallback)
            sids = sort_station_ids_by_kitchen_order(sids, station_users)
            advance_order_at_all_stations(session, base, oid, sids, metrics)
            pay_order_open_lines(session, base, oid, metrics)
            processed += 1
    return processed


def stats_summary(lat: list[float]) -> str:
    if not lat:
        return "(keine Messungen)"
    lat_sorted = sorted(lat)
    def pct(p: float) -> float:
        i = int(round((p / 100.0) * (len(lat_sorted) - 1)))
        return lat_sorted[i]

    return (
        f"n={len(lat_sorted)}  mean={statistics.mean(lat_sorted):.1f}ms  "
        f"p50={pct(50):.1f}ms  p95={pct(95):.1f}ms  p99={pct(99):.1f}ms  max={max(lat_sorted):.1f}ms"
    )


def run_load(
    base: str,
    duration: float,
    rng_seed: int | None,
    *,
    poll_station_substring: str | None = None,
    advance_station_status: bool = True,
    drain_after: bool = True,
) -> None:
    rng = random.Random(rng_seed)
    metrics = Metrics()

    waiters, tables, products = fetch_runtime_ids(base)
    if len(waiters) < WAITERS or len(tables) < TABLES or not products:
        print(
            "Fehlende [LT]-Daten. Zuerst: python tools/load_test.py --base-url ... --seed",
            file=sys.stderr,
        )
        sys.exit(1)

    waiter_table_map: dict[int, list[int]] = {}
    for idx, w in enumerate(waiters[:WAITERS]):
        waiter_table_map[w["id"]] = [tables[2 * idx]["id"], tables[2 * idx + 1]["id"]]

    product_ids = [p["id"] for p in products]
    stations_all_lt = fetch_stations_for_poll(base, None)
    lt_station_ids = [int(s["id"]) for s in stations_all_lt]
    stations = fetch_stations_for_poll(base, poll_station_substring)
    if poll_station_substring:
        if not stations:
            print(
                f"Keine Station, deren Name '{poll_station_substring}' enthaelt. "
                "Admin pruefen oder Option weglassen fuer [LT]-Stationen.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Eine gefilterte Station: mehrere parallele Poller auf derselben Station (wie mehrere Terminals)
        sid = stations[0]["id"]
        station_ids_for_poll = [sid] * STATION_POLLERS
        print(f"Display-Polling: Station id={sid} ({stations[0].get('name', '')!r}) x{STATION_POLLERS}")
    else:
        if len(stations) < 4:
            print("Zu wenige [LT]-Stationen.", file=sys.stderr)
            sys.exit(1)
        # 6 Poller: Station-IDs gemäß 1,1,3,1 Terminals
        station_ids_for_poll = [
            stations[0]["id"],
            stations[1]["id"],
            stations[2]["id"],
            stations[2]["id"],
            stations[2]["id"],
            stations[3]["id"],
        ]

    stats_before = requests.get(base.rstrip("/") + "/admin/events/stats", timeout=30).json()

    print(
        f"Lasttest {duration:.0f}s: {WAITERS} Kellner-Threads, "
        f"{len(station_ids_for_poll)} Display-Poller, "
        f"Order-Intervall je Kellner {ORDER_INTERVAL_MIN}-{ORDER_INTERVAL_MAX}s, "
        f"Station-Status simuliert: {advance_station_status} ..."
    )
    t0 = time.perf_counter()

    futures = []
    with ThreadPoolExecutor(max_workers=WAITERS + len(station_ids_for_poll)) as ex:
        for w in waiters[:WAITERS]:
            futures.append(
                ex.submit(
                    waiter_loop,
                    base,
                    w,
                    waiter_table_map[w["id"]],
                    product_ids,
                    duration,
                    metrics,
                    random.Random(rng.randint(0, 2**30)),
                )
            )
        for sid in station_ids_for_poll:
            futures.append(
                ex.submit(
                    display_poller,
                    base,
                    sid,
                    duration,
                    metrics,
                    random.Random(rng.randint(0, 2**30)),
                    advance_status=advance_station_status,
                )
            )
        for f in as_completed(futures):
            f.result()

    if drain_after:
        print(
            "Drain-Phase: je Order Stationen laut OSS auf Zubereitet, "
            "dann pay-item bis keine offenen Orders mehr ...",
        )
        n_drain = drain_open_orders_after_load(base, lt_station_ids, metrics)
        print(f"Drain-Phase abgeschlossen ({n_drain} Verarbeitungsschritte).")

    elapsed = time.perf_counter() - t0
    stats_after = requests.get(base.rstrip("/") + "/admin/events/stats", timeout=30).json()

    summary_b = stats_before.get("summary") or stats_before
    summary_a = stats_after.get("summary") or stats_after
    ob = int(summary_b.get("orders_total", 0) or 0)
    oa = int(summary_a.get("orders_total", 0) or 0)

    print()
    print("=== Ergebnis ===")
    print(f"Laufzeit (Wall): {elapsed:.1f}s")
    print(f"HTTP-Requests:   {metrics.requests}  Fehler: {metrics.errors}  "
          f"Fehlerquote: {100.0 * metrics.errors / max(1, metrics.requests):.2f}%")
    print(f"Bestellungen OK (lokal gezählt): {metrics.orders_ok}")
    print(f"Latenz (alle Requests): {stats_summary(metrics.lat_ms)}")
    print(f"Orders laut Statistik: {ob} -> {oa} (Delta {oa - ob})")
    summary_end = stats_after.get("summary") or stats_after
    oo = int(summary_end.get("orders_open", 0) or 0)
    op = int(summary_end.get("orders_paid", 0) or 0)
    print(f"Endstand Event: orders_open={oo}, orders_paid={op}")

    if metrics.orders_ok != oa - ob:
        print(
            "Hinweis: Delta aus Statistik kann von lokal gezählten Orders abweichen "
            "(andere Clients, fehlgeschlagene Teile nach order_id).",
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Gastro Lasttest")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API-Basis-URL")
    p.add_argument(
        "--event-name",
        default=None,
        help="Event-Name: anlegen falls nicht vorhanden, dann als aktiv setzen (vor --seed / Lasttest)",
    )
    p.add_argument("--seed", action="store_true", help="[LT]-Testdaten im aktiven Event anlegen")
    p.add_argument("--duration", type=float, default=120.0, help="Lastdauer in Sekunden")
    p.add_argument("--random-seed", type=int, default=None, help="Zufalls-Seed (reproduzierbar)")
    p.add_argument(
        "--poll-station-substring",
        default=None,
        metavar="TEXT",
        help="Nur Station(en), deren Name TEXT enthaelt (z. B. Getränke); mehrere Poller auf erster Treffer-Station",
    )
    p.add_argument(
        "--no-advance-status",
        action="store_true",
        help="Keine POSTs auf .../orders/<id>/status (nur Display-Polling wie frueher)",
    )
    p.add_argument(
        "--no-drain",
        action="store_true",
        help="Nach dem Lastlauf KEINE Drain-Phase (Station ready + pay-item); Standard ist Drain aktiv",
    )
    p.add_argument(
        "--clear-orders",
        action="store_true",
        help="Vor allem anderen: alle Orders des aktiven Events loeschen (inkl. station_display)",
    )
    p.add_argument(
        "--live-reset",
        action="store_true",
        help="Alle Orders + alle Stammdaten/Events loeschen, neues leeres Event (--event-name oder Live)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Eine Demo-Bestellung (4 Stationen nacheinander bis Zubereitet, dann Kasse)",
    )
    p.add_argument(
        "--demo-delay",
        type=float,
        default=2.5,
        metavar="S",
        help="Pause zwischen Stationen in der Demo (Sekunden)",
    )
    p.add_argument(
        "--demo-then-load",
        action="store_true",
        help="Nach --demo: Lasttest (--duration) und Drain ausfuehren",
    )
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    health(base)
    if args.live_reset and args.clear_orders:
        print("Hinweis: --live-reset schliesst --clear-orders ein.", file=sys.stderr)
    if args.live_reset:
        live_reset_api(base, (args.event_name or "Live").strip())
    elif args.clear_orders:
        clear_orders_api(base)
    elif args.event_name:
        ensure_active_event(base, args.event_name)
    if args.seed:
        seed_data(base)
        if not args.demo:
            return

    if args.demo:
        run_demo_sequence(base, float(args.demo_delay))
        if args.demo_then_load:
            print()
            run_load(
                base,
                args.duration,
                args.random_seed,
                poll_station_substring=args.poll_station_substring,
                advance_station_status=not args.no_advance_status,
                drain_after=not args.no_drain,
            )
        return

    run_load(
        base,
        args.duration,
        args.random_seed,
        poll_station_substring=args.poll_station_substring,
        advance_station_status=not args.no_advance_status,
        drain_after=not args.no_drain,
    )


if __name__ == "__main__":
    main()
