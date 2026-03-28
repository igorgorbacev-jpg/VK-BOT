import datetime
import json
import os

FAVORITES_FILE = "favorites.json"
BLACKLIST_FILE = "blacklist.json"


def _load_json(path):
    """Load a JSON list from file. Returns [] if file does not exist."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    """Write data as JSON to file atomically (STOR-03)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def add_to_favorites(owner_id, candidate):
    """Add candidate to favorites.json. Returns 'added' or 'duplicate'."""
    data = _load_json(FAVORITES_FILE)
    if any(e["id"] == candidate["id"] for e in data):
        return "duplicate"
    entry = {
        **candidate,
        "owner_id": owner_id,
        "added_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    data.append(entry)
    _save_json(FAVORITES_FILE, data)
    return "added"


def add_to_blacklist(owner_id, candidate):
    """Add candidate to blacklist.json. Returns 'added' or 'duplicate'."""
    data = _load_json(BLACKLIST_FILE)
    if any(e["id"] == candidate["id"] for e in data):
        return "duplicate"
    entry = {
        **candidate,
        "owner_id": owner_id,
        "added_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    data.append(entry)
    _save_json(BLACKLIST_FILE, data)
    return "added"
