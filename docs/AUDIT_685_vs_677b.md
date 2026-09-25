# Аудит карт: 6.85 (рабочая) vs 6.77b (эталон)

- 6.85: `6.85`, war3map.w3d формат = `with_level`, war3map.w3b формат = `without_level`
- 6.77b: `6.77b`, war3map.w3d формат = `with_level`, war3map.w3b формат = `without_level`

## 1. Дудады и разрушаемые объекты

| карта | версия war3map.doo | плейсментов всего | типов дудадов (custom) | типов destructable (custom) |
|---|---:|---:|---:|---:|
| 6.85 | 8 | 5149 | 5 | 11 |
| 6.77b | 7 | 5319 | 4 | 8 |

### Куда резолвятся типы, размещённые на карте (по типам, не по числу плейсментов)

| карта | map | disk | standard | standard(base-model) | missing |
|---|---:|---:|---:|---:|---:|
| 6.85 | 1 | 0 | 1 | 62 | 0 |
| 6.77b | 1 | 0 | 3 | 66 | 0 |

### Импортированные модели дудадов/destructables в 6.77b, отсутствующие в 6.85 (кандидаты на перенос)

Не найдено: ни один тип с импортированной (не-стандартной) моделью, используемый в 6.77b, не остался без соответствия в 6.85 (по путям моделей). Судя по данным, кастомных (war3mapImported) моделей дудадов/destructables у лестниц и заборов в этой версии 6.77b просто нет — они размещены стандартными (не кастомизированными) type id из движка.

### Type id, размещённые в террейне 6.77b, но не встречающиеся вообще ни разу в 6.85

Не про "модель отсутствует", а про "такого объекта вообще нет на карте 6.85" (даже если модель стандартная и всегда доступна). Может быть полезно для Radiant Terrain Fix.

| type id | категория | модель (если задана) | плейсментов в 6.77b |
|---|---|---|---:|
| NOal | standard(unmodified) | `(стандартная, без override)` | 6 |
| VOfs | standard(unmodified) | `(стандартная, без override)` | 6 |
| D001 | doodad | `buildings\other\BookOfSummoning\BookOfSummoning.mdl` | 4 |
| COhs | standard(unmodified) | `(стандартная, без override)` | 3 |
| OOsk | standard(unmodified) | `(стандартная, без override)` | 3 |
| COob | standard(unmodified) | `(стандартная, без override)` | 2 |
| LOsh | doodad | `(стандартная, без override)` | 2 |
| AOob | doodad | `Doodads\Ashenvale\Props\Obelisk\Obelisk2.mdl` | 2 |
| NOok | doodad | `(стандартная, без override)` | 2 |
| CSbc | standard(unmodified) | `(стандартная, без override)` | 2 |
| ATtc | standard(unmodified) | `(стандартная, без override)` | 1 |
| OOal | doodad | `(стандартная, без override)` | 1 |
| OOob | doodad | `(стандартная, без override)` | 1 |
| AOks | standard(unmodified) | `(стандартная, без override)` | 1 |
| AOsk | standard(unmodified) | `(стандартная, без override)` | 1 |
| LOss | doodad | `(стандартная, без override)` | 1 |

## 2. Модели юнитов

- общих rawcode в units\unitUI.slk: 1849
- только в 6.85: 125, только в 6.77b: 2
- юнитов с MISSING моделью в 6.85 (нет ни в карте, ни на диске, путь war3mapImported): 12

| rawcode | модель 6.85 | модель 6.77b |
|---|---|---|
| e00J | `war3mapImported\dummy` | `war3mapImported\dummy` |
| e033 | `war3mapImported\faerie` | `war3mapImported\faerie` |
| e034 | `war3mapImported\faerie` | `war3mapImported\faerie` |
| e035 | `war3mapImported\faerie` | `war3mapImported\faerie` |
| e036 | `war3mapImported\faerie` | `war3mapImported\faerie` |
| e037 | `war3mapImported\dummy` | `war3mapImported\dummy` |
| h0AZ | `war3mapImported\LichMissile_4` | `war3mapImported\LichMissile_4` |
| h0CE | `war3mapImported\EnergyField_5` | `war3mapImported\EnergyField_5` |
| h0D2 | `war3mapImported\ice cube` | `war3mapImported\ice cube` |
| h0D6 | `war3mapImported\FlyingCorpse` | `war3mapImported\FlyingCorpse` |
| h0D7 | `war3mapImported\FlyingCorpse` | `war3mapImported\FlyingCorpse` |
| h0DC | `war3mapImported\MageMissile_5` | `war3mapImported\MageMissile_5` |

- юнитов 6.85 с war3mapImported-моделью, не лежащей в самой карте: 0

## 3. Звуки

- unitSound-наборов в 6.85: 266, в 6.77b (эталон "стандартных"): 261
- кастомных unitSound-наборов в 6.85 (эвристика: имени нет среди юнитов 6.77b): 34
- unitSound-набор считается кастомным, если такого имени нет ни у одного юнита в units\unitUI.slk 6.77b (эталон стандартных Warcraft/DotA 6.77 наборов); сам список звуков по этим наборам не проверяется, т.к. UI\SoundInfo\*.slk отсутствует в обеих картах и на диске недоступен по содержимому.

- .wav/.mp3 упомянутых в скрипте+txt 6.85: 88, из них MISSING: 0
- .wav/.mp3 упомянутых в скрипте+txt 6.77b: 159

- UI\SoundInfo\*.slk в картах: [] / []
- UI\SoundInfo\*.slk найдены по имени на диске (содержимое недоступно): ['UI/SoundInfo/AbilitySounds.slk', 'UI/SoundInfo/UnitAckSounds.slk', 'UI/SoundInfo/DialogSounds.slk', 'WC3DotaHQTest/SoundInfo/AbilitySounds.slk', 'WC3DotaHQTest/SoundInfo/UnitAckSounds.slk', 'WC3DotaHQTest/SoundInfo/DialogSounds.slk']

Полные списки: `.work/audit/doodads.json`, `.work/audit/units.json`, `.work/audit/sounds.json`.
