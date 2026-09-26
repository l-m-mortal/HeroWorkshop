#!/bin/zsh
# Лестницы (куски разрезанной сборки AshenRock7, типы DS00..DS0M). Высота над землёй, не накапливает.
#   zsh stairs.sh 100            # все лестницы обеих сторон
#   zsh stairs.sh 100 radiant    # только Radiant (DS00-DS09, DS0E, DS0K)
#   zsh stairs.sh 100 dire       # только Dire (DS0A-DS0D, DS0F-DS0J, DS0L, DS0M)
#   zsh stairs.sh 100 DS03       # один кусок
cd "$(dirname "$0")"
case "${2:-all}" in
  radiant) T=DS00,DS01,DS02,DS03,DS04,DS05,DS06,DS07,DS08,DS09,DS0E,DS0K ;;
  dire)    T=DS0A,DS0B,DS0C,DS0D,DS0F,DS0G,DS0H,DS0I,DS0J,DS0L,DS0M ;;
  all)     T='DS*' ;;
  *)       T=$2 ;;
esac
python3 map_fix.py doodads-z --types $T --offset ${1:-0} --apply
