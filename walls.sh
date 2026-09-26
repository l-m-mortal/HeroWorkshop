#!/bin/zsh
# Круговая стена базы Radiant и у фонтана (AOnt): высота над землёй. Не накапливает.
#   zsh walls.sh 400
# Второй параметр: другой тип, например   zsh walls.sh 226 D000   (тёмные стены Dire)
cd "$(dirname "$0")"
python3 map_fix.py doodads-z --types ${2:-AOnt} --offset ${1:-400} --apply
