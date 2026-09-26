# Hero Workshop: передача для локальной работы

Цель документа: новая сессия (локальная, с доступом к папке игры и запуску Warcraft III
1.31.1 на macOS) продолжает работу без восстановления контекста из чата. Обновлять на
каждом шаге.

## Окружение

* Игра: `Warcraft III/` (macOS, 1.31.1). Карта: `Maps/Downloads/Dota_Radiant_Terrain_Fix_v4.w3x`
  (DotA 6.85ne14). Эталон: `Dota Mod Project/Sources/Packs/DOTA 2 mod/DOTA-HQv5_RePack.part01/Maps/Download/DotA v6.77b.w3x`
  (DotA 6.77b с HQ-модом для 1.26a).
* Репозиторий: `Dota Mod Project/Tools/HeroWorkshop`, ветка `claude/optimistic-gauss-alg516`.
  Запуск из этой папки: `python3 map_fix.py <fix> [--apply]`, `python3 workshop.py ...`, `zsh *.sh`.
* Файлы мода рядом с игрой: `WC3DotaHQTest/A/...`, `WC3Dota2Test/...`, `WC3WardotaTest/...`.
  **Loose-файлы на диске имеют приоритет над файлами в карте.** Модель из `WC3WardotaTest\...`
  чинится правкой файла на диске (`model-events --into root`, оригинал сохраняется как `.hw_orig`).
* Игра **игнорирует высоту z размещения декораций**: `doodads-z` меняет только число в карте.
  Реально двигают геометрию: `model-lift` (части сборки), `model-shift` (модель целиком).
* Состояние: `state/<карта>/state.json` (не в git): иконки, масштабы, `doodads_added`,
  `custom_doodads_added`, `removed_placements`, `model_lift`, `model_shift`.
* Дамп карты без моделей: `python3 map_fix.py dump` -> `.work/<карта>/dump.zip`.
* Библиотека иконок: `Dota Mod Project/Library/icons/` (`library_build.py`); пользовательские
  иконки: `Library/icons/custom/<kind>/<id>/*.png` (`workshop.py add-icon КЛЮЧ файл.png`,
  в UI пункт контекстного меню ячейки "Добавить PNG в библиотеку"), показываются первыми.

## Сделано и проверено в игре

* Иконки героев/способностей/предметов (Hero Workshop, SwiftUI + workshop.py); инвентарь по
  одной карточке на предмет, состояния (Power Treads, Armlet, Dagon) отдельно.
* Масштабы моделей, сохранение между правками, P3-таблица.
* Модели лавок (`shops --apply`): боковая Merchant, потайная = ShopKeeper (видимый торговец).
* Кулдауны над панелью команд и над инвентарём (`cooldown-numbers --font 0.022 --apply`);
  Инвокер припаркован (вызванные заклинания исключены).
* Окраска юнитов снята (`untint --apply`); Войд после Time Walk (`script-tints --apply`).
* Магазин-окно (`shop_jass.py`, `shop-ui --top 0.55 --bottom 0.15 --apply`, `-shop` в чате,
  кнопка SHOP над панелью команд): только лавки своей команды, 3 колонки, покупка через
  штатную продажу лавки; рецепты из подсказок лавок (Requires), раскрываются только записи
  с Recipe (Ring of Basilius покупается целиком). Сборка Vladmir's Offering / Battle Fury /
  Armlet в игре **ещё не подтверждена**.
* Уплотнение карты `compact --apply`. Перенос декораций 6.77b (`doodads`, `custom-doodads`,
  `remove`, `overlaps`); лишние фонари убраны; стена Рошана убрана.
* Сборка `AshenRock7` (стены и лестницы обеих баз в одной модели): части поднимаются внутри
  модели (`zsh stairs.sh N <группа|DSxx>`, абсолютные значения, `all` затирает подбор).
  Проверенное состояние: части 3,4,11,12,13,20,30 на 200 (нижние лестницы Radiant стоят
  правильно), остальные 0: `zsh stairs.sh 0 all` затем
  `zsh stairs.sh 200 DS03,DS04,DS0B,DS0C,DS0D,DS0K,DS0U`.

## Открытые проблемы (по приоритету)

1. **Стена вокруг фонтана Radiant утоплена.** По геометрии сборки AshenRock7 у фонтана нет ни
   одной её части; там стоят `AOnt` (2), `CPct` (1), `D009`, `AObd`, `NOfp` (probe --at=-7168,-7168,900).
   Их HQ-модели из `Ashenvale/Props`. Пробовать `zsh props.sh 150 Ashenvale/Props` (сдвиг
   моделей целиком), затем сузить до одной модели (`zsh props.sh 150 AshenObilisk` и т.п.),
   остальные вернуть `zsh props.sh 0 Ashenvale/Props`. Не проверено в игре.
2. **Лишние лестницы у ямы Рошана** (перенесены из 6.77b, там был другой Рошан): это
   размещения `ARrk` вариаций 0-5,8 у (4208,-2288) (probe --at=4208,-2288,1500). Убрать:
   `python3 map_fix.py remove --types ARrk --near=4208,-2288,1200 --apply` (проверить список
   без --apply, чтобы не задеть родные камни).
3. **Нумерация частей сборки.** Пересчёт "часть -> место" ненадёжен (все три варианта поворота
   дают расхождения); метки (`labels.sh`) появляются, но на пустых местах. Надёжный способ:
   `zsh parts_probe.sh DSxx ...` (одна часть на 800, перезапуск матча, Enter). Известно:
   DS01/DS02 = плиты у выхода из базы Radiant в верхнюю сторону.
4. **Звук дальней атаки (Снайпер `Usyl`, Дроу `Nbrn`)**, припарковано. Причина: в моделях
   Wardota/Dota2 нет звуковых событий. Снайпер: `model-events --path 'WC3WardotaTest\Units\Human\Rifleman\Rifleman.mdx' --events 'SNDxKRIF@370' --into root --apply`
   (результат не подтверждён). Дроу: у донора BansheeRanger звуковых событий атаки нет,
   звук шёл через данные оружия; проверять `weapsd1` в UnitWeapons.slk. Коды -> звуки:
   `Build/DotaHQ/Inputs/NativeSoundInfo/animlookups.slk`.
5. **Потайные лавки**, припарковано: оставлены с моделью торговца. Идея: юнит = невидимый
   куст (HQ ShopKeeper.mdx), шатёр отдельной декорацией со своей текстурой для Radiant/Dire;
   модели шатра в HQ-папке нет, искать в `Dota Mod Project/Sources/Packs/` по `ShopKeeper`/`secretshop`.
6. **Магазин, хвосты**: панель правее 0.8 обрезается (родитель GAME_UI; `--parent world` даёт
   полную ширину, но кнопки там не проверены); кнопка SHOP высоковата; подобрать `--top/--bottom`.
   Подтвердить сборку составных предметов.
7. **Деревья Radiant**: типы те же, что в 6.77b; команда `trees` (вложить HQ `Doodads/Terrain/AshenTree/*`
   и `ReplaceableTextures/AshenvaleTree/*` в карту) не написана. См. `docs/AUDIT_ranged_and_trees.md`.
8. Столбы с цепями у фонтана Dire родные, не трогать.

## Команды

```zsh
python3 map_fix.py list                      # все исправления
python3 map_fix.py probe --at=X,Y,R          # декорации вокруг точки здесь и в 6.77b (с номерами)
zsh fix_scene.sh                             # вся сцена разом, повторяемо
zsh stairs.sh N [all|radiant|dire|rad-wall|...|DS03]
zsh props.sh N [Ashenvale/Props|имя модели]  # HQ-пропсы целиком
zsh walls.sh N [radiant|dire|тип]            # только число z в карте (игра игнорирует)
zsh parts_probe.sh DS02 DS03                 # опознание частей сборки
zsh labels.sh [off]
python3 workshop.py add-icon item:I0B4 icon.png
```
