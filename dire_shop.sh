#!/bin/zsh
# Оформление потайной лавки Dire из 6.77b: модель Obstacle2 (навес, факелы, кости) на её месте,
# без кольца скал ямы Рошана (геосеты 7-13) и плоских камней (17-19). Повторяемо.
cd "$(dirname "$0")"
python3 map_fix.py custom-doodads --types AOob --apply || true
python3 map_fix.py model-cut --path 'Doodads\\Outland\\Props\\Obstacle\\Obstacle2.mdx' --source hq --drop 7,8,9,10,11,12,13,17,18,19 --apply
