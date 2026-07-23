#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found on PATH." >&2
  exit 1
fi

echo "Creating virtual environment in $SCRIPT_DIR/venv ..."
python3 -m venv venv

# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing dependencies from requirements.txt ..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example - fill in your exchange API credentials before running live."
fi

echo
echo "Install complete."
echo "Next steps:"
echo "  1. source venv/bin/activate"
echo "  2. edit .env with your exchange API key/secret"
echo "  3. python bot.py"
