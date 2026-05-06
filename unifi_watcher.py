"""
Unifi Stock Watcher — CLI  (v2.0)
Headless console watcher using the shared core module.

Commands:
  python unifi_watcher.py           -- run watcher (setup on first run)
  python unifi_watcher.py --setup   -- re-run product picker
  python unifi_watcher.py --once    -- check once and exit (for cron)
  python unifi_watcher.py --test    -- verify notifications + stock detection
"""

import sys
import json
import time
from datetime import datetime
from pathlib import Path

from unifi_core import (
    REQUESTS_OK, STORE_BASE, STORE_REGIONS, CATEGORIES, CATEGORY_LABELS,
    STATE_FILE,
    load_settings, fetch_all_products,
    is_available, get_price, check_slug,
    load_watched, save_watched, stock_history,
    notify_ntfy,
)


def store_home(region="us"):
    return f"{STORE_BASE}/{STORE_REGIONS[region]['path']}"


# ── Interactive product picker ────────────────────────────────────────────────

def run_setup():
    settings = load_settings()
    region   = settings.get("region", "us")

    print("=" * 60)
    print("  Unifi Stock Watcher v2.0 — Product Picker")
    print(f"  Region: {STORE_REGIONS[region]['label']}")
    print("=" * 60)
    print()
    print("Fetching out-of-stock items from the Unifi store...")
    print("(This takes about 10 seconds)\n")

    try:
        all_products = fetch_all_products(region)
    except Exception as e:
        print(f"ERROR: Could not reach the store: {e}")
        input("\nPress Enter to exit.")
        sys.exit(1)

    out_of_stock = sorted(
        [p for p in all_products if not is_available(p)],
        key=lambda p: p["title"]
    )

    if not out_of_stock:
        print("Everything appears to be in stock right now!")
        input("\nPress Enter to exit.")
        sys.exit(0)

    print(f"Found {len(out_of_stock)} out-of-stock items:\n")
    print(f"  {'#':<5} {'Product Name':<45} {'Price'}")
    print("  " + "-" * 60)
    for i, p in enumerate(out_of_stock, 1):
        price = get_price(p) or ""
        print(f"  {i:<5} {p['title']:<45} {price}")

    print()
    print("Enter the numbers of items you want to watch,")
    print("separated by commas.  Example: 1, 4, 7")
    print()

    while True:
        raw = input("Your selection: ").strip()
        if not raw:
            print("Please enter at least one number.")
            continue
        try:
            picks = [int(x.strip()) for x in raw.split(",")]
            if all(1 <= p <= len(out_of_stock) for p in picks):
                break
            print(f"Please enter numbers between 1 and {len(out_of_stock)}.")
        except ValueError:
            print("Invalid input — please enter numbers separated by commas.")

    watched = []
    for i in picks:
        p = out_of_stock[i - 1]
        watched.append({
            "title":     p["title"],
            "slug":      p["slug"],
            "favourite": False,
            "price":     get_price(p),
            "added_at":  datetime.now().isoformat(),
        })

    save_watched(watched)

    print()
    print("=" * 60)
    print("  Watching these items:")
    for w in watched:
        price_str = f" ({w['price']})" if w.get("price") else ""
        print(f"    - {w['title']}{price_str}")
    print()
    print(f"  Saved to watched_items.json")
    print("=" * 60)
    print()

    return watched


# ── Self-test ─────────────────────────────────────────────────────────────────

def test_mode():
    settings = load_settings()
    region   = settings.get("region", "us")

    print("=" * 60)
    print("  Unifi Stock Watcher v2.0 — TEST MODE")
    print("=" * 60)
    print()

    print("Step 1/3  Firing a test ntfy notification…")
    notify_ntfy(
        "TEST: Unifi Stock Watcher works!",
        "This is exactly what an in-stock alert looks like.",
        settings,
    )
    print("          Done. Did you receive a notification?\n")
    time.sleep(2)

    IN_STOCK_TEST = {"title": "Access Point U7 Pro", "slug": "u7-pro"}
    print(f"Step 2/3  Verifying stock detection…")
    print(f"          Checking: {IN_STOCK_TEST['title']}")
    try:
        in_stock, price = check_slug(IN_STOCK_TEST["slug"], region)
        price_str = f" ({price})" if price else ""
        if in_stock:
            print(f"          PASS — detected as IN STOCK{price_str}.\n")
        else:
            print(f"          WARNING — showed as out of stock{price_str}.\n")
    except Exception as e:
        print(f"          FAIL — could not reach the store: {e}\n")
    time.sleep(1)

    watched = load_watched()
    if watched:
        print("Step 3/3  Checking your watched items…")
        try:
            for item in watched:
                in_stock, price = check_slug(item["slug"], region)
                price_str = f" ({price})" if price else ""
                if in_stock:
                    note = f"IN STOCK{price_str} — you'd get a notification now!"
                else:
                    note = f"Out of stock{price_str} — watcher will alert you."
                print(f"          {item['title']}: {note}")
        except Exception as e:
            print(f"          Could not check: {e}")
        print()
    else:
        print("Step 3/3  No watched items configured yet — run --setup first.\n")

    print("=" * 60)
    print("  Test complete. Run without --test to start watching.")
    print("=" * 60)


# ── Main watcher loop ─────────────────────────────────────────────────────────

def main():
    settings = load_settings()
    region   = settings.get("region", "us")
    interval = settings.get("poll_interval", 60)

    watched = load_watched()
    if not watched:
        print("No watched items found — let's pick some now.\n")
        watched = run_setup()
        print("Starting watcher in 3 seconds…\n")
        time.sleep(3)

    print("=" * 60)
    print("  Unifi Stock Watcher v2.0 — Running")
    print(f"  Region: {STORE_REGIONS[region]['label']}  ·  Interval: {interval}s")
    for w in watched:
        price_str = f" ({w.get('price', '')})" if w.get("price") else ""
        print(f"    - {w['title']}{price_str}")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    notified = {w["slug"]: False for w in watched}

    while True:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}]  Checking…")
        for item in watched:
            slug, title = item["slug"], item["title"]
            try:
                in_stock, price = check_slug(slug, region)
                price_str = f" ({price})" if price else ""

                stock_history.record_check(slug, title, in_stock, price)

                if in_stock:
                    print(f"          {'IN STOCK':<16}  {title}{price_str}")
                else:
                    print(f"          {'out of stock':<16}  {title}{price_str}")

                if in_stock and not notified[slug]:
                    notify_ntfy(
                        f"IN STOCK: {title}",
                        f"{title} is now available on the Unifi store!{price_str}",
                        settings,
                        click_url=f"{store_home(region)}/products/{slug}",
                    )
                    notified[slug] = True
                    print("          >>> Notification sent!")
                elif not in_stock:
                    notified[slug] = False
            except Exception as e:
                print(f"          WARNING  {title}: {e}")

        print(f"          Next check in {interval}s\n")
        time.sleep(interval)


# ── Single-run mode (for cron) ────────────────────────────────────────────────

def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def run_once():
    """Check all watched items once, notify on in-stock transitions, then exit."""
    settings = load_settings()
    region   = settings.get("region", "us")

    watched = load_watched()
    if not watched:
        print("No watched items — add items to watched_items.json first.")
        sys.exit(0)

    state = _load_state()
    now   = datetime.now().isoformat()

    print(f"[{now}] Checking {len(watched)} item(s) — region: {STORE_REGIONS[region]['label']}")

    for item in watched:
        slug, title = item["slug"], item["title"]
        try:
            in_stock, price = check_slug(slug, region)
            price_str = f" ({price})" if price else ""
            status    = "IN STOCK" if in_stock else "out of stock"
            print(f"  {status:<16}  {title}{price_str}")

            stock_history.record_check(slug, title, in_stock, price)

            was_in_stock = state.get(slug, {}).get("in_stock")
            if in_stock and not was_in_stock:
                notify_ntfy(
                    f"IN STOCK: {title}",
                    f"{title} is now available{price_str}!",
                    settings,
                    click_url=f"{store_home(region)}/products/{slug}",
                )
                print(f"  >>> Notification sent for {title}")

            state[slug] = {"in_stock": in_stock, "last_checked": now}

        except Exception as e:
            print(f"  WARNING  {title}: {e}")

    _save_state(state)
    print("Done.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not REQUESTS_OK:
        print("Installing requests…")
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "requests", "--quiet"])

    if "--test" in sys.argv:
        test_mode()
    elif "--once" in sys.argv:
        run_once()
    elif "--setup" in sys.argv:
        run_setup()
        print("Starting watcher in 3 seconds…\n")
        time.sleep(3)
        main()
    else:
        try:
            main()
        except KeyboardInterrupt:
            print("\nStopped.")
