#!/bin/zsh
# Скалы ямы Рошана (OOob): абсолютный угол и, при желании, точка.
#   zsh roshan.sh 180            # повернуть так, чтобы угол стал 180°
#   zsh roshan.sh 180 4150,-2050 # и подвинуть в точку
cd "$(dirname "$0")"
ANGLE=${1:-180}; TO=${2:-4110,-2100}
python3 map_fix.py move-doodads --types OOob --to=$TO --angle $ANGLE --apply
