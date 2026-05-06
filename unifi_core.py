"""
Unifi Stock Watcher — Core Module
Shared store API, configuration, notifications, price & stock history.
"""

import re
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).parent
CONFIG_FILE    = BASE_DIR / "watched_items.json"
SETTINGS_FILE  = BASE_DIR / "settings.json"
HISTORY_FILE   = BASE_DIR / "stock_history.json"
STATE_FILE     = BASE_DIR / "stock_state.json"

# ── Store constants ──────────────────────────────────────────────────────────

STORE_REGIONS = {
    "us": {"label": "United States", "path": "us/en"},
    "eu": {"label": "Europe",        "path": "eu/en"},
    "uk": {"label": "United Kingdom", "path": "uk/en"},
    "ca": {"label": "Canada",        "path": "ca/en"},
}

STORE_BASE = "https://store.ui.com"

CATEGORIES = [
    "category/all-cloud-gateways",
    "category/all-switching",
    "category/all-wifi",
    "category/all-cameras-nvrs",
    "category/all-door-access",
    "category/all-integrations",
    "category/all-advanced-hosting",
    "category/accessories-cables-dacs",
    "category/network-storage",
]

CATEGORY_LABELS = {
    "category/all-cloud-gateways":      "Cloud Gateways",
    "category/all-switching":           "Switching",
    "category/all-wifi":                "WiFi",
    "category/all-cameras-nvrs":        "Cameras & NVRs",
    "category/all-door-access":         "Door Access",
    "category/all-integrations":        "Integrations",
    "category/all-advanced-hosting":    "Advanced Hosting",
    "category/accessories-cables-dacs": "Accessories, Cables & DACs",
    "category/network-storage":         "Network Storage",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


def _extract_next_data(html):
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError("__NEXT_DATA__ not found in page")
    return json.loads(m.group(1))

# ── Default settings ─────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "poll_interval":  3600,
    "region":         "us",
    "max_retries":    3,
    "ntfy_url":       "https://ntfy.sh",
    "ntfy_topic":     "",
    "ntfy_priority":  "high",
}

# ── Settings load/save ───────────────────────────────────────────────────────

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            s = json.loads(SETTINGS_FILE.read_text())
            merged = DEFAULT_SETTINGS.copy()
            merged.update(s)
            return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


# ── Store API ────────────────────────────────────────────────────────────────

def fetch_all_products(region="us", progress_cb=None, error_cb=None):
    """Fetch all products from every category, deduplicated. Returns list of dicts."""
    products = {}
    region_path = STORE_REGIONS[region]["path"]
    for i, cat in enumerate(CATEGORIES):
        url = f"{STORE_BASE}/{region_path}/{cat}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = _extract_next_data(r.text)
            pp   = data.get("props", {}).get("pageProps", {})
            for subcat in pp.get("subCategories", []):
                for p in subcat.get("products", []):
                    if p.get("slug"):
                        p["_category"] = cat
                        products[p["slug"]] = p
            for p in pp.get("products", []):
                if p.get("slug"):
                    p.setdefault("_category", cat)
                    products.setdefault(p["slug"], p)
        except Exception as e:
            print(f"[UnifiWatcher] Category fetch failed: {cat} — {e}")
            if error_cb:
                try:
                    error_cb(cat, e)
                except Exception:
                    pass
        if progress_cb:
            progress_cb(int((i + 1) / len(CATEGORIES) * 100))
        time.sleep(0.3)
    print(f"[UnifiWatcher] Fetched {len(products)} unique products across {len(CATEGORIES)} categories")
    return list(products.values())


def is_available(product):
    return any(v.get("status") == "Available" for v in product.get("variants", []))


def _format_price(price_val):
    """Format a price value which may be a Money dict, number, or string."""
    if isinstance(price_val, str):
        return price_val
    if isinstance(price_val, dict):
        amount   = price_val.get("amount", 0)
        currency = price_val.get("currency", "USD")
        symbols  = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$",
                     "AUD": "A$", "SEK": "", "NOK": "", "DKK": ""}
        sym = symbols.get(currency, "")
        formatted = f"{amount / 100:,.2f}"
        if sym:
            return f"{sym}{formatted}"
        return f"{formatted} {currency}"
    if isinstance(price_val, (int, float)):
        return f"${price_val:,.2f}"
    return str(price_val)


def get_price(product):
    """Extract the display price from a product dict.
    displayPrice can be a Money dict like {'amount': 39900, 'currency': 'USD'}
    or a plain number or string.
    """
    for v in product.get("variants", []):
        price = v.get("displayPrice") or v.get("price")
        if price is not None:
            return _format_price(price)
    return None


def check_slug(slug, region="us", retries=3):
    """Check if a product slug is in stock. Returns (in_stock: bool, price: str|None)."""
    region_path = STORE_REGIONS[region]["path"]
    url = f"{STORE_BASE}/{region_path}/products/{slug}"

    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data     = _extract_next_data(r.text)
            pp       = data.get("props", {}).get("pageProps", {})
            products = pp.get("collection", {}).get("products", [])
            if not products:
                return False, None
            product  = next((p for p in products if p.get("slug") == slug), products[0])
            variants = product.get("variants", [])
            in_stock = any(v.get("status") == "Available" for v in variants)
            price    = None
            for v in variants:
                p = v.get("displayPrice") or v.get("price")
                if p is not None:
                    price = _format_price(p)
                    break
            return in_stock, price
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    raise last_err or RuntimeError(f"Failed to check {slug} after {retries} attempts")


# ── Config load/save ─────────────────────────────────────────────────────────

def load_watched():
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            for item in data:
                item.setdefault("favourite", False)
                item.setdefault("price", None)
                item.setdefault("added_at", None)
            return data
        except Exception:
            return []
    return []


def save_watched(items):
    CONFIG_FILE.write_text(json.dumps(items, indent=2))


# ── Stock history ────────────────────────────────────────────────────────────

class StockHistory:
    """Persist stock check events to a JSON file for history/stats."""

    def __init__(self, path=HISTORY_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                pass
        return {"events": [], "stats": {"total_checks": 0, "in_stock_alerts": 0}}

    def _save(self):
        # Keep only last 2000 events to prevent unbounded growth
        if len(self._data["events"]) > 2000:
            self._data["events"] = self._data["events"][-2000:]
        self._path.write_text(json.dumps(self._data, indent=2))

    def record_check(self, slug, title, in_stock, price=None):
        with self._lock:
            self._data["stats"]["total_checks"] += 1
            if in_stock:
                self._data["stats"]["in_stock_alerts"] += 1
            self._data["events"].append({
                "ts":       datetime.now().isoformat(),
                "slug":     slug,
                "title":    title,
                "in_stock": in_stock,
                "price":    price,
            })
            self._save()

    def get_stats(self):
        with self._lock:
            return self._data["stats"].copy()

    def get_events(self, slug=None, limit=50):
        with self._lock:
            events = self._data["events"]
            if slug:
                events = [e for e in events if e["slug"] == slug]
            return events[-limit:]

    def last_in_stock(self, slug):
        with self._lock:
            for e in reversed(self._data["events"]):
                if e["slug"] == slug and e["in_stock"]:
                    return e["ts"]
            return None

    def clear(self):
        with self._lock:
            self._data = {"events": [], "stats": {"total_checks": 0, "in_stock_alerts": 0}}
            self._save()


# Global instance
stock_history = StockHistory()


# ── Notification ─────────────────────────────────────────────────────────────

def notify_ntfy(title, message, settings=None, click_url=None):
    """Send a push notification via ntfy (https://ntfy.sh or self-hosted)."""
    if settings is None:
        settings = load_settings()
    ntfy_url   = settings.get("ntfy_url", "").rstrip("/")
    ntfy_topic = settings.get("ntfy_topic", "")
    priority   = settings.get("ntfy_priority", "high")

    if not ntfy_url or not ntfy_topic:
        print(f"  [ntfy] Not configured — set ntfy_url and ntfy_topic in settings.json")
        print(f"  *** ALERT: {title} — {message}")
        return

    try:
        headers = {
            "Title":    title,
            "Priority": priority,
            "Tags":     "bell,white_check_mark",
        }
        if click_url:
            headers["Click"]   = click_url
            headers["Actions"] = f"view, Open Store, {click_url}"

        requests.post(
            f"{ntfy_url}/{ntfy_topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        print(f"  [ntfy] Notification sent: {title}")
    except Exception as e:
        print(f"  [ntfy] Notification failed: {e}")
        print(f"  *** ALERT: {title} — {message}")


# ── Export / Import ──────────────────────────────────────────────────────────

def export_watchlist(filepath):
    """Export current watch list to a JSON file."""
    items = load_watched()
    Path(filepath).write_text(json.dumps(items, indent=2))
    return len(items)


def import_watchlist(filepath):
    """Import watch list from a JSON file, merging with existing."""
    new_items = json.loads(Path(filepath).read_text())
    existing  = load_watched()
    slugs     = {w["slug"] for w in existing}
    added     = 0
    for item in new_items:
        if item.get("slug") and item["slug"] not in slugs:
            item.setdefault("favourite", False)
            item.setdefault("price", None)
            item.setdefault("added_at", datetime.now().isoformat())
            existing.append(item)
            slugs.add(item["slug"])
            added += 1
    save_watched(existing)
    return added
