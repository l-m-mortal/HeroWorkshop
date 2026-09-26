#!/bin/zsh
# Опознание частей сборки AshenRock7: поднимает ОДНУ часть на 800 (остальные на землю),
# ждёт Enter, следующая. Запускайте, и на каждом шаге смотрите в игре (новый запуск матча), что улетело вверх.
#   zsh parts_probe.sh            # все части по очереди
#   zsh parts_probe.sh DS00 DS0K  # только указанные
cd "$(dirname "$0")"
M='Doodads\Ashenvale\Rocks\AshenRock\AshenRock7.mdx'
if [ $# -gt 0 ]; then LIST=("$@"); else LIST=(DS00 DS01 DS02 DS03 DS04 DS0B DS0C DS0D DS0E DS0F DS0G DS0H DS0I DS0J DS0K DS0L DS0M DS0N DS0O DS0P DS0Q DS0R DS0S DS0T DS0U DS0V DS0Z DS10 DS11 DS12); fi
for P in $LIST; do
  python3 map_fix.py part-probe --path "$M" --types ARrk:7 --parts $P --offset 800 --apply >/dev/null && echo "=== Поднята часть $P. Запустите карту, посмотрите, что в воздухе, потом Enter."
  read
done
python3 map_fix.py model-lift --path "$M" --types ARrk:7 --parts all --offset 0 --apply >/dev/null && echo "Все части на земле."
