#!/bin/zsh
# Стены вокруг фонтанов и баз. Высота над землёй, не накапливает.
#   zsh walls.sh 100 radiant   # белая стена Radiant: столбы AOnt и фонари-колонны CPct
#   zsh walls.sh 226 dire      # тёмная стена Dire: секции D000
#   zsh walls.sh 100 AOnt      # любой тип напрямую
cd "$(dirname "$0")"
case "${2:-radiant}" in
  radiant) T=AOnt,CPct ;;
  dire)    T=D000 ;;
  *)       T=$2 ;;
esac
python3 map_fix.py doodads-z --types $T --offset ${1:-0} --apply
