#!/usr/bin/env python3
"""Create a PNG preview from a Warcraft III BLP without modifying the BLP."""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: blp_to_png.py INPUT.blp OUTPUT.png")
    source, target = map(Path, sys.argv[1:])
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGBA").save(target)


if __name__ == "__main__":
    main()
