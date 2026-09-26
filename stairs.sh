#!/bin/zsh
# Куски разрезанной сборки AshenRock7 (39 штук, DS00..DS12). Высота низа куска над землёй, абсолютная.
#   zsh stairs.sh 0 all          # все
#   zsh stairs.sh 0 radiant      # всё на стороне Radiant
#   zsh stairs.sh 0 dire         # всё на стороне Dire
#   zsh stairs.sh 0 rad-wall     # плиты стены/спусков у базы Radiant (DS00-DS04, DS0B-DS0D)
#   zsh stairs.sh 0 rad-deco     # эмблемы и камни у базы Radiant (DS05-DS0A)
#   zsh stairs.sh 0 dire-wall    # плиты Dire (DS0E-DS0V без DS0S)
#   zsh stairs.sh 0 dire-deco    # эмблемы Dire (DS0W-DS0Y)
#   zsh stairs.sh 0 river        # статуи и ступени у реки/центра (DS0S, DS0Z-DS12)
#   zsh stairs.sh 0 DS00,DS01    # любые куски
# Карта кусков (мировые координаты центра): DS00 (-6744,-3373) DS01 (-4394,-4183) DS02 (-3069,-6504)
#   DS03 (-1322,-6999) DS04 (1726,-2757) DS0B (-18,-2968) DS0C (1115,-3041) DS0D (2358,-3484)
#   DS0E (-2147,3335) DS0F (-2618,3460) DS0G (1373,1878) DS0H (-1009,2776) DS0I (-308,1062) DS0J (-1374,1155)
#   DS0K (3567,-1549) DS0L (-3028,3465) DS0M (1284,5786) DS0N (1404,4018) DS0O (2096,5794) DS0P (3401,2821)
#   DS0Q (6281,773) DS0R (6405,1809) DS0T (-1156,3520) DS0U (2340,-1854) DS0V (3789,1030)
cd "$(dirname "$0")"
case "${2:-all}" in
  all)       T='DS*' ;;
  radiant)   T=DS00,DS01,DS02,DS03,DS04,DS05,DS06,DS07,DS08,DS09,DS0A,DS0B,DS0C,DS0D,DS0J,DS0S,DS0Z,DS10,DS11,DS12 ;;
  dire)      T=DS0E,DS0F,DS0G,DS0H,DS0I,DS0K,DS0L,DS0M,DS0N,DS0O,DS0P,DS0Q,DS0R,DS0T,DS0U,DS0V,DS0W,DS0X,DS0Y ;;
  rad-wall)  T=DS00,DS01,DS02,DS03,DS04,DS0B,DS0C,DS0D ;;
  rad-deco)  T=DS05,DS06,DS07,DS08,DS09,DS0A ;;
  dire-wall) T=DS0E,DS0F,DS0G,DS0H,DS0I,DS0J,DS0K,DS0L,DS0M,DS0N,DS0O,DS0P,DS0Q,DS0R,DS0T,DS0U,DS0V ;;
  dire-deco) T=DS0W,DS0X,DS0Y ;;
  river)     T=DS0S,DS0Z,DS10,DS11,DS12 ;;
  *)         T=$2 ;;
esac
if [ "$T" = 'DS*' ]; then python3 map_fix.py doodads-z --types 'DS*' --offset ${1:-0} --apply; python3 map_fix.py piece-lift --offset ${1:-0} --apply
else python3 map_fix.py doodads-z --types $T --offset ${1:-0} --apply; python3 map_fix.py piece-lift --offset ${1:-0} --types $T --apply; fi
