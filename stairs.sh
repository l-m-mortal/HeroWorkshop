#!/bin/zsh
# Стены и лестницы сборки AshenRock7 (одна модель, части DS00..DS12 = геосеты 0..38).
# Высота низа части над землёй под ней, абсолютная; повтор не накапливает. Все значения помнятся.
#   zsh stairs.sh 100 rad-wall     zsh stairs.sh 0 all     zsh stairs.sh 120 DS00,DS01
# Группы: rad-wall (плиты стены Radiant: DS00-DS04, DS0B-DS0D), rad-deco (DS05-DS0A),
#   dire-wall (DS0E-DS0V без DS0S), dire-deco (DS0W-DS0Y), river (DS0S, DS0Z-DS12)
# Положение частей: DS00 (-6744,-3373) DS01 (-4394,-4183) DS02 (-3069,-6504) DS03 (-1322,-6999)
#   DS04 (1726,-2757) DS0B (-18,-2968) DS0C (1115,-3041) DS0D (2358,-3484)
cd "$(dirname "$0")"
case "${2:-all}" in
  all)       P=all ;;
  radiant)   P=DS00,DS01,DS02,DS03,DS04,DS05,DS06,DS07,DS08,DS09,DS0A,DS0B,DS0C,DS0D,DS0J,DS0S,DS0Z,DS10,DS11,DS12 ;;
  dire)      P=DS0E,DS0F,DS0G,DS0H,DS0I,DS0K,DS0L,DS0M,DS0N,DS0O,DS0P,DS0Q,DS0R,DS0T,DS0U,DS0V,DS0W,DS0X,DS0Y ;;
  rad-wall)  P=DS00,DS01,DS02,DS03,DS04,DS0B,DS0C,DS0D ;;
  rad-deco)  P=DS05,DS06,DS07,DS08,DS09,DS0A ;;
  dire-wall) P=DS0E,DS0F,DS0G,DS0H,DS0I,DS0J,DS0K,DS0L,DS0M,DS0N,DS0O,DS0P,DS0Q,DS0R,DS0T,DS0U,DS0V ;;
  dire-deco) P=DS0W,DS0X,DS0Y ;;
  river)     P=DS0S,DS0Z,DS10,DS11,DS12 ;;
  *)         P=$2 ;;
esac
python3 map_fix.py model-lift --path 'Doodads\Ashenvale\Rocks\AshenRock\AshenRock7.mdx' --types ARrk:7 --drop 39,40,41 --parts $P --offset ${1:-0} --apply
