"""
Unifi Stock Watcher — Product Lister
One-shot script to browse all Ubiquiti store products and get their slugs.

Usage:
  python list_products.py                  # list all products
  python list_products.py --oos            # list only out-of-stock products
  python list_products.py --region eu      # use EU store
  python list_products.py --search "pro"   # filter by name
"""

import sys
import json
import argparse
from pathlib import Path

from unifi_core import (
    REQUESTS_OK, STORE_REGIONS, CATEGORY_LABELS,
    load_settings, fetch_all_products,
    is_available, get_price,
)


def parse_args():
    p = argparse.ArgumentParser(description="List Ubiquiti store products and their slugs.")
    p.add_argument("--oos",    action="store_true", help="Show only out-of-stock products")
    p.add_argument("--region", default=None,        help="Store region: us, eu, uk, ca (default: from settings.json)")
    p.add_argument("--search", default=None,        help="Filter product names (case-insensitive)")
    p.add_argument("--json",   action="store_true", help="Output raw JSON (for scripting)")
    return p.parse_args()


def main():
    if not REQUESTS_OK:
        print("ERROR: 'requests' library is not installed.")
        print("Run: pip install requests")
        sys.exit(1)

    args     = parse_args()
    settings = load_settings()
    region   = args.region or settings.get("region", "us")

    if region not in STORE_REGIONS:
        print(f"ERROR: Unknown region '{region}'. Valid: {', '.join(STORE_REGIONS)}")
        sys.exit(1)

    print(f"Fetching products from Ubiquiti store ({STORE_REGIONS[region]['label']})…")
    print("This takes about 10 seconds.\n")

    try:
        products = fetch_all_products(region)
    except Exception as e:
        print(f"ERROR: Could not reach the store: {e}")
        sys.exit(1)

    # Apply filters
    if args.oos:
        products = [p for p in products if not is_available(p)]
    if args.search:
        needle = args.search.lower()
        products = [p for p in products if needle in p.get("title", "").lower()]

    products.sort(key=lambda p: (p.get("_category", ""), p.get("title", "")))

    if args.json:
        out = [
            {
                "title":    p.get("title", ""),
                "slug":     p.get("slug", ""),
                "status":   "Available" if is_available(p) else "SoldOut",
                "price":    get_price(p),
                "category": CATEGORY_LABELS.get(p.get("_category", ""), ""),
            }
            for p in products
        ]
        print(json.dumps(out, indent=2))
        return

    if not products:
        print("No products found matching your criteria.")
        return

    # Group by category for readability
    current_cat = None
    for p in products:
        cat = p.get("_category", "")
        if cat != current_cat:
            current_cat = cat
            label = CATEGORY_LABELS.get(cat, cat)
            print(f"\n── {label} {'─' * max(0, 50 - len(label))}")
            print(f"  {'Title':<45} {'Status':<14} {'Price':<12} Slug")
            print("  " + "─" * 85)

        title    = p.get("title", "")[:44]
        slug     = p.get("slug", "")
        status   = "✓ Available" if is_available(p) else "✗ Out of stock"
        price    = get_price(p) or ""
        print(f"  {title:<45} {status:<14} {price:<12} {slug}")

    print(f"\nTotal: {len(products)} product(s)")
    if args.oos:
        print("\nTo watch an item, add it to watched_items.json:")
        print("""  [
    { "title": "Product Name", "slug": "product-slug" }
  ]""")


if __name__ == "__main__":
    main()
