#!/bin/zsh
set -e
SCRIPT_DIR="${0:A:h}"

cd "$SCRIPT_DIR"
if [[ ! -x .venv/bin/python3 ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python3 -c 'from PIL import Image' >/dev/null 2>&1; then
  .venv/bin/pip install -r requirements.txt
fi
export PATH="$SCRIPT_DIR/.venv/bin:$PATH"

cd "$SCRIPT_DIR/HeroWorkshopUI"
swift build
exec .build/debug/HeroWorkshopUI
