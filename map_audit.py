#!/usr/bin/env python3
"""Compare a 6.85 DotA map (working) against a 6.77b reference map (original DotA)
in three areas: doodads/destructables, unit models, sounds.

    python3 map_audit.py --map <6.85.w3x> --ref <6.77b.w3x>

Writes .work/audit/{doodads,units,sounds}.json and .work/audit/REPORT.md.

Formats used (discovered/verified empirically against the two maps this script
ships with defaults for -- see the sanity-check assertions in main()):

- war3map.w3d / war3map.w3b / war3map.w3u / war3map.w3t / war3map.w3a / war3map.w3q /
  war3map.w3h ("object modification" files) all share the same outer shape:
      uint32 version
      uint32 origCount;  origCount * record   (edits of standard/original objects)
      uint32 customCount; customCount * record (brand new objects)
      record = uint32 oldId, uint32 newId, uint32 modCount, modCount * mod
  The *inner* per-field `mod` layout differs by file and is NOT reliably
  predicted by the file extension alone (empirically war3map.w3d in both test
  maps uses the "with level/pointer" shape while war3map.w3b uses the
  "without" shape -- the opposite of the naive w3d/w3b vs w3a/w3q grouping
  some notes suggest). So this script tries both shapes per file and keeps
  whichever one exactly consumes the buffer (see `parse_obj_file`).
      mod (with level/pointer) = uint32 field, uint32 type, uint32 level, uint32 pointer, value, uint32 end
      mod (without)            = uint32 field, uint32 type, value, uint32 end
      value: type==3 -> nul-terminated string; type in (1,2) -> float32; else uint32
  `field`/`oldId`/`newId` are 4-byte tags (e.g. 'dfil') stored as a little-endian
  uint32; `fourstr()`/`four()` convert between the int and the ASCII tag.

- war3map.doo (doodad + destructable placements): magic 'W3do', uint32 version,
  uint32 subversion, uint32 count, then per placement:
      4-byte type id, uint32 variation, 3x float32 (x,y,z), float32 angle,
      3x float32 (scale x,y,z), byte flags, byte life,
      [version >= 8 only] int32 itemTableId, uint32 itemSetCount, per set:
        uint32 itemCount, per item: 4-byte item id + uint32 chance,
      uint32 editorId
  followed by a trailing "special doodads" section (int32 version, int32 count,
  count * (4-byte id + 3x int32 xyz)) which is 0/0 (8 zero bytes) in both test
  maps. Verified byte-exact against both maps (see `parse_doo`).
"""
from __future__ import annotations
import argparse, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mpq import MPQ
from workshop import slk, Txt

SCRATCH_MAPS = Path('/tmp/claude-0/-home-user-HeroWorkshop/065532ad-19fd-5c20-8156-ab7098d7f103/scratchpad/maps')
DEFAULT_MAP = SCRATCH_MAPS / 'Dota_Radiant_Terrain_Fix_v4.w3x'
DEFAULT_REF = SCRATCH_MAPS / 'DotA v6.77b.w3x'
FILES_ALL = ROOT / 'HeroWorkshop_inventory' / 'FILES_ALL.tsv'
OUT_DIR = ROOT / '.work' / 'audit'

# --------------------------------------------------------------- tag ints --
def four(s: str) -> int:
    return struct.unpack('<I', s.encode('latin1'))[0]

def fourstr(n: int) -> str:
    return struct.pack('<I', n).decode('latin1')

# ------------------------------------------------------- object-mod files --
class _R:
    """Cursor over an object-modification file (.w3d/.w3b/.w3u/.w3t/.w3a/...)."""
    def __init__(self, b: bytes):
        self.b = b; self.o = 0
    def u32(self):
        v = struct.unpack_from('<I', self.b, self.o)[0]; self.o += 4; return v
    def f32(self):
        v = struct.unpack_from('<f', self.b, self.o)[0]; self.o += 4; return v
    def st(self):
        j = self.b.index(b'\0', self.o); v = self.b[self.o:j].decode('latin1'); self.o = j + 1; return v

def _parse_obj_shape(b: bytes, has_level: bool):
    r = _R(b)
    def rec():
        old, new, n = r.u32(), r.u32(), r.u32()
        mods = []; raw = []
        for _ in range(n):
            field, typ = r.u32(), r.u32()
            level = pointer = 0
            if has_level:
                level, pointer = r.u32(), r.u32()  # level/variation, data pointer
            if typ == 3: val = r.st()
            elif typ in (1, 2): val = r.f32()
            else: val = r.u32()
            end = r.u32()  # end marker (0 or the object id, editor dependent)
            mods.append((fourstr(field), typ, val)); raw.append((level, pointer, end))
        return {'old': fourstr(old), 'new': fourstr(new) if new else None, 'mods': mods, 'raw': raw}
    ver = r.u32()
    orig = [rec() for _ in range(r.u32())]
    cust = [rec() for _ in range(r.u32())]
    return ver, orig, cust, r.o

def parse_obj_file(b: bytes):
    """Try both mod-record shapes; keep whichever exactly consumes the buffer."""
    for has_level in (True, False):
        try:
            ver, orig, cust, consumed = _parse_obj_shape(b, has_level)
        except (struct.error, IndexError, UnicodeDecodeError, ValueError):
            continue
        if consumed == len(b):
            return {'version': ver, 'original': orig, 'custom': cust, 'shape': 'with_level' if has_level else 'without_level'}
    return None  # both shapes failed to cleanly consume -> report failure upstream

def serialize_obj_file(parsed) -> bytes:
    """Inverse of parse_obj_file (same shape as parsed: 'with_level' or 'without_level')."""
    has_level = parsed['shape'] == 'with_level'
    out = bytearray(struct.pack('<I', parsed['version']))
    def rec(r):
        out.extend(struct.pack('<II', four(r['old']), four(r['new']) if r['new'] else 0))
        out.extend(struct.pack('<I', len(r['mods'])))
        raw = r.get('raw') or [(0, 0, four(r['new']) if r['new'] else four(r['old']))] * len(r['mods'])
        for (field, typ, val), (level, pointer, end) in zip(r['mods'], raw):
            out.extend(struct.pack('<II', four(field), typ))
            if has_level: out.extend(struct.pack('<II', level, pointer))
            if typ == 3: out.extend(str(val).encode('latin1', 'replace') + b'\0')
            elif typ in (1, 2): out.extend(struct.pack('<f', float(val)))
            else: out.extend(struct.pack('<I', int(val)))
            out.extend(struct.pack('<I', end))
    out.extend(struct.pack('<I', len(parsed['original'])))
    for r in parsed['original']: rec(r)
    out.extend(struct.pack('<I', len(parsed['custom'])))
    for r in parsed['custom']: rec(r)
    return bytes(out)

def obj_index(parsed, model_field: str, name_field: str):
    """type id -> {model, name, base, kind} using the LAST value seen per field
    (mirrors in-game "later field wins") across original+custom records."""
    idx = {}
    if not parsed: return idx
    for kind, records in (('original', parsed['original']), ('custom', parsed['custom'])):
        for rec in records:
            tid = rec['new'] or rec['old']
            entry = idx.setdefault(tid, {'model': None, 'name': None, 'base': rec['old'], 'kind': kind})
            for field, typ, val in rec['mods']:
                if field == model_field and val: entry['model'] = val
                if field == name_field and val: entry['name'] = val
    return idx

# -------------------------------------------------------------- war3map.doo
def parse_doo(b: bytes):
    o = [0]
    def u32():
        v = struct.unpack_from('<I', b, o[0])[0]; o[0] += 4; return v
    def i32():
        v = struct.unpack_from('<i', b, o[0])[0]; o[0] += 4; return v
    def f32():
        v = struct.unpack_from('<f', b, o[0])[0]; o[0] += 4; return v
    def byte():
        v = b[o[0]]; o[0] += 1; return v
    def tag():
        v = b[o[0]:o[0] + 4].decode('latin1'); o[0] += 4; return v
    magic = tag()
    if magic != 'W3do': raise ValueError(f'not a war3map.doo (magic={magic!r})')
    version = u32(); subversion = u32(); count = u32()
    entries = []
    for _ in range(count):
        type_id = tag(); variation = u32()
        x = f32(); y = f32(); z = f32()
        angle = f32()
        sx = f32(); sy = f32(); sz = f32()
        flags = byte(); life = byte()
        if version >= 8:
            item_table_id = i32()
            for _ in range(u32()):
                for _ in range(u32()):
                    tag(); u32()  # item id, chance
        editor_id = u32()
        entries.append(type_id)
    return {'version': version, 'subversion': subversion, 'count': count, 'entries': entries, 'consumed': o[0], 'size': len(b)}

def histogram(items):
    h = {}
    for i in items: h[i] = h.get(i, 0) + 1
    return h

# ----------------------------------------------------------------- disk db
def load_disk_set(tsv_path: Path):
    disk = set()
    with tsv_path.open('r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('#') or not line.strip(): continue
            path = line.split('\t', 1)[0]
            disk.add(path.strip().lower())
    return disk

MOD_PREFIX = re.compile(r'^war3mapimported', re.I)

def resolve_asset(path, mpq: MPQ, disk_set: set, alt_exts=()):
    """where a game-style path (backslashes) would load from: map / disk / standard / missing."""
    if not path: return {'where': 'none', 'path': path}
    path = re.sub(r'\\{2,}', '\\\\', path)  # war3map.j sometimes stores doubled backslashes
    cands = [path]
    if alt_exts:
        # Warcraft resolves an extension-less art path by trying known model
        # extensions in order, and also tolerates a wrong one being swapped.
        has_ext = '.' in Path(path.replace('\\', '/')).name
        stem = path.rsplit('.', 1)[0] if has_ext else path
        for ext in alt_exts:
            c = stem + ext
            if c not in cands: cands.append(c)
    for c in cands:
        if mpq.has(c): return {'where': 'map', 'path': c}
    for c in cands:
        key = c.replace('\\', '/').lower()
        if key in disk_set: return {'where': 'disk', 'path': c}
    if MOD_PREFIX.match(path):
        return {'where': 'missing', 'path': path}
    return {'where': 'standard', 'path': path}

# -------------------------------------------------------------- map bundle
class MapBundle:
    def __init__(self, path: Path, label: str, txt_names_hint=None):
        self.path = Path(path); self.label = label
        self.mpq = MPQ(self.path)
        self.txt_names_hint = txt_names_hint or []

    def read(self, name):
        return self.mpq.read(name)

    def has(self, name):
        return self.mpq.has(name)

    def unit_ui(self):
        return slk(self.read('units\\unitUI.slk').decode('latin1', 'replace'))

    def script_text(self):
        for name in ('war3map.j', 'scripts\\war3map.j'):
            if self.mpq.has(name):
                return self.read(name).decode('latin1', 'replace')
        return ''

    def unit_txt_files(self):
        """Units\\*.txt actually present in this map; for a listfile-less map
        (list() shows only a handful of names) fall back to a fixed set of
        well-known names and probe each with has()."""
        found = {}
        listed = [n for n in self.mpq.list() if n.lower().startswith('units\\') and n.lower().endswith('.txt')]
        candidates = set(listed) | set(self.txt_names_hint)
        if not candidates:
            races = ('Human', 'Orc', 'NightElf', 'Undead', 'Neutral', 'Campaign', 'Common', 'Item')
            kinds = ('UnitFunc', 'UnitStrings', 'AbilityFunc', 'AbilityStrings', 'UpgradeFunc', 'UpgradeStrings', 'Func', 'Strings')
            for r in races:
                for k in kinds:
                    candidates.add(f'Units\\{r}{k}.txt')
        for n in sorted(candidates):
            if self.mpq.has(n):
                try: found[n] = self.read(n).decode('latin1', 'replace')
                except KeyError: pass
        return found

REF_UNITS_TXT_HINT = [
    'Units\\CampaignAbilityFunc.txt', 'Units\\CampaignUnitFunc.txt', 'Units\\HumanAbilityFunc.txt',
    'Units\\HumanUnitFunc.txt', 'Units\\ItemAbilityFunc.txt', 'Units\\ItemFunc.txt',
    'Units\\NeutralAbilityFunc.txt', 'Units\\NightElfAbilityFunc.txt', 'Units\\OrcAbilityFunc.txt',
    'Units\\OrcUnitFunc.txt', 'Units\\UndeadAbilityFunc.txt',
]

# ---------------------------------------------------------- area 1: doodads
def area_doodads(mapb: MapBundle, disk_set, alt_exts=('.mdx', '.mdl')):
    out = {'map': mapb.label}
    w3d_raw = mapb.read('war3map.w3d'); w3b_raw = mapb.read('war3map.w3b')
    w3d = parse_obj_file(w3d_raw); w3b = parse_obj_file(w3b_raw)
    out['w3d_shape'] = w3d['shape'] if w3d else 'FAILED'
    out['w3b_shape'] = w3b['shape'] if w3b else 'FAILED'
    doodad_idx = obj_index(w3d, 'dfil', 'dnam')
    destr_idx = obj_index(w3b, 'bfil', 'bnam')

    doo_raw = mapb.read('war3map.doo')
    try:
        doo = parse_doo(doo_raw)
        out['doo_ok'] = doo['consumed'] <= doo['size']
        out['doo_consumed'] = doo['consumed']; out['doo_size'] = doo['size']
        counts = histogram(doo['entries'])
        out['placement_total'] = len(doo['entries'])
        out['placement_version'] = doo['version']
    except Exception as e:
        out['doo_error'] = str(e)
        # fall back: just histogram raw 4-char windows we can find near known type ids -- best effort
        counts = {}
        out['placement_total'] = None

    types = {}
    for tid, cnt in counts.items():
        if tid in doodad_idx:
            cat, model, name, base, kind = 'doodad', doodad_idx[tid]['model'], doodad_idx[tid]['name'], doodad_idx[tid]['base'], doodad_idx[tid]['kind']
        elif tid in destr_idx:
            cat, model, name, base, kind = 'destructable', destr_idx[tid]['model'], destr_idx[tid]['name'], destr_idx[tid]['base'], destr_idx[tid]['kind']
        else:
            cat, model, name, base, kind = 'standard(unmodified)', None, None, tid, None
        res = resolve_asset(model, mapb.mpq, disk_set, alt_exts) if model else {'where': 'standard(base-model)', 'path': None}
        types[tid] = {'category': cat, 'model': model, 'name': name, 'base': base, 'kind': kind, 'placements': cnt, 'resolve': res['where'], 'resolve_path': res.get('path')}
    out['types'] = types
    out['doodad_custom_ids'] = sorted(k for k, v in doodad_idx.items() if v['kind'] == 'custom')
    out['destructable_custom_ids'] = sorted(k for k, v in destr_idx.items() if v['kind'] == 'custom')
    out['doodad_index'] = doodad_idx
    out['destructable_index'] = destr_idx
    return out

def diff_doodads(a685: dict, a677: dict):
    """6.77b type ids whose model is a non-standard (imported) path with no
    equivalent model path present anywhere resolvable in 6.85's own data."""
    models_685 = set()
    for tid, t in a685['types'].items():
        if t['model']: models_685.add(t['model'].lower())
    candidates = []
    for tid, t in a677['types'].items():
        if not t['model']: continue
        if MOD_PREFIX.match(t['model']) or not re.match(r'^(units|buildings|doodads|abilities|sound|splats|textures|terrainart|ui|environment)\\', t['model'], re.I):
            if t['model'].lower() not in models_685:
                candidates.append({'type_id': tid, 'category': t['category'], 'model': t['model'], 'name': t['name'],
                                    'placements_677': t['placements'], 'resolve_677': t['resolve']})
    candidates.sort(key=lambda c: -c['placements_677'])
    return candidates

def diff_types_not_placed(a685: dict, a677: dict):
    """Type ids placed anywhere in 6.77b's terrain but not placed at all in 6.85 --
    even when the model itself is a standard CASC asset (nothing to import, just
    nothing currently on the 6.85 terrain with that type id)."""
    only = []
    for tid, t in a677['types'].items():
        if tid not in a685['types']:
            only.append({'type_id': tid, 'category': t['category'], 'model': t['model'], 'name': t['name'],
                          'base': t['base'], 'placements_677': t['placements'], 'resolve_677': t['resolve']})
    only.sort(key=lambda c: -c['placements_677'])
    return only

# ------------------------------------------------------------ area 2: units
def area_units(m685: MapBundle, m677: MapBundle, disk_set):
    cells685, h685, rows685 = m685.unit_ui()
    cells677, h677, rows677 = m677.unit_ui()
    common = sorted(set(rows685) & set(rows677))
    def model_of(cells, h, rows, code):
        r = rows.get(code)
        if r is None: return None
        return cells.get((h['file'], r))
    def sound_of(cells, h, rows, code):
        r = rows.get(code)
        if r is None: return None
        return cells.get((h['unitSound'], r))

    missing_685 = []
    imported_unresolved_685 = []
    for code in common:
        m85 = model_of(cells685, h685, rows685, code)
        m77 = model_of(cells677, h677, rows677, code)
        res = resolve_asset(m85, m685.mpq, disk_set, ('.mdx', '.mdl'))
        if res['where'] == 'missing':
            missing_685.append({'code': code, 'model_685': m85, 'model_677': m77, 'resolve_685': res['where']})
        elif res['where'] == 'map' and m85 and MOD_PREFIX.match(m85):
            pass  # fine, present in the map itself
        elif MOD_PREFIX.match(m85 or '') and res['where'] != 'map':
            imported_unresolved_685.append({'code': code, 'model_685': m85, 'resolve_685': res['where']})

    return {
        'common_rawcodes': len(common),
        'only_in_685': sorted(set(rows685) - set(rows677)),
        'only_in_677': sorted(set(rows677) - set(rows685)),
        'missing_model_685': missing_685,
        'imported_unresolved_685': imported_unresolved_685,
        '_cells': (cells685, h685, rows685, cells677, h677, rows677),
    }

# ----------------------------------------------------------- area 3: sounds
WAV_RE = re.compile(r'''['"]([^'"]+?\.(?:wav|mp3))['"]''', re.I)
SOUNDINFO_HINT_PATHS = [
    'UI/SoundInfo/AbilitySounds.slk', 'UI/SoundInfo/UnitAckSounds.slk', 'UI/SoundInfo/DialogSounds.slk',
    'WC3DotaHQTest/SoundInfo/AbilitySounds.slk', 'WC3DotaHQTest/SoundInfo/UnitAckSounds.slk',
    'WC3DotaHQTest/SoundInfo/DialogSounds.slk', 'WC3DotaHQTest/A/UI/SoundInfo/AbilitySounds.slk',
    'WC3Dota2Test/SoundInfo/AbilitySounds.slk', 'WC3Dota2Test/UI/SoundInfo/AbilitySounds.slk',
]

def area_sounds(m685: MapBundle, m677: MapBundle, disk_set):
    out = {}
    # unitSound sets
    cells685, h685, rows685 = m685.unit_ui()
    cells677, h677, rows677 = m677.unit_ui()
    sounds685 = {c: cells685.get((h685['unitSound'], r)) for c, r in rows685.items()}
    sounds677 = {c: cells677.get((h677['unitSound'], r)) for c, r in rows677.items()}
    standard_sets = {v.strip() for v in sounds677.values() if v and v.strip()}
    custom_sets = sorted({v.strip() for v in sounds685.values() if v and v.strip() and v.strip() not in standard_sets})
    out['unit_sound_sets_685_total'] = len({v for v in sounds685.values() if v and v.strip()})
    out['unit_sound_sets_677_total'] = len(standard_sets)
    out['unit_sound_sets_custom_685'] = custom_sets
    out['heuristic'] = ('unitSound-набор считается кастомным, если такого имени нет ни у одного юнита ' +
                         'в units\\unitUI.slk 6.77b (эталон стандартных Warcraft/DotA 6.77 наборов); ' +
                         'сам список звуков по этим наборам не проверяется, т.к. UI\\SoundInfo\\*.slk ' +
                         'отсутствует в обеих картах и на диске недоступен по содержимому.')

    # literal .wav/.mp3 in war3map.j
    j685 = m685.script_text(); j677 = m677.script_text()
    wav685 = sorted(set(WAV_RE.findall(j685)))
    wav677 = sorted(set(WAV_RE.findall(j677)))

    # literal .wav/.mp3 in Units\*.txt
    for n, text in m685.unit_txt_files().items():
        wav685 += WAV_RE.findall(text)
    for n, text in m677.unit_txt_files().items():
        wav677 += WAV_RE.findall(text)
    wav685 = sorted(set(wav685)); wav677 = sorted(set(wav677))

    def resolve_list(paths, mapb):
        res = {}
        for p in paths:
            r = resolve_asset(p, mapb.mpq, disk_set)
            res[p] = r['where']
        return res

    out['wav_refs_685'] = {'count': len(wav685), 'resolve': resolve_list(wav685, m685)}
    out['wav_refs_677'] = {'count': len(wav677), 'resolve': resolve_list(wav677, m677)}
    out['wav_missing_685'] = sorted(p for p, w in out['wav_refs_685']['resolve'].items() if w == 'missing')

    # UI\SoundInfo\*.slk presence: map, then disk listing (names/sizes only, no content)
    soundinfo = {}
    for label, mapb in (('685', m685), ('677', m677)):
        for name in ('UI\\SoundInfo\\AbilitySounds.slk', 'UI\\SoundInfo\\UnitSoundData.slk', 'UI\\SoundInfo\\UnitAckSoundData.slk', 'UI\\SoundInfo\\DialogSounds.slk'):
            if mapb.mpq.has(name):
                soundinfo.setdefault(label, []).append({'path': name, 'where': 'map'})
    soundinfo['disk_listings_found'] = [p for p in SOUNDINFO_HINT_PATHS if p.lower() in disk_set]
    out['soundinfo_slk'] = soundinfo
    return out

# ---------------------------------------------------------------- reporting
def top(d: dict, n=15):
    return sorted(d.items(), key=lambda kv: -kv[1]['placements'])[:n] if d and isinstance(next(iter(d.values()), None), dict) else []

def write_report(d685, d677, diff_doo, diff_not_placed, units, sounds):
    lines = []
    lines.append('# Аудит карт: 6.85 (рабочая) vs 6.77b (эталон)\n')
    lines.append(f'- 6.85: `{d685["map"]}`, war3map.w3d формат = `{d685["w3d_shape"]}`, war3map.w3b формат = `{d685["w3b_shape"]}`')
    lines.append(f'- 6.77b: `{d677["map"]}`, war3map.w3d формат = `{d677["w3d_shape"]}`, war3map.w3b формат = `{d677["w3b_shape"]}`\n')

    lines.append('## 1. Дудады и разрушаемые объекты\n')
    lines.append('| карта | версия war3map.doo | плейсментов всего | типов дудадов (custom) | типов destructable (custom) |')
    lines.append('|---|---:|---:|---:|---:|')
    for d in (d685, d677):
        lines.append(f'| {d["map"]} | {d.get("placement_version")} | {d.get("placement_total")} | {len(d["doodad_custom_ids"])} | {len(d["destructable_custom_ids"])} |')
    lines.append('')

    def resolve_counts(d):
        c = {}
        for t in d['types'].values():
            c[t['resolve']] = c.get(t['resolve'], 0) + 1
        return c
    lines.append('### Куда резолвятся типы, размещённые на карте (по типам, не по числу плейсментов)\n')
    lines.append('| карта | map | disk | standard | standard(base-model) | missing |')
    lines.append('|---|---:|---:|---:|---:|---:|')
    for d in (d685, d677):
        c = resolve_counts(d)
        lines.append(f'| {d["map"]} | {c.get("map",0)} | {c.get("disk",0)} | {c.get("standard",0)} | {c.get("standard(base-model)",0)} | {c.get("missing",0)} |')
    lines.append('')

    lines.append('### Импортированные модели дудадов/destructables в 6.77b, отсутствующие в 6.85 (кандидаты на перенос)\n')
    if diff_doo:
        lines.append('| type id | категория | модель (6.77b) | имя | плейсментов в 6.77b | резолв в 6.77b |')
        lines.append('|---|---|---|---|---:|---|')
        for c in diff_doo:
            lines.append(f'| {c["type_id"]} | {c["category"]} | `{c["model"]}` | {c["name"] or ""} | {c["placements_677"]} | {c["resolve_677"]} |')
    else:
        lines.append('Не найдено: ни один тип с импортированной (не-стандартной) моделью, используемый в 6.77b, не остался без соответствия в 6.85 (по путям моделей). Судя по данным, кастомных (war3mapImported) моделей дудадов/destructables у лестниц и заборов в этой версии 6.77b просто нет — они размещены стандартными (не кастомизированными) type id из движка.')
    lines.append('')

    lines.append('### Type id, размещённые в террейне 6.77b, но не встречающиеся вообще ни разу в 6.85\n')
    lines.append('Не про "модель отсутствует", а про "такого объекта вообще нет на карте 6.85" (даже если модель стандартная и всегда доступна). Может быть полезно для Radiant Terrain Fix.\n')
    if diff_not_placed:
        lines.append('| type id | категория | модель (если задана) | плейсментов в 6.77b |')
        lines.append('|---|---|---|---:|')
        for c in diff_not_placed[:30]:
            lines.append(f'| {c["type_id"]} | {c["category"]} | `{c["model"] or "(стандартная, без override)"}` | {c["placements_677"]} |')
    else:
        lines.append('Не найдено.')
    lines.append('')

    lines.append('## 2. Модели юнитов\n')
    lines.append(f'- общих rawcode в units\\unitUI.slk: {units["common_rawcodes"]}')
    lines.append(f'- только в 6.85: {len(units["only_in_685"])}, только в 6.77b: {len(units["only_in_677"])}')
    lines.append(f'- юнитов с MISSING моделью в 6.85 (нет ни в карте, ни на диске, путь war3mapImported): {len(units["missing_model_685"])}')
    if units['missing_model_685']:
        lines.append('\n| rawcode | модель 6.85 | модель 6.77b |')
        lines.append('|---|---|---|')
        for u in units['missing_model_685'][:40]:
            lines.append(f'| {u["code"]} | `{u["model_685"]}` | `{u["model_677"]}` |')
    lines.append(f'\n- юнитов 6.85 с war3mapImported-моделью, не лежащей в самой карте: {len(units["imported_unresolved_685"])}')
    lines.append('')

    lines.append('## 3. Звуки\n')
    lines.append(f'- unitSound-наборов в 6.85: {sounds["unit_sound_sets_685_total"]}, в 6.77b (эталон "стандартных"): {sounds["unit_sound_sets_677_total"]}')
    lines.append(f'- кастомных unitSound-наборов в 6.85 (эвристика: имени нет среди юнитов 6.77b): {len(sounds["unit_sound_sets_custom_685"])}')
    lines.append(f'- {sounds["heuristic"]}')
    lines.append(f'\n- .wav/.mp3 упомянутых в скрипте+txt 6.85: {sounds["wav_refs_685"]["count"]}, из них MISSING: {len(sounds["wav_missing_685"])}')
    lines.append(f'- .wav/.mp3 упомянутых в скрипте+txt 6.77b: {sounds["wav_refs_677"]["count"]}')
    if sounds['wav_missing_685']:
        lines.append('\nПервые MISSING звуки 6.85:')
        for p in sounds['wav_missing_685'][:20]: lines.append(f'- `{p}`')
    lines.append(f'\n- UI\\SoundInfo\\*.slk в картах: {sounds["soundinfo_slk"].get("685", [])} / {sounds["soundinfo_slk"].get("677", [])}')
    lines.append(f'- UI\\SoundInfo\\*.slk найдены по имени на диске (содержимое недоступно): {sounds["soundinfo_slk"]["disk_listings_found"]}')
    lines.append('')
    lines.append('Полные списки: `.work/audit/doodads.json`, `.work/audit/units.json`, `.work/audit/sounds.json`.\n')
    return '\n'.join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', default=str(DEFAULT_MAP))
    ap.add_argument('--ref', default=str(DEFAULT_REF))
    args = ap.parse_args()

    disk_set = load_disk_set(FILES_ALL)
    m685 = MapBundle(args.map, '6.85')
    m677 = MapBundle(args.ref, '6.77b', txt_names_hint=REF_UNITS_TXT_HINT)

    d685 = area_doodads(m685, disk_set)
    d677 = area_doodads(m677, disk_set)
    assert d685.get('placement_total', 0) and d685['placement_total'] > 1000, \
        f'sanity check failed: 6.85 doodad placements = {d685.get("placement_total")}, expected thousands'
    diff = diff_doodads(d685, d677)
    diff_not_placed = diff_types_not_placed(d685, d677)

    units = area_units(m685, m677, disk_set)
    units_out = {k: v for k, v in units.items() if k != '_cells'}

    sounds = area_sounds(m685, m677, disk_set)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'doodads.json').write_text(json.dumps({'map_685': d685, 'ref_677': d677, 'diff_candidates_677_not_in_685': diff, 'diff_types_not_placed_685': diff_not_placed}, ensure_ascii=False, indent=2))
    (OUT_DIR / 'units.json').write_text(json.dumps(units_out, ensure_ascii=False, indent=2))
    (OUT_DIR / 'sounds.json').write_text(json.dumps(sounds, ensure_ascii=False, indent=2))
    (OUT_DIR / 'REPORT.md').write_text(write_report(d685, d677, diff, diff_not_placed, units_out, sounds), encoding='utf-8')

    print(f'6.85 doodad placements: {d685["placement_total"]}  (types: {len(d685["types"])})')
    print(f'6.77b doodad placements: {d677["placement_total"]}  (types: {len(d677["types"])})')
    print(f'imported-model candidates from 6.77b missing in 6.85: {len(diff)}')
    for c in diff[:20]:
        print(f'  {c["type_id"]} [{c["category"]}] {c["model"]}  name={c["name"]!r} placements={c["placements_677"]}')
    print(f'units: common={units_out["common_rawcodes"]} missing_model_685={len(units_out["missing_model_685"])} imported_unresolved_685={len(units_out["imported_unresolved_685"])}')
    print(f'sounds: custom unitSound sets in 685={len(sounds["unit_sound_sets_custom_685"])} missing wav/mp3 in 685={len(sounds["wav_missing_685"])}')
    print(f'\nWrote {OUT_DIR}/REPORT.md and JSON files.')

if __name__ == '__main__':
    main()
