# HeroWorkshop_inventory

Машиночитаемое описание всей папки Warcraft III на Mac пользователя, собранное для облачной
сессии, у которой нет доступа к диску. Начинать чтение с `LOCATIONS.md`.

| файл | размер | назначение |
|---|---:|---|
| `LOCATIONS.md` | 16 KB | абсолютные пути ко всему, версия игры, Allow Local Files, карта проекта |
| `FILES_ALL.tsv` | 10 MB | **каждый файл** под корнем Warcraft III (71 855 строк): путь, байты, mtime, ext |
| `FILES_ALL.json.gz` | ~1.5 MB | то же в JSON |
| `DIRS.tsv` | 0.9 MB | каждая папка: файлов/байт рекурсивно, файлов напрямую, топ расширений |
| `TREE.md` | 136 KB | обзор верхних папок, полные списки для маленьких, структура до глубины 4 для больших |
| `REFERENCES.md` | 566 KB | резолв `map_external_refs.txt` (1108/1108 найдено) и `map_other_missing_refs.txt` (706/1414) |
| `ICONS_DOTA2.md` | 73 KB | все папки с иконками, образец имени и размеры |
| `HUD.md` | 277 KB | 1 544 HUD-файла с размерами и источником |
| `manifest.json.gz` | см. ниже | вывод `library_scan.py` по всем asset-папкам: sha1, размеры, BLP-формат |
| `manifest.zip`, `manifest/thumbs/` | локально, не в git | PNG-превью (159 MB zip) — при необходимости передать отдельно |

Пересборка (только чтение диска):

```zsh
python3 inventory_build.py --root "<Warcraft III root>" --out HeroWorkshop_inventory \
    --refs map_external_refs.txt --other-refs map_other_missing_refs.txt
```

Правило для скриптов: `ROOT = Path(__file__).resolve().parents[3]` из корня репозитория;
абсолютный путь любого файла = `ROOT / path_from_FILES_ALL`.
