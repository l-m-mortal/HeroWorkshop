# Аудит: беззвучные снайперы и радиантский лес (6.85 vs 6.77b)

Карты: `.../scratchpad/game/Maps/Downloads/Dota_Radiant_Terrain_Fix_v4.w3x` (6.85)
и `.../scratchpad/maps/DotA v6.77b.w3x` (6.77b). Только чтение, карта не менялась.

## A. Sniper / Drow Ranger: нет звука атаки и снаряда

### Корневая причина

В обеих картах `Units\unitUI.slk` (`file`, `unitSound`, `weap1/weap2`) и текстовые
`*UnitFunc.txt` (`Missileart`) у `h04O` (Sniper) и `h055` (Drow Ranger) практически
идентичны — `unitSound` пуст/`_` в обеих версиях, это не регрессия.

Регрессия — в `Units\UnitWeapons.slk`: это НЕ таблица объекта-редактора (не .w3u), а
отдельная SLK-таблица боевых характеристик, экспортируемая World Editor'ом одной
строкой на unitWeapID **= rawcode юнита**. У 6.77b в ней 1851 строка (1602 кастомных),
у 6.85 — только 451 строка (246 кастомных). Строки для `h04O`, `h055` и ещё двух героев
из 6.85 **пропали целиком**:

| код | герой | `weapTp1` в 6.77b | строка в 6.85 |
|---|---|---|---|
| h04O | Sniper (Kardel Sharpeye) | `missile` | **отсутствует** |
| h055 | Drow Ranger (Traxex) | `missile` | **отсутствует** |
| E02G | Phoenix | `missile` | отсутствует (но у Phoenix `missileart/speed/arc/homing` заданы прямо в `NightElfUnitFunc.txt` в 6.85 — визуально может ещё работать) |
| H0DL | Naga Siren (Revenant of the Waves) | `missile` | отсутствует, и `missilespeed/arc/homing` тоже потеряны из txt |

Больше ни один из ~78 героев с `weapTp1`/`weapTp2` = `missile` в 6.77b не потерял
строку в 6.85 (проверено сопоставлением rawcode → rawcode, т.к. rawcode героев не
меняется между версиями). Это точечная порча 4 строк, не общий регресс дальнобойных.

Без строки в `UnitWeapons.slk` клиент 1.31 не знает `weapTp1=missile` для этого
конкретного юнита и откатывается к типу оружия/анимации базового юнита-основы
(`hrif`/Rifleman → `weapTp1=instant`, `BansheeRanger` — аналогично): анимация становится
"мгновенной" (без полёта снаряда) и озвучка атаки берётся не из missile-набора, а из
набора для instant-атаки, которого у этих кастомных героев тоже нет (`unitSound` пуст) →
итог: ни снаряда, ни звука. На 1.26 клиент, видимо, был терпимее к дырам в этой таблице
(либо у более старой сборки карты строки ещё были), на 1.31 — нет.

`Units\UnitWeaponSounds.slk` ни в одной из карт не переопределён (используется
стандартный, из игры) — сами метки типа `MissileNone`, `AxeMediumChop` и т.п. тут ни при
чём: `weap1`/`weap2` (метка звука оружия) у обоих героев пуста в обеих версиях.

`Missileart` (`Abilities\Weapons\WaterElementalMissile\WaterElementalMissile.mdl`) у
обоих героев **не изменился** и присутствует в обеих версиях — сама модель снаряда не
пострадала, пропала лишь связка "этот юнит стреляет снарядом вообще".

### Точный рецепт для `map_fix.py ranged`

Добавить недостающую кастомную запись в `war3map.w3b`… нет, в `war3map.w3u`
(UnitWeapons — производная таблица, редактируется через сам объект юнита, а не
отдельным файлом в карте) полями weapon-блока 1, взяв значения из строки 6.77b:

Для `h04O` и `h055` (значения идентичны в 6.77b):
```
weapTp1   = missile      # 'msl1' / weapon type 1
atkType1  = pierce       # 'atk1'
rangeN1   = 300          # 'rn1' range 1
cool1     = 1.5          # 'wc1' cooldown 1
dice1=2, sides1=5, dmgplus1=39   # 'wd1'/'ws1'/'wdm1' damage
launchZ   = 60           # 'wlz'
impactZ   = 120          # 'wiz' (было именно у этих героев 120, у стандартной Rifleman-строки 60 — держать 120!)
targs1    = ground,structure,air,debris,item,ward   # 'wtg1'
```
и в `*UnitFunc.txt` (поля `Missilespeed`/`Missilearc`, теряются вместе со строкой):
```
Missilespeed = 1300
Missilearc   = 0.15
```
(`Missileart` уже верный, трогать не нужно).

Для `H0DL` (Naga Siren) — те же поля из её строки 6.77b: `atkType1=hero, rangeN1=500,
cool1=1.7, dice1=1, sides1=7, dmgplus1=18, launchZ=100, impactZ=60`, плюс вернуть в txt
`Missilespeed=1000, Missilearc=0.15, MissileHoming=1` (уже есть верный `Missileart`).

Практическая реализация в `map_fix.py`: т.к. `weapTp1` и весь боевой блок в игре
реально читаются из полей объекта юнита (описанных как теговые mod-записи вида
`'wpon'`-подобных полей weapon-блока в `war3map.w3u`), команда `ranged` должна не трогать
SLK/txt внутри `unitUI`, а **дописать недостающие weapon-поля в w3u-запись юнита** —
`parse_obj_file('war3map.w3u')` → `obj_index`, найти запись по `old/new == h04O` и т.п.,
добавить в её `mods` набор `(field, type, value)` из таблицы выше (типы: `weapTp1`
строка→typ=3 через код метки, числа — typ=2 float либо typ=0 int по образцу соседних
полей той же записи), затем `serialize_obj_file` и подмена файла в MPQ. Для `Missilespeed`/
`Missilearc`/`MissileHoming` — это поля-строки в `*UnitFunc.txt`, patch через `Txt.set`.

## B. Радиантский (Sentinel) лес: типы destructable-объектов

### Что реально стоит в лесу

`war3map.doo`, гистограмма размещений (destructable-типы, топ):

| tid | 6.85 | 6.77b | что это |
|---|---|---|---|
| ATtr | 1652 | 2095 | Ashenvale Tree (лето) — основной радиантский лес |
| NTtw | 1828 | 1618 | Northrend Tree (зима) — дайрский лес |
| ZPsh/ZPfw | 423/165 | 444/174 | кусты/скалы region-декор |
| YTpb/YTlb | 117/48 | 0/214 | ещё один тип дерева/декора (перераспределён между версиями) |

`ATtr` и `NTtw` **не кастомизированы по модели** ни в одной из карт: в `war3map.w3b`
(`obj_index` по `bfil`/`bnam` + прямая проверка raw-модов) у `ATtr` в обеих версиях
меняются только `bvcr/bvcg/bvcb=190,190,190` (тон) и `bmas=1.1` (масштаб) — `bfil`,
`btxf`, `btxi`, `bvar` не тронуты, т.е. модель и текстура берутся полностью из
стандартных данных игры в обеих картах одинаково. Разница числа посадок (1652 vs 2095)
— это terrain-fix (перерисовка леса), не смена типа дерева.

Единственная кастомная destructable-запись с "tree" в модели — `B003` (база `LTlt`,
`bfil=Doodads\Terrain\NorthrendTree\NorthrendTree.mdl`, `btxf=ReplaceableTextures\
NorthrendTree\NorthTree`, `btxi=34`) — но у неё **0 размещений** в обеих картах, это
неиспользуемый шаблон, не часть видимого леса.

### Модель и текстуры HQ-леса на диске

Стандартные ID замен текстур деревьев в движке: `31=LordaeronTree, 32=AshenvaleTree,
33=BarrensTree, 34=NorthrendTree, 35=MushroomTree` (видно по `btxi=34` у `B003`/
NorthrendTree). Модель (`AshenTree0.mdx`, MDX v800, 2 sequence, один replaceable-texture
id 32) — общая на семейство, конкретная текстура выбирается только через `btxf` по этому
id, отдельных ashenvale/lordaeron/northrend-моделей с зашитой текстурой нет.

На диске (`FILES_ALL.tsv`) HQ-мод хранит готовый комплект в двух местах:
* `WC3DotaHQTest/A/Doodads/Terrain/AshenTree/AshenTree{0..9}[D|S].mdx` — HD-модели дерева
  (вариации по индексу `variation` в .doo, `D`=мёртвое/`S`=снег).
* `WC3DotaHQTest/A/Doodads/Terrain/LordaeronTree/...`, `.../NorthrendTree/...` — то же
  для дайрского(зимнего) и лордеронского наборов.
* `WC3DotaHQTest/A/ReplaceableTextures/{AshenvaleTree,LordaeronTree,NorthrendTree}/*.blp`
  — сами текстуры (`AshenTree.blp`, `AshenTreeBlight.blp`, `NorthTree.blp`, ...),
  ровно под btxf-путями выше.
* Корневая копия без префикса `WC3DotaHQTest\A\`: `Doodads/Terrain/AshenTree/
  AshenTree0.mdx` и т.д. лежит и прямо в корне игры — то есть при обычном запуске
  (без сборки на диск в это дерево) это уже подхватывается как loose-override
  стандартного игрового пути; в самой карте (.w3x) этих файлов нет ни в 6.85, ни в 6.77b.

### Что использует 6.77b vs 6.85

Обе карты идентично не переопределяют `bfil/btxf/btxi/bvar` у `ATtr`/`NTtw` — обе
полагаются на то, что стандартный путь модели/текстуры дерева подхватит HQ-оверлей на
диске (при его наличии) или ванильный ассет (при отсутствии). Разницы в самих типах
между 6.85 и 6.77b по факту нет — если лес в 6.85 выглядит хуже, дело не в SLK/w3b
карты, а в том, что HQ-оверлей на диске не задействован для конкретного запуска (не
скопирован в стандартные пути, либо игра не сконфигурирована искать `WC3DotaHQTest/A`).

### Рецепт для `map_fix.py trees` (не меняя типы леса, встраивая ассеты в саму карту)

Чтобы результат не зависел от того, стоит ли HQ-мод на диске у игрока, разумно
встроить HD-комплект прямо в MPQ карты по **стандартным** путям (карта имеет приоритет
над базовыми MPQ игры для этих же путей), ничего не меняя в `war3map.w3b`/`.doo`:

1. Скопировать в карту (без префикса `WC3DotaHQTest\A\`):
   - `Doodads\Terrain\AshenTree\AshenTree{0..9}.mdx` (+ `...D.mdx`, `...S.mdx` варианты,
     что реально используются по `variation` в `.doo` для `ATtr`)
   - `Doodads\Terrain\NorthrendTree\NorthrendTree{0..N}.mdx` (для `NTtw`, дайрская сторона)
   - при желании то же для `LordaeronTree` (используется другими destructable-типами
     карты, не входящими строго в "радиантский лес", но общими декорациями региона)
   - `ReplaceableTextures\AshenvaleTree\AshenTree.blp`, `AshenTreeBlight.blp`
   - `ReplaceableTextures\NorthrendTree\NorthTree.blp`, `NorthTreeBlight.blp`
   - `ReplaceableTextures\LordaeronTree\LordaeronSummerTree.blp` (+`Blight`), если решаем
     трогать и лордеронский набор.
2. **Не трогать** `bfil/btxf/btxi/bvar` у `ATtr`/`NTtw`/`LTlt`-и-подобных в `war3map.w3b`
   — они и так пустые (наследуют стандартный путь), а стандартный путь теперь будет
   резолвиться в карту, а не в отсутствующий на диске файл.
3. Проверка перед записью: `mpq.has()` по каждому целевому стандартному пути в обеих
   тестовых картах — сейчас `False` в обеих (не проверялось детально из-за бюджета
   времени; перед реализацией `trees` стоит прогнать `MPQ(map).has(path)` по всем путям
   из списка выше, чтобы не перезаписать то, что уже случайно встроено).

## Ограничения аудита

Времени хватило на выборочную проверку (Sniper/Drow плюс автопоиск по rawcode-схождению
для остальных ~78 "missile"-героев, и на верхние ~10 типов destructable по числу
размещений). Полный перебор всех 208/174 героев по `war3map.w3u` (не только SLK-срез
`UnitWeapons.slk`) и пространственная привязка `.doo`-размещений к стороне карты
(Sentinel/Scourge по координатам) не проводились — при необходимости это отдельный
проход `map_audit.py` с доработкой (не входит в 30-минутный бюджет данной задачи).
