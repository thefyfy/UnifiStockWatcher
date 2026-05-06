#!/usr/bin/env bash
# Unifi Stock Watcher — Raspberry Pi installer
# Usage: bash install_rpi.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="python3"

echo "======================================================"
echo "  Unifi Stock Watcher — Raspberry Pi Setup"
echo "======================================================"
echo ""

# ── Check Python ──────────────────────────────────────────

if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: python3 not found. Install it with:"
    echo "  sudo apt install python3 python3-venv"
    exit 1
fi
echo "Python: $($PYTHON --version)"

# ── Create virtualenv ─────────────────────────────────────

echo ""
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment…"
    $PYTHON -m venv "$VENV_DIR"
    echo "  ✓ Virtual environment created at .venv/"
else
    echo "  ✓ Virtual environment already exists"
fi

VENV_PYTHON="$VENV_DIR/bin/python3"

# ── Install dependencies ──────────────────────────────────

echo "Installing Python dependencies…"
"$VENV_PYTHON" -m pip install --quiet --upgrade requests
echo "  ✓ requests installed"

# ── Create watched_items.json if missing ──────────────────

if [ ! -f "$SCRIPT_DIR/watched_items.json" ]; then
    echo "[]" > "$SCRIPT_DIR/watched_items.json"
    echo "  ✓ watched_items.json created (empty)"
fi

# ── Create settings.json if missing ──────────────────────

if [ ! -f "$SCRIPT_DIR/settings.json" ]; then
    cat > "$SCRIPT_DIR/settings.json" <<'EOF'
{
  "region": "eu",
  "ntfy_url": "https://ntfy.sh",
  "ntfy_topic": "your-secret-topic",
  "ntfy_priority": "high"
}
EOF
    echo "  ✓ settings.json created"
    echo ""
    echo "  IMPORTANT: Edit settings.json and set your ntfy_topic."
fi

# ── Set up cron ───────────────────────────────────────────

echo ""
echo "Setting up cron job (every hour)…"

CRON_CMD="0 * * * * $VENV_PYTHON $SCRIPT_DIR/unifi_watcher.py --once >> $SCRIPT_DIR/watcher.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/unifi_watcher.py"; then
    echo "  ✓ Cron job already configured — skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "  ✓ Cron job added: runs every hour"
fi

# ── Summary ───────────────────────────────────────────────

echo ""
echo "======================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Browse products:  $VENV_PYTHON list_products.py --oos"
echo "  2. Edit watched_items.json — add items to watch"
echo "  3. Test notification: $VENV_PYTHON unifi_watcher.py --test"
echo "  4. Test single run:   $VENV_PYTHON unifi_watcher.py --once"
echo "  5. Cron runs automatically every hour."
echo ""
echo "  Logs: $SCRIPT_DIR/watcher.log"
echo "======================================================"
