# Hero Workshop

Редактор иконок и масштабов моделей для карты DotA (Warcraft III 1.31, macOS).
Работает напрямую с картой `.w3x` и с папками мода рядом с игрой (`WC3DotaHQTest`
и другие): читает, что применено сейчас, показывает это в панели, похожей на игровой
HUD, и применяет замены одним перетаскиванием.

Репозиторий лежит внутри папки Warcraft III: `Dota Mod Project/Tools/HeroWorkshop`.
Корень игры определяется автоматически (папка, в которой есть `Maps/Downloads`).

## Запуск

Двойной клик по `Open Hero Workshop.command`. При первом запуске создаётся `.venv`,
ставится Pillow и собирается Swift-приложение. Из терминала:

```zsh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 workshop.py doctor
```

Карта выбирается в `workshop.json` (`map`, относительно корня игры). Локальные
переопределения кладите в `workshop.local.json` (см. `workshop.local.example.json`),
он не попадает в Git. То же через `HERO_WORKSHOP_MAP` и `HERO_WORKSHOP_GAME_ROOT`.

## Что показывает приложение

* **Герои**: портрет/иконка героя, масштаб модели, панель команд 4×3, где способности
  стоят на своих местах (`Buttonpos` из карты). Лишние способности выводятся отдельным
  рядом, служебные спрятаны в раскрывающийся список.
* **Связанные юниты**: морф-форма из таблицы `P3`, альтернативная модель, призывы
  (по полям `UnitID` способностей) и добавленные вручную по rawcode. У каждого своя
  иконка, масштаб и панель способностей.
* **Предметы**: сетка всех предметов карты с поиском.
* Подпись под ячейкой говорит, откуда иконка грузится сейчас: «в карте», «на диске»
  (папка мода), «стандарт WC3». Зелёная точка — иконка заменена через Workshop.
  Переключатель «Серые (DISBTN)» показывает версии для неактивных кнопок.

## Замена иконки

Перетащите PNG или BLP на ячейку (двойной клик открывает выбор файла). Файл
приводится к 64×64, кодируется в BLP1 с альфа-каналом, серая версия генерируется
автоматически. Куда пишется результат:

* иконка ссылается на файл мода (`WC3DotaHQTest\...`): файл заменяется на диске,
  старый копируется в `Dota Mod Project/Archives/HeroWorkshop/Trash/<дата>/`;
* иконка стандартная или общая: объекту назначается собственный файл
  `ReplaceableTextures\CommandButtons\BTN_HW_<тип>_<rawcode>.blp` внутри карты,
  а строка `Art=`/`art=` (и `Researchart=`) в txt-файлах карты переписывается.

Правый клик по ячейке: «Вернуть исходную иконку», «Показать файл в Finder».

## Масштаб

Значение абсолютное. Записывается в `unitUI.slk:modelScale` для героя и его
морф-формы и одновременно в число в строке `P3(...)` скрипта карты, поэтому после
смерти и перерождения масштаб не сбрасывается. Введённые значения сохраняются в
`state/<карта>/state.json` и показываются при следующем открытии.

## Состояние и резервные копии

* `state/<карта>/state.json` — что заменено и какие масштабы заданы; исходные PNG в
  `state/<карта>/icons/`, оригиналы заменённых файлов мода в `originals/`. Папку
  `state/` можно коммитить.
* `.work/<карта>/` — кэш превью, не в Git.
* Перед первой записью в карту делается копия в `Archives/HeroWorkshop/Backups/HeroWorkshop`
  (не чаще раза в 30 минут, хранится 10 последних).

## Команды

```zsh
python3 workshop.py doctor
python3 workshop.py state                      # .work/<карта>/state.json + превью
python3 workshop.py set-icon unit:H06S kunkka.png
python3 workshop.py set-icon ability:A136 torrent.png
python3 workshop.py set-icon item:I0B4 scepter.png
python3 workshop.py clear-icon ability:A136
python3 workshop.py set-scale H06S 1.25 [--morph 1.25] [--alt 1.0]
python3 workshop.py add-related H06S n0EE      # призыв, созданный триггером
python3 workshop.py regen-disabled [--apply] [--scope all|map|disk]  # перегенерировать disabled-иконки
python3 workshop.py candidates ability:A136    # варианты иконок из библиотеки (JSON)
```

Ключи: `unit:<rawcode>`, `ability:<rawcode>`, `item:<rawcode>`.

## Исправления карты (`map_fix.py`)

Все команды сначала показывают план; записывают только с `--apply`.

```zsh
python3 map_fix.py list
python3 map_fix.py shops --apply                     # модели боковой/секретной лавки
python3 map_fix.py doodads [--ref карта] [--types A,B] [--near=X,Y,R] [--undo] --apply
python3 map_fix.py hq-doodads [--match Fence] [--textures] [--models] --apply
python3 map_fix.py probe [--at=-7168,-7168,2600]     # декорации вокруг точки здесь и в 6.77b
python3 map_fix.py move-doodads --types DH01 --from=2448,-528 --to=4208,-2288 [--rotate 90] --apply  # перенести группу
python3 map_fix.py custom-doodads [--types D001,AOob] [--near=X,Y,R] [--undo] --apply  # пользовательские типы 6.77b под новыми кодами
python3 map_fix.py static-models [--match Fence] [--undo] --apply   # экспериментально: Stand для моделей без анимаций; --undo вернуть из папки HQ
python3 map_fix.py repack-textures [--match Shrub] --apply  # JPEG-BLP текстуры HQ-моделей -> палитровый BLP1
python3 map_fix.py cooldown-numbers [--debug] [--parent gameui|button] [--font 0.016] [--undo] --apply
```

* `probe` сравнивает размещения декораций вокруг точки (по умолчанию фонтан Radiant)
  в текущей карте и в 6.77b, показывает модели пользовательских типов.
* `doodads --near=X,Y,R` переносит из 6.77b только размещения в радиусе R, пропуская
  уже стоящие на том же месте. Знак `=` обязателен из-за минусов в координатах.
* `custom-doodads` переносит пользовательские типы декораций 6.77b (D0xx/B0xx и
  стандартные типы с заменённой моделью) под новыми кодами `DH00..`, `BH00..`, вместе с
  размещениями и моделями (HQ-копия из `WC3DotaHQTest\A` или файл из 6.77b).
* `hq-doodads --models` проверяет каждую HQ-модель (версия MDX, число геосетов) и
  формат каждой текстуры так, как их найдёт игра: BLP2 или отсутствующая текстура
  означает белую модель.
* `cooldown-numbers --debug` показывает на всех кнопках их номера 0..11 и строку
  состояния вверху экрана (выбранный юнит, число найденных способностей, кулдауны).

## Модули

* `mpq.py` — чтение и запись MPQ на чистом Python (без внешних утилит).
* `blp.py` — декодирование BLP1 (палитра и JPEG), кодирование BLP1 с альфой, серые иконки.
* `workshop.py` — ядро: состояние карты, применение иконок и масштабов.
* `map_fix.py`, `doo.py`, `cooldown_jass.py`, `map_audit.py` — исправления карты:
  лавки, декорации из 6.77b, HQ-модели, счётчики кулдаунов.
* `library_scan.py`, `inventory_build.py`, `HeroWorkshop_inventory/` — инвентарь
  папки игры для работы без доступа к диску.
* `tools/` — старые MPQ-утилиты, больше не используются.
