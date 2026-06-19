"""Produktname → passendes Standard-Icon (für Vereinsgastronomie / aktuelle Karte)."""

from __future__ import annotations

import re
import unicodedata

from icon_catalog import STANDARD_ICON_BY_ID

# (Muster, icon_id) – erste Treffer gewinnt
_NAME_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"spundek", re.I), "cheese_spread"),
    (re.compile(r"huober.*brezel|brezel", re.I), "pretzel"),
    (re.compile(r"chips|knabber", re.I), "chips"),
    (re.compile(r"hausmacherwurst", re.I), "sausage_plate"),
    (re.compile(r"rindswurst|brötchen|bratwurst|im\s+br", re.I), "sausage_roll"),
    (re.compile(r"weizen", re.I), "beer_weizen"),
    (re.compile(r"alkoholfrei|alkfrei", re.I), "beer_nonalc"),
    (re.compile(r"kölsch|kolsch|früh|fruh", re.I), "beer_kolsch"),
    (re.compile(r"pils", re.I), "beer_pils"),
    (re.compile(r"helles|büble|bueble", re.I), "beer_helles"),
    (re.compile(r"mineralwasser.*1[,.]0|1[,.]0.*mineral", re.I), "water_bottle"),
    (re.compile(r"mineralwasser|wasser", re.I), "water_glass"),
    (re.compile(r"sekt.*0[,.]75|sekt.*flasche", re.I), "sekt_bottle"),
    (re.compile(r"sekt", re.I), "sekt_glass"),
    (re.compile(r"riesling", re.I), "wine_white"),
    (re.compile(r"\brose\b|rosé", re.I), "wine_rose"),
    (re.compile(r"rotwein", re.I), "wine_red"),
    (re.compile(r"chantr", re.I), "wine_chantré"),
    (re.compile(r"hätchen.*tablett|haetchen.*tablett|tablett", re.I), "wine_carafe"),
    (re.compile(r"schoppen.*gespritzt|gespritzt|schorle", re.I), "wine_spritzer"),
    (re.compile(r"apfelschorle", re.I), "apfelschorle"),
    (re.compile(r"fanta|orange", re.I), "fanta"),
    (re.compile(r"sprite|zitrone|limo", re.I), "lemonade"),
    (re.compile(r"cola\s*zero|zero|light", re.I), "softdrink_light"),
    (re.compile(r"softdrink|cola|limonade", re.I), "softdrink"),
    (re.compile(r"saft", re.I), "juice"),
    (re.compile(r"kaffee", re.I), "coffee"),
    (re.compile(r"tee", re.I), "tea"),
    (re.compile(r"pizza", re.I), "pizza"),
    (re.compile(r"schnitzel", re.I), "schnitzel"),
    (re.compile(r"pommes", re.I), "fries"),
    (re.compile(r"kuchen|torte", re.I), "cake"),
    (re.compile(r"\beis\b", re.I), "ice"),
]


def _normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold().strip()


def suggest_icon_for_product_name(name: str) -> str | None:
    raw = (name or "").strip()
    if not raw:
        return None
    norm = _normalize_name(raw)
    for pattern, icon_id in _NAME_RULES:
        if pattern.search(raw) or pattern.search(norm):
            if icon_id in STANDARD_ICON_BY_ID:
                return icon_id
    return None
