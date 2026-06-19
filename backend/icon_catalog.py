"""Standard product icons – distinct Twemoji-Grafiken (einheitlich auf allen Geräten)."""

TWEMOJI_VERSION = "14.0.2"
TWEMOJI_CDN = (
    f"https://cdn.jsdelivr.net/gh/twitter/twemoji@{TWEMOJI_VERSION}/assets/72x72"
)


def twemoji_image_url(codepoint: str) -> str:
    return f"{TWEMOJI_CDN}/{codepoint}.png"


# id, label (Admin-Auswahl), emoji (Vorschau im Dropdown), twemoji (eindeutige Grafik)
STANDARD_ICONS = [
    # Bier
    {"id": "beer_helles", "label": "Helles / Lager (Becher)", "emoji": "🍺", "twemoji": "1f37a"},
    {"id": "beer_kolsch", "label": "Kölsch / helles Bier (Maß)", "emoji": "🍻", "twemoji": "1f37b"},
    {"id": "beer_pils", "label": "Pils (Flasche)", "emoji": "🍾", "twemoji": "1f37e"},
    {"id": "beer_weizen", "label": "Weizenbier", "emoji": "🍻", "twemoji": "1f37b"},
    {"id": "beer_nonalc", "label": "Alkoholfreies Bier", "emoji": "🥤", "twemoji": "1f9c3"},
    # Softdrinks & Wasser
    {"id": "softdrink", "label": "Softdrink / Cola", "emoji": "🥤", "twemoji": "1f964"},
    {"id": "softdrink_light", "label": "Softdrink Light / Zero", "emoji": "🧃", "twemoji": "1f9c3"},
    {"id": "fanta", "label": "Fanta / Orange-Limo", "emoji": "🍊", "twemoji": "1f34a"},
    {"id": "lemonade", "label": "Zitronenlimo / Sprite", "emoji": "🍋", "twemoji": "1f34b"},
    {"id": "water_glass", "label": "Wasser (Glas / 0,2)", "emoji": "💧", "twemoji": "1f4a7"},
    {"id": "water_bottle", "label": "Wasser (Flasche / 1,0)", "emoji": "🫗", "twemoji": "1fad7"},
    {"id": "juice", "label": "Saft", "emoji": "🧃", "twemoji": "1f9c3"},
    {"id": "apfelschorle", "label": "Apfelschorle", "emoji": "🍎", "twemoji": "1f34e"},
    # Wein & Sekt
    {"id": "wine_red", "label": "Rotwein", "emoji": "🍷", "twemoji": "1f377"},
    {"id": "wine_white", "label": "Weißwein / Riesling", "emoji": "🥂", "twemoji": "1f942"},
    {"id": "wine_rose", "label": "Roséwein", "emoji": "🌹", "twemoji": "1f339"},
    {"id": "wine_chantré", "label": "Chantré / süßer Wein", "emoji": "🍸", "twemoji": "1f378"},
    {"id": "wine_carafe", "label": "Wein (Kanne / Tablett)", "emoji": "🍷", "twemoji": "1f377"},
    {"id": "wine_spritzer", "label": "Weinschorle / Gespritzter", "emoji": "🍹", "twemoji": "1f379"},
    {"id": "sekt_glass", "label": "Sekt (Glas / 0,1)", "emoji": "🥂", "twemoji": "1f942"},
    {"id": "sekt_bottle", "label": "Sekt (Flasche)", "emoji": "🍾", "twemoji": "1f37e"},
    # Speisen
    {"id": "pretzel", "label": "Brezel", "emoji": "🥨", "twemoji": "1f968"},
    {"id": "sausage_roll", "label": "Wurst im Brötchen", "emoji": "🌭", "twemoji": "1f32d"},
    {"id": "sausage_plate", "label": "Wurst mit Brot", "emoji": "🥩", "twemoji": "1f356"},
    {"id": "cheese_spread", "label": "Spundekäs / Käse", "emoji": "🧀", "twemoji": "1f9c0"},
    {"id": "chips", "label": "Chips / Knabbereien", "emoji": "🥔", "twemoji": "1f954"},
    {"id": "sandwich", "label": "Brotzeit / Sandwich", "emoji": "🥪", "twemoji": "1f96a"},
    {"id": "fries", "label": "Pommes", "emoji": "🍟", "twemoji": "1f35f"},
    {"id": "schnitzel", "label": "Schnitzel", "emoji": "🍖", "twemoji": "1f356"},
    {"id": "pizza", "label": "Pizza", "emoji": "🍕", "twemoji": "1f355"},
    {"id": "cake", "label": "Kuchen", "emoji": "🍰", "twemoji": "1f370"},
    {"id": "ice", "label": "Eis", "emoji": "🍦", "twemoji": "1f366"},
    # Heißgetränke
    {"id": "coffee", "label": "Kaffee", "emoji": "☕", "twemoji": "2615"},
    {"id": "tea", "label": "Tee", "emoji": "🍵", "twemoji": "1f375"},
    # Allgemein
    {"id": "food_generic", "label": "Speise (allgemein)", "emoji": "🍽️", "twemoji": "1f37d"},
    {"id": "drink_generic", "label": "Getränk (allgemein)", "emoji": "🥤", "twemoji": "1f964"},
]

STANDARD_ICON_IDS = {x["id"] for x in STANDARD_ICONS}
STANDARD_ICON_BY_ID = {x["id"]: x for x in STANDARD_ICONS}

# Alte Icon-IDs aus früheren Versionen → neue Zuordnung
LEGACY_ICON_MAP = {
    "cola": "softdrink",
    "cola_zero": "softdrink_light",
    "sprite": "lemonade",
    "beer": "beer_helles",
    "beer_radler": "beer_kolsch",
    "beer_wheat": "beer_weizen",
    "beer_nonalc": "beer_nonalc",
    "water": "water_glass",
    "water_sparkling": "water_bottle",
    "wine_red": "wine_red",
    "wine_white": "wine_white",
    "sekt": "sekt_bottle",
    "cocktail": "wine_spritzer",
    "bratwurst": "sausage_roll",
    "currywurst": "sausage_roll",
    "pretzel": "pretzel",
    "cheese": "cheese_spread",
    "chips": "chips",
    "sandwich": "sandwich",
    "fries": "fries",
    "schnitzel": "schnitzel",
    "pizza": "pizza",
    "cake": "cake",
    "ice": "ice",
    "coffee": "coffee",
    "tea": "tea",
    "food_generic": "food_generic",
    "drink_generic": "drink_generic",
}


def resolve_standard_icon_id(icon_ref: str | None) -> str | None:
    if not icon_ref:
        return None
    ref = str(icon_ref).strip()
    if ref in STANDARD_ICON_IDS:
        return ref
    return LEGACY_ICON_MAP.get(ref)


def standard_icon_image_url(icon_id: str) -> str | None:
    resolved = resolve_standard_icon_id(icon_id) or icon_id
    item = STANDARD_ICON_BY_ID.get(resolved)
    if not item:
        return None
    cp = item.get("twemoji")
    if not cp:
        return None
    return twemoji_image_url(cp)
