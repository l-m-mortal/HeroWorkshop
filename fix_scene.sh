#!/bin/zsh
# Сцена карты: стены, лестницы, фонари, яма Рошана. Можно запускать повторно.
# Числа высот и угол ямы правятся прямо здесь.
cd "$(dirname "$0")"
set -e
AONT=400      # круговая стена базы Radiant (AOnt): больше = выше
ARRK=0        # прочие камни ARrk (сама лестница теперь в кусках DS)
D000=226      # тёмные стены Dire (D000), точное значение по геометрии модели
DS_RADWALL=100  # плиты стены Radiant (rad-wall) над землёй; остальные части на земле

step() { echo; echo "=== $1"; }

step "1. Вернуть всё, что удалила старая overlaps (если ещё не возвращено)"
python3 map_fix.py remove --undo --apply || true

step "2. Каменные заборы у фонтана Radiant (VOfs/VOfl): убрать"
python3 map_fix.py doodads --undo --types VOfs,VOfl --apply || true

step "3. Лишнее у фонтана по номерам (фонарь в стене, стойка, второй фонарь)"
python3 map_fix.py remove --ids 5254,5244,5253 --apply || true

step "3b. Перенесённые столбы AOnt и колонны CPct: дублируют стену из сборки, убрать"
python3 map_fix.py doodads --undo --types AOnt,CPct --ported --apply || true

step "4. Перенесённые фонари, факелы и мелкие украшения (все типы): убрать, родные 6.85 остаются"
python3 map_fix.py doodads --undo --types AOsr,IOst,LOth,LOsk,NOfl,LOtz,LOic,CPct,JOgr,LOlp,NOtb,NObt,LObz,CPlp,NOfg,NOfp,ZWfs,CPms,APtv,AObd,LOss,LOsh,NOok,NOal,OOal,OOsk,CSbc,AOks,AOsk,ATtc --ported --apply || true

step "5. Лестница и камни 6.77b (ARrk): убрать родные камни ZRrk на тех же местах"
python3 map_fix.py overlaps --pairs ARrk:ZRrk --radius 100 --prefer ported --apply || true

step "6. Высоты (от земли, повторный запуск ничего не накапливает)"
python3 map_fix.py doodads-z --apply || true
python3 map_fix.py doodads-z --types AOnt --offset $AONT --apply || true
python3 map_fix.py doodads-z --types ARrk --offset $ARRK --apply || true
python3 map_fix.py doodads-z --types D000 --offset $D000 --apply || true

step "6b. Сборка AshenRock7: части ставятся на землю внутри одной модели (без нарезки)"
python3 map_fix.py split-model --undo --apply 2>/dev/null || true
zsh stairs.sh 0 all || true
zsh stairs.sh $DS_RADWALL rad-wall || true

step "7. Яма Рошана: скалы OOob убрать совсем"
python3 map_fix.py doodads --undo --types OOob --apply || true

step "Готово. Перезапустите карту в игре."
