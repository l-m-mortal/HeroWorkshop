#!/bin/zsh
# Метки DS00..DS12 над частями сборки AshenRock7 в игре (для проверки нумерации). zsh labels.sh off убирает.
cd "$(dirname "$0")"
if [ "$1" = off ]; then python3 map_fix.py part-labels --undo --apply; else python3 map_fix.py part-labels --path 'Doodads\Ashenvale\Rocks\AshenRock\AshenRock7.mdx' --types ARrk:7 --apply; fi
