import os
import re
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from db import DB_PATH, get_db_connection
from icon_catalog import STANDARD_ICONS, STANDARD_ICON_IDS

icons_bp = Blueprint("icons", __name__)

ICON_ROOT = Path(os.environ.get("GASTRO_ICON_DIR", str(Path(DB_PATH).parent / "uploads" / "icons")))
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
MAX_BYTES = int(os.environ.get("GASTRO_ICON_MAX_BYTES", str(512 * 1024)))


def _ensure_icon_dir() -> Path:
    ICON_ROOT.mkdir(parents=True, exist_ok=True)
    return ICON_ROOT


def _icon_url(filename: str) -> str:
    return f"/media/icons/{filename}"


def _normalize_icon_fields(icon_type: str | None, icon_ref: str | None) -> tuple[str, str | None]:
    t = str(icon_type or "none").strip().lower()
    if t not in ("none", "standard", "custom"):
        t = "none"
    ref = str(icon_ref).strip() if icon_ref not in (None, "") else None
    if t == "none":
        return "none", None
    if t == "standard":
        if ref not in STANDARD_ICON_IDS:
            return "none", None
        return "standard", ref
    if t == "custom":
        if not ref or not ref.isdigit():
            return "none", None
        return "custom", ref
    return "none", None


@icons_bp.route("/icons/standard", methods=["GET"])
def list_standard_icons():
    return jsonify({"icons": STANDARD_ICONS})


@icons_bp.route("/admin/icons", methods=["GET"])
def list_custom_icons():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, name, filename, created_at
        FROM custom_icons
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["url"] = _icon_url(d["filename"])
        out.append(d)
    return jsonify(out)


@icons_bp.route("/admin/icons/upload", methods=["POST"])
def upload_custom_icon():
    name = (request.form.get("name") or "").strip() or "Icon"
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "file required"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "invalid file type"}), 400

    raw = file.read()
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "file too large (max 512 KB)"}), 400

    _ensure_icon_dir()
    filename = f"{uuid.uuid4().hex}{ext}"
    path = ICON_ROOT / filename
    path.write_bytes(raw)

    conn = get_db_connection()
    cur = conn.execute(
        "INSERT INTO custom_icons (name, filename) VALUES (?, ?)",
        (name, filename),
    )
    icon_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "id": icon_id,
        "name": name,
        "filename": filename,
        "url": _icon_url(filename),
    })


@icons_bp.route("/admin/icons/delete", methods=["POST"])
def delete_custom_icon():
    data = request.json or {}
    icon_id = data.get("id")
    try:
        icon_id = int(icon_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid id"}), 400

    conn = get_db_connection()
    row = conn.execute(
        "SELECT filename FROM custom_icons WHERE id = ?",
        (icon_id,),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404

    in_use = conn.execute(
        """
        SELECT COUNT(*) AS c FROM products
        WHERE icon_type = 'custom' AND icon_ref = ?
        """,
        (str(icon_id),),
    ).fetchone()["c"]
    if in_use:
        conn.close()
        return jsonify({"error": "icon still used by products"}), 409

    conn.execute("DELETE FROM custom_icons WHERE id = ?", (icon_id,))
    conn.commit()
    conn.close()

    path = ICON_ROOT / row["filename"]
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass

    return jsonify({"status": "ok"})


@icons_bp.route("/media/icons/<path:filename>", methods=["GET"])
def serve_icon(filename: str):
    safe = re.sub(r"[^a-zA-Z0-9._-]", "", Path(filename).name)
    if not safe:
        return jsonify({"error": "not found"}), 404
    directory = _ensure_icon_dir()
    if not (directory / safe).is_file():
        return jsonify({"error": "not found"}), 404
    return send_from_directory(str(directory), safe, max_age=3600)


def enrich_product_icon(conn, product_row: dict) -> dict:
    """Add icon_url / icon_emoji for API responses."""
    d = dict(product_row)
    t = d.get("icon_type") or "none"
    ref = d.get("icon_ref")
    d["icon_emoji"] = None
    d["icon_url"] = None
    if t == "standard" and ref:
        for item in STANDARD_ICONS:
            if item["id"] == ref:
                d["icon_emoji"] = item["emoji"]
                break
    elif t == "custom" and ref:
        row = conn.execute(
            "SELECT filename FROM custom_icons WHERE id = ?",
            (int(ref),),
        ).fetchone()
        if row:
            d["icon_url"] = _icon_url(row["filename"])
    return d
