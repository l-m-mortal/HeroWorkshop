#!/bin/zsh
# Поднять/опустить целиком HQ-модели декораций (высоту размещения игра игнорирует). Значение абсолютное.
#   zsh props.sh 150 Ashenvale/Props      # все HQ-пропсы Ashenvale (обелиски, статуи, жаровни)
#   zsh props.sh 150 AshenObilisk         # одна модель
#   zsh props.sh 0 Ashenvale/Props        # вернуть
cd "$(dirname "$0")"
python3 map_fix.py model-shift --match "${2:-Ashenvale/Props}" --dz ${1:-0} --apply
