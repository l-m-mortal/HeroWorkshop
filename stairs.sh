#!/bin/zsh
# Лестницы и стены из разрезанной сборки AshenRock7 (куски DS00..DS0M). Высота низа куска над землёй.
# Значение абсолютное (не накапливается). Меняется и запись в карте, и сама геометрия куска.
#   zsh stairs.sh 100            # все куски
#   zsh stairs.sh 100 radiant    # только Radiant (DS00-DS09, DS0E, DS0K)
#   zsh stairs.sh 100 dire       # только Dire
#   zsh stairs.sh 100 DS03       # один кусок
cd "$(dirname "$0")"
case "${2:-all}" in
  radiant) T=DS00,DS01,DS02,DS03,DS04,DS05,DS06,DS07,DS08,DS09,DS0E,DS0K ;;
  dire)    T=DS0A,DS0B,DS0C,DS0D,DS0F,DS0G,DS0H,DS0I,DS0J,DS0L,DS0M ;;
  all)     T='DS*' ;;
  *)       T=$2 ;;
esac
python3 map_fix.py doodads-z --types $T --offset ${1:-0} --apply
if [ "$T" = 'DS*' ]; then python3 map_fix.py piece-lift --offset ${1:-0} --apply; else python3 map_fix.py piece-lift --offset ${1:-0} --types $T --apply; fi
