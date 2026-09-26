#!/bin/zsh
# Куски модели-сборки AshenRock7 (лестницы и стены обеих баз, типы DS00..): высота над землёй.
# Не накапливает. Один кусок: zsh stairs.sh 40 DS03
#   zsh stairs.sh 0
cd "$(dirname "$0")"
python3 map_fix.py doodads-z --types ${2:-'DS*'} --offset ${1:-0} --apply
