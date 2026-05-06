# UniFi Stock Watcher

A headless stock monitoring tool for the [Ubiquiti Store](https://store.ui.com). Runs on a Raspberry Pi as a cron job and sends push notifications to your iPhone via [ntfy](https://ntfy.sh) when a watched product comes back in stock.

Built with Python. No API key required — works by polling the public store page.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Watch list monitoring** — Define the products you want to track in a simple JSON file
- **iPhone push notifications via ntfy** — Instant alert with product name, price, and a tap-to-open link to the store page
- **Smart state tracking** — Only notifies on transitions (out of stock → available), no duplicate alerts
- **Product browser** — One-shot script to list the full catalog with slugs, filterable by status, category, or name
- **Multi-region support** — US, EU, UK, and Canada stores
- **Stock history** — Persistent log of every check with statistics
- **Cron-friendly** — Runs once and exits; the OS handles scheduling

## Requirements

- Raspberry Pi running Raspberry Pi OS (Bookworm or later)
- Python 3.11+
- [ntfy app](https://ntfy.sh) on your iPhone (free)

## Installation

```bash
git clone https://github.com/your-username/UnifiStockWatcher.git
cd UnifiStockWatcher
bash install_rpi.sh
```

The installer will:
1. Create a Python virtual environment (`.venv/`)
2. Install the `requests` dependency
3. Create `settings.json` with your ntfy topic pre-filled
4. Register a cron job that runs every hour

## Configuration

### settings.json

```json
{
  "region": "eu",
  "ntfy_url": "https://ntfy.sh",
  "ntfy_topic": "your-secret-topic",
  "ntfy_priority": "high"
}
```

| Field | Description |
|-------|-------------|
| `region` | Store region: `us`, `eu`, `uk`, `ca` |
| `ntfy_url` | ntfy server URL (use `https://ntfy.sh` or your self-hosted instance) |
| `ntfy_topic` | Your private ntfy topic — subscribe to it in the iPhone app |
| `ntfy_priority` | Notification priority: `low`, `default`, `high`, `urgent` |

### watched_items.json

```json
[
  { "title": "Switch Pro 24", "slug": "usw-pro-24" },
  { "title": "UniFi Express",  "slug": "ux" }
]
```

Only `title` and `slug` are required. Use `list_products.py` to find slugs.

## Usage

### 1. Find products to watch

```bash
# List all out-of-stock products (EU store)
.venv/bin/python3 list_products.py --oos --region eu

# Search by name
.venv/bin/python3 list_products.py --search "pro"

# Export as JSON (for scripting)
.venv/bin/python3 list_products.py --oos --json
```

Copy the `slug` values you want into `watched_items.json`.

### 2. Test notifications

```bash
.venv/bin/python3 unifi_watcher.py --test
```

Sends a test ntfy notification and checks your watched items.

### 3. Run manually

```bash
.venv/bin/python3 unifi_watcher.py --once
```

Checks all watched items once, sends notifications for anything newly in stock, and exits.

### 4. Cron (automatic)

The installer registers this cron entry automatically:

```
0 * * * * /home/pi/UnifiStockWatcher/.venv/bin/python3 /home/pi/UnifiStockWatcher/unifi_watcher.py --once >> /home/pi/UnifiStockWatcher/watcher.log 2>&1
```

To edit the schedule: `crontab -e`

## Project Structure

```
UnifiStockWatcher/
├── unifi_core.py        # Store API, config, notifications, history
├── unifi_watcher.py     # CLI watcher (--once for cron, --test, --setup)
├── list_products.py     # One-shot product browser
├── install_rpi.sh       # Raspberry Pi setup script
├── requirements.txt     # Python dependencies
├── LICENSE
└── README.md
```

### Generated files (not tracked)

| File | Purpose |
|------|---------|
| `watched_items.json` | Your watch list |
| `settings.json` | ntfy config and region |
| `stock_state.json` | Last known stock state per product (prevents duplicate notifications) |
| `stock_history.json` | Full event log with statistics |
| `.venv/` | Python virtual environment |

## How It Works

1. Fetches each category page from the Ubiquiti store
2. Extracts product data from the embedded `__NEXT_DATA__` JSON in the HTML
3. Parses variant `status` fields (`Available`, `SoldOut`, `ComingSoon`)
4. Compares against the previous state saved in `stock_state.json`
5. Sends an ntfy push notification for any product that transitioned to `Available`

No authentication, scraping, or rate-limit-busting — standard HTTP requests with polite delays between category fetches.

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Forked from the original Windows GUI version and adapted for headless Raspberry Pi deployment.*
