#!/bin/zsh
# Лестницы и камни 6.77b (ARrk): высота над землёй. Повторный запуск считает от земли, не накапливает.
#   zsh stairs.sh 400
cd "$(dirname "$0")"
python3 map_fix.py doodads-z --types ARrk --offset ${1:-400} --apply
