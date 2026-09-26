#!/bin/zsh
# Сцена карты: стены, лестницы, фонари, яма Рошана. Можно запускать повторно.
# Числа высот и угол ямы правятся прямо здесь.
cd "$(dirname "$0")"
set -e
AONT=250      # круговая стена базы Radiant (AOnt): больше = выше
ARRK=250      # лестница Radiant (ARrk)
D000=226      # тёмные стены Dire (D000), точное значение по геометрии модели
ROSHAN_ANGLE=90   # абсолютный угол скал ямы Рошана (OOob), 0..359

step() { echo; echo "=== $1"; }

step "1. Вернуть всё, что удалила старая overlaps (если ещё не возвращено)"
python3 map_fix.py remove --undo --apply || true

step "2. Каменные заборы у фонтана Radiant (VOfs/VOfl): убрать"
python3 map_fix.py doodads --undo --types VOfs,VOfl --apply || true

step "3. Лишнее у фонтана по номерам (фонарь в стене, стойка, второй фонарь)"
python3 map_fix.py remove --ids 5254,5244,5253 --apply || true

step "4. Дубли фонарей: перенесённые AOsr рядом с родными LOfl"
python3 map_fix.py overlaps --pairs AOsr:LOfl --radius 200 --apply || true

step "5. Лестница и камни 6.77b (ARrk): убрать родные камни ZRrk на тех же местах"
python3 map_fix.py overlaps --pairs ARrk:ZRrk --radius 100 --prefer ported --apply || true

step "6. Высоты (от земли, повторный запуск ничего не накапливает)"
python3 map_fix.py doodads-z --apply || true
python3 map_fix.py doodads-z --types AOnt --offset $AONT --apply || true
python3 map_fix.py doodads-z --types ARrk --offset $ARRK --apply || true
python3 map_fix.py doodads-z --types D000 --offset $D000 --apply || true

step "7. Яма Рошана: скалы OOob у нового Рошана, абсолютный угол $ROSHAN_ANGLE"
python3 map_fix.py move-doodads --types OOob --to=4110,-2100 --angle $ROSHAN_ANGLE --apply || true

step "Готово. Перезапустите карту в игре."
