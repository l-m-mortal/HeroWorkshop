# LOCATIONS

Собрано 2026-09-26 локальной сессией Claude Code на Mac. Ничего не изменялось и не удалялось.

## 0. Как читать этот инвентарь

Корень игры (далее `ROOT`):

```
/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III macOS 64bit/Warcraft III
```

Все относительные пути в `FILES_ALL.tsv`, `DIRS.tsv`, `TREE.md`, `REFERENCES.md`, `HUD.md`,
`ICONS_DOTA2.md` отсчитываются от `ROOT` и используют `/`. Абсолютный путь = `ROOT + "/" + path`.
В игре тот же путь пишется через `\` относительно `ROOT` (режим локальных файлов включён, см. п. 2).

Репозиторий HeroWorkshop лежит внутри `ROOT`:

```
ROOT/Dota Mod Project/Tools/HeroWorkshop        (git: https://github.com/l-m-mortal/HeroWorkshop.git)
```

Значит из скрипта в репозитории `ROOT` = `Path(__file__).resolve().parents[3]`
(`HeroWorkshop` → `Tools` → `Dota Mod Project` → `ROOT`). Именно так можно писать скрипты,
которые будут работать локально на Mac над всеми файлами из `FILES_ALL.tsv`.

Файлы инвентаря:

| файл | что внутри |
|---|---|
| `FILES_ALL.tsv` | каждый файл под `ROOT`: путь, размер в байтах, mtime, расширение. 71 855 строк. |
| `FILES_ALL.json` | то же в JSON (`{"root","generated","count","skipped_dirs","files":[{path,size,mtime,ext}]}`) |
| `DIRS.tsv` | каждая папка: файлов рекурсивно, байт рекурсивно, файлов непосредственно, топ расширений |
| `TREE.md` | обзор по верхним папкам: полные списки для папок ≤300 файлов, структура до глубины 4 для больших |
| `REFERENCES.md` | проверка `map_external_refs.txt` и `map_other_missing_refs.txt` |
| `ICONS_DOTA2.md` | папки с иконками, схема имён, размеры |
| `HUD.md` | все HUD-файлы с размерами и набором-источником |
| `manifest.zip` / `manifest/` | результат `library_scan.py`: `manifest.json` + PNG-превью |
| `inventory_build.py` (в корне репо) | скрипт, который сгенерировал всё выше; можно перезапускать |

Из листингов исключены: AppleDouble `._*` (exFAT-мусор macOS, их тысячи, к ассетам не относятся),
`.DS_Store`, содержимое `.git`, `__pycache__`, `.venv`, `.build`.
Симлинк `ROOT/Dota2` не обходился (его цель перечислена по месту, см. п. 3).

## 1. Warcraft III 1.31.1

| что | путь |
|---|---|
| корень установки | `ROOT` |
| исполняемое приложение | `ROOT/x86_64/Warcraft III.app` (CFBundleShortVersionString **1.31.1.12173**) |
| "fixed" лаунчер | `ROOT/x86_64/Warcraft III fixed.app` (тоже 1.31.1.12173) |
| Public Test Launcher (НЕ запускать, обновит до Reforged) | `ROOT/Warcraft III Public Test Launcher.app` |
| CASC-данные игры | `ROOT/Data` (437 файлов, 1.9 ГБ) |
| `.build.info` | `ROOT/.build.info` (enUS OSX Release, дата 2024-04-18) |
| карты | `ROOT/Maps/Downloads/` |
| CustomKeys | `ROOT/CustomKeys.txt`, `ROOT/CustomKeyInfo.txt`, `ROOT/CustomKeysSample.txt` |
| логи игры | `~/Documents/Warcraft III/Logs/War3Log.txt`, `~/Documents/Warcraft III/Errors/` |
| ключи PTR (roc.w3k, user.w3k) | `/Users/Shared/Blizzard/Warcraft III Public Test/`, `~/Library/Application Support/Blizzard/Warcraft III Public Test/` |
| readme установки | `/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III macOS 64bit/Readme.txt` |
| zip-копия всей установки (старая) | `/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III macOS 64bit.zip` |

Карты в `ROOT/Maps/Downloads/` (все четыре файла):

| файл | размер | назначение |
|---|---:|---|
| `D85 06 DotaHQv5.w3x` | 24 138 848 | финальная интегрированная карта, внутреннее имя `Dota HQ V5` |
| `D85 07 AnimationUpdatesTest.w3x` | 24 138 861 | тестовая ветка для анимаций и Hero Workshop |
| `Dota_Radiant_Terrain_Fix_v4.w3x` | 24 197 032 | карта, которую разбирала облачная сессия (mtime 2026-09-25 18:51) |
| `Dota_Radiant_Terrain_Fix_v4.w3x.zip` | 23 719 696 | её zip |

Папки модов рядом с игрой (runtime-слой, на который карта ссылается буквальными путями):

| папка | файлов | размер | содержимое |
|---|---:|---:|---|
| `ROOT/WC3DotaHQTest` | 12 006 | 3.9 ГБ | `A/` (главный изолированный HQ runtime, namespace `WC3DotaHQTest\A\...`), `Mix/` (runtime Selected Mix), `SoundInfo/` |
| `ROOT/WC3Dota2Test` | 2 039 | 994 МБ | `Defaults`, `Fixes`, `GeneratedUI`, `Icons`, `Skins`, `Units`, `UpdateSkins` (модели Selected Mix / Dota Heroes) |
| `ROOT/WC3WardotaTest` | 1 291 | 512 МБ | `Units`, `SoundInfo` (модели Wardota) |

Корневые path-bound overrides (файлы прямо по игровым путям):

| папка | файлов | размер |
|---|---:|---:|
| `ROOT/Abilities` | 5 | 4.1 МБ |
| `ROOT/Buildings` | 22 | 9.3 МБ |
| `ROOT/Doodads` | 69 | 22 МБ |
| `ROOT/Environment` | 1 | <1 МБ |
| `ROOT/Objects` | 2 | 1 МБ |
| `ROOT/ReplaceableTextures` | 1 | <1 МБ |
| `ROOT/SPELLS` | 2 | <1 МБ |
| `ROOT/TerrainArt` | 22 | 14 МБ |
| `ROOT/Textures` | 4 | <1 МБ |
| `ROOT/Ton_ucki` | 12 | 4.3 МБ |
| `ROOT/UI` | только `UI/SoundInfo/*` (визуальный HUD перенесён внутрь карт D85 06/07) |
| `ROOT/Units` | 144 | 58 МБ (включая `Units/Custom/ShopKeeper`) |
| `ROOT/effects`, `ROOT/ssance` | по 1 файлу |
| `ROOT/TideTonucki.blp`, `ROOT/dire_tree007_moss.blp`, `ROOT/dire_tree007c.blp` | loose-файлы в корне |

Полные списки этих небольших папок есть в `TREE.md`.

Ещё одна папка с тем же именем, но это НЕ установка:
`/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III/WC3Dota2Test/CooldownFDF/` (2 файла:
`Cooldown.fdf`, `build_fdf_test.py`) — остаток старого эксперимента с cooldown-оверлеем.

## 2. Allow Local Files и версия

Проверено `defaults read`:

```
$ defaults read com.blizzard.warcraftiii
{ "Allow Local Files" = 1; fullscreenWindowMode = 0; }

$ defaults read "com.blizzard.Warcraft III"
{ "Allow Local Files" = 1; }
```

Файлы: `~/Library/Preferences/com.blizzard.WarcraftIII.plist`,
`~/Library/Preferences/com.blizzard.Warcraft III.plist`,
`~/Library/Preferences/com.blizzard.Warcraft III Public Test.plist`.

**Режим локальных файлов включён** в обоих доменах. Версия игры **1.31.1.12173** (из Info.plist обоих
`.app` в `ROOT/x86_64`).

## 3. Warcraft III 1.26a и Dota HQ V5 для неё

Установка 1.26a на этом Mac **не найдена**. Что есть:

- `~/Applications/CrossOver/Warcraft III Expansion Set/Warcraft III The Frozen Throne.app` — ярлык
  CrossOver; папка bottles `~/Library/Application Support/CrossOver/Bottles/` отсутствует, т.е.
  сама Windows-установка удалена. Версия неизвестна.
- `~/Downloads/[CD] Warcraft III ... (1.26a, 1.27b, 1.29.2) ... .torrent` — только торрент-файл.

Исходники Dota HQ V5 (для 1.26a) есть в виде паков, а не установки:

- `ROOT/Dota Mod Project/Sources/Packs/DOTA 2 mod/DOTA-HQv5_RePack.part01/` (10 файлов, внутри `Maps/`)
- уже распакованный runtime: `ROOT/WC3DotaHQTest/A/`

## 4. Dota Mod Project

`ROOT/Dota Mod Project` — 66 668 файлов, ~60 ГБ (в это число входит `Tools/HeroWorkshop2` 4.7 ГБ и `Build/DotaHQ` с 19 537 файлами).

| папка | файлов | описание |
|---|---:|---|
| `Dota Mod Project/README.md` | | описание структуры проекта |
| `Dota Mod Project/Documentation/HANDOFF_PROMPT_RU.md`, `MapArchive_README.md` | 2 | handoff-контекст и описание карт |
| `Dota Mod Project/Build/DotaHQ/` | 19 537 | сборщик `build_dota_hq_test.py`, `rollback_external_hq.py`, `Inputs/`, `Reports/` (`DOTA_HQ_BUILD_REPORT.json`), `State/` |
| `Dota Mod Project/Sources/Maps/` | 10 | исходные W3X: `DotA v6.85ne14.w3x`, `D85 00 Original i`, `D85 01 DotaHeroesV2`, `D85 02 HeroClashRAR`, `D85 03 Wardota2`, `D85 04 SelectedMix`, `D85 05 Wardota`, `D85 05 WardotaDecor`, `D85 08 CooldownFDFProbe`, `D15 00 Dota15ModelTest` |
| `Dota Mod Project/Sources/Packs/DOTA 2 mod/` | 18 727 | исходные паки, см. ниже |
| `Dota Mod Project/Tools/HeroWorkshop/` | 2 394 | этот репозиторий |
| `Dota Mod Project/Tools/HeroWorkshop2/` | 19 963 | **старая копия** Hero Workshop с распакованными `heroes/` (118 папок `Hero__rawcode`), `items/`, `units/`, `__pycache__`; не git. В текущем репо эти деревья лежат как `heroes.zip`, `items.zip`, `units.zip` |
| `Dota Mod Project/Workspaces/Dota2/Icon Audit/` | 5 330 | библиотека иконок (см. п. 5) |
| `Dota Mod Project/Workspaces/Dota2/{Backups,CooldownFDF,FailedTests}` | 24 | вспомогательное |
| `Dota Mod Project/Workspaces/Wardota/` | 18 | таблицы аудита Wardota |
| `Dota Mod Project/Archives/GlobalOverrides/2026-09-25-ui-moved-into-maps` | | глобальные UI overrides, вынесенные из `ROOT/UI` |
| `Dota Mod Project/Archives/GlobalOverrides/2026-09-25-wrong-secret-shop-assets` | | ошибочные ассеты лавки |
| `Dota Mod Project/Archives/HeroWorkshop/Backups` | 380 | резервные копии карт от Hero Workshop |
| `Dota Mod Project/Archives/MapSnapshots/2026-09-25-secret-shop-ui-scope` | 2 | снимки карт |
| `Dota Mod Project/Archives/DotaHQ/HistoricalMaps` | 3 | исторические карты |

Паки в `Dota Mod Project/Sources/Packs/DOTA 2 mod/`:

| пак | файлов | заметка |
|---|---:|---|
| `Wardota 2 Compilation V2 - Creative's ArT - 2014/` | 13 023 | `Dota2/` (11 137 — на него указывает симлинк `ROOT/Dota2`), `Units/` 1 648, `Doodads/` 214, `TerrainArt/`, `Maps/` |
| `DotA_Heroes_v2.0/` | 1 643 | `Units/` 1 606, `UI/`, `Maps/` |
| `Dota 1.5 - PrO_SoZaIa & ShadowProgr - 2012/` | 1 658 | `ReplaceableTextures/` 1 484 (иконки), `UI/` 72, `Units/`, `Sound/`, `Load/` |
| `Dota 1.5 2/` | 450 | First/Third/Fifth/Sixth Pack, Miscellaneous Models, Units |
| `114 HEROES ICONOS/` | 1 162 | `ReplaceableTextures/` 1 153 (иконки), `PARCHE ICONO/` |
| `Massive Dota 2 Special Effects Rip/` | 352 | ~90 папок эффектов (Laguna Blade, Echo Slam, ...) |
| `AnimeDecor/` | 115 | подпапки с битой кодировкой имён (cp866→utf8) |
| `Dota2HeroesClash_IconsGrouped/` | 72 | иконки по 5 на героя (14 героев) |
| `Dota2HeroesClash_SkinDatabase/` | 73 | `Skins/`, `Previews/` |
| `DOTA-HQv5_RePack.part01/` | 10 | `Maps/` |
| `UPDATE/`, `UPDATE 2/`, `UPDATE 3/` | 70 / 2 / 91 | нетронутые паки для будущего теста на D85 07 |

Симлинк: `ROOT/Dota2` → `ROOT/Dota Mod Project/Sources/Packs/DOTA 2 mod/Wardota 2 Compilation V2 - Creative's ArT - 2014/Dota2`.
В игре путь `Dota2\...` разрешается через него.

## 5. Иконки Dota 2 в PNG

Подробно в `ICONS_DOTA2.md`. Главные места:

| путь | файлов | схема |
|---|---:|---|
| `Dota Mod Project/Workspaces/Dota2/Icon Audit/Heroes/<Hero Name>/<Set>/ReplaceableTextures/CommandButtons/BTN*.{blp,png}` и `CommandButtonsDisabled/DISBTN*.{blp,png}` | 1 920 | Set ∈ {`Dota_1_5`, `114_Heroes_Icons`, ...}; BLP + PNG-превью рядом |
| `Dota Mod Project/Workspaces/Dota2/Icon Audit/Items/<Set>/ReplaceableTextures/{CommandButtons,AutoCastButtons,...}/` | 388 | |
| `Dota Mod Project/Workspaces/Dota2/Icon Audit/Shared_or_Unassigned/` | 2 930 | иконки, не привязанные к герою |
| `Dota Mod Project/Workspaces/Dota2/Icon Audit/CONTACT_SHEETS/` | 88 | контактные листы |
| `Dota Mod Project/Tools/HeroWorkshop/assets/icons/catalog/{current-map,sources}/` | | иконки текущей карты и наборов, BLP + PNG |
| `Dota Mod Project/Sources/Packs/DOTA 2 mod/114 HEROES ICONOS/ReplaceableTextures/` | 1 153 | исходный пак |
| `Dota Mod Project/Sources/Packs/DOTA 2 mod/Dota 1.5 - .../ReplaceableTextures/` | 1 484 | исходный пак |
| `Dota Mod Project/Sources/Packs/DOTA 2 mod/Dota2HeroesClash_IconsGrouped/<Hero>/` | 72 | |
| `ROOT/WC3Dota2Test/Icons/` | | иконки runtime-слоя |

Современных PNG-иконок Dota 2 (из самой Dota 2, `<hero>_<ability>_png` и т.п.) **не найдено** —
все наборы это Warcraft-стилизованные BTN/DISBTN 64×64 из паков 2012–2014.

## 6. HUD

Подробно в `HUD.md`. Кратко:

- `ROOT/UI/` глобально содержит только `UI/SoundInfo/` (таблицы звуков). Визуальный HUD (Console,
  Widgets, Cursor, MiniMap, cooldown FDF) импортирован внутрь `D85 06` и `D85 07`.
- Извлечённые копии HUD: `Dota Mod Project/Tools/HeroWorkshop/assets/icons/catalog/current-map/ui-assets/`
  (Dota HQ V5) и `.../catalog/sources/map-ui/{D85_03_Wardota2,D85_04_SelectedMix,D85_05_WardotaDecor,D85_01_DotaHeroesV2}/`.
- Вынесенные из `ROOT/UI` глобальные overrides: `Dota Mod Project/Archives/GlobalOverrides/2026-09-25-ui-moved-into-maps/`.
- `Cooldown.fdf`: `.../catalog/sources/ui-scripts/Cooldown.fdf`, `Dota Mod Project/Workspaces/Dota2/CooldownFDF/`,
  `/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III/WC3Dota2Test/CooldownFDF/Cooldown.fdf`.
- Исходные HUD паков: `Sources/Packs/DOTA 2 mod/Dota 1.5 - .../UI/` (72), `DotA_Heroes_v2.0/UI/` (3),
  `WC3Dota2Test/GeneratedUI/`, `WC3DotaHQTest/A/UI/`, `WC3DotaHQTest/Mix/UI/`.

## 7. Другие ассеты Warcraft III на диске

Вне `ROOT` папок с `.mdx/.blp/.w3x` не найдено (искалось по `mdfind -name "Warcraft III"`, `/Applications`,
`~/`, `/Volumes`). Всё лежит внутри `ROOT`; единственное исключение — 2 файла CooldownFDF в
`/Volumes/Data/RECOVERY/Games/Warcraft 3/Warcraft III/WC3Dota2Test/`.

## 8. Замечания по репозиторию (для облачной сессии)

- В репо **нет `.gitignore`**, хотя README_RU обещает его. `git ls-files` показывает 5 760 файлов, из них
  5 709 под `HeroWorkshopUI/` — скорее всего закоммичен Swift `.build`. Стоит добавить `.gitignore`
  (`.venv/`, `.work/`, `HeroWorkshopUI/.build/`, `__pycache__/`, `*.w3x`, `workshop.local.json`,
  `HeroWorkshop_inventory/manifest/`) и вычистить `.build` из индекса.
- `workshop.json` указывает на `Maps/Downloads/D85 06 DotaHQv5.w3x`, handoff говорит что Workshop
  перенаправлен на D85 07 — проверить, что именно должно быть целью.
- Облачная карта `Dota_Radiant_Terrain_Fix_v4.w3x` лежит рядом с D85 06/07; в handoff она не упомянута.
