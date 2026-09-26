#!/usr/bin/env python3
"""Hero Workshop core: read the live state of a DotA map (icons, scales),
apply icon and scale changes directly to the map and the mod folders, and
persist what was chosen so later edits never lose earlier ones.

    python3 workshop.py doctor
    python3 workshop.py state                 # -> .work/<map>/state.json + previews
    python3 workshop.py set-icon unit:H06S ~/Downloads/kunkka.png
    python3 workshop.py set-icon ability:A136 torrent.png
    python3 workshop.py set-icon item:I0B4 scepter.png
    python3 workshop.py clear-icon ability:A136
    python3 workshop.py set-scale H06S 1.25 [--morph 1.25] [--alt 1.0]

Keys: unit:<rawcode>, ability:<rawcode>, item:<rawcode>.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mpq import MPQ
import blp

# ---------------------------------------------------------------- config ---
def _config() -> dict:
    data = {}
    for p in (ROOT / 'workshop.json', ROOT / 'workshop.local.json'):
        if p.is_file(): data.update(json.loads(p.read_text()))
    return data
CONFIG = _config()

def _setting(env, key, default=None):
    return os.environ.get(env) or CONFIG.get(key) or default

def game_root() -> Path:
    raw = _setting('HERO_WORKSHOP_GAME_ROOT', 'game_root')
    if raw: return Path(raw).expanduser()
    # The repository normally lives in <Warcraft III>/Dota Mod Project/Tools/HeroWorkshop.
    for cand in (ROOT, *ROOT.parents):
        if (cand / 'Maps' / 'Downloads').is_dir(): return cand
    return ROOT.parents[3] if len(ROOT.parents) > 3 else ROOT.parent

GAME = game_root()
def map_path() -> Path:
    raw = _setting('HERO_WORKSHOP_MAP', 'map') or CONFIG.get('map_relative_to_game', 'Maps/Downloads/D85 06 DotaHQv5.w3x')
    p = Path(raw).expanduser()
    return p if p.is_absolute() else GAME / p
MAP = map_path()
WORK = ROOT / '.work' / re.sub(r'[^A-Za-z0-9_.-]+', '_', MAP.stem)
STATE_DIR = ROOT / 'state' / re.sub(r'[^A-Za-z0-9_.-]+', '_', MAP.stem)
BACKUPS = Path(_setting('HERO_WORKSHOP_BACKUPS', 'backups', GAME / 'Dota Mod Project/Archives/HeroWorkshop/Backups/HeroWorkshop'))
TRASH = Path(_setting('HERO_WORKSHOP_TRASH', 'trash', GAME / 'Dota Mod Project/Archives/HeroWorkshop/Trash'))
SELECTION = ROOT / 'data' / 'MODEL_SELECTION.json'
DOTA2_REF = ROOT / 'data' / 'dota2_reference.json'
HERO_ALIASES = ROOT / 'data' / 'hero_aliases.json'
INVENTORY = ROOT / 'HeroWorkshop_inventory' / 'manifest.json.gz'
MOD_PREFIX = re.compile(r'^WC3\w*Test\\', re.I)
KEEP_BACKUPS = int(_setting('HERO_WORKSHOP_KEEP_BACKUPS', 'keep_backups', 10))
BACKUP_INTERVAL = 30 * 60  # seconds: consecutive edits share one backup

def die(msg): raise SystemExit('ERROR: ' + msg)

# ------------------------------------------------------------ text tables --
def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def strip_color(s: str) -> str:
    return re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', s).strip().strip('"')

class Txt:
    """One Warcraft ini-like txt file: [CODE] sections of key=value lines."""
    def __init__(self, name: str, text: str):
        self.name = name; self.lines = text.split('\n'); self.sections = {}
        cur = None
        for i, line in enumerate(self.lines):
            m = re.match(r'\[(\w{4})\]\s*$', line.rstrip('\r'))
            if m: cur = m.group(1); self.sections.setdefault(cur, {}); continue
            if cur is None: continue
            m = re.match(r'([A-Za-z0-9_]+)=(.*)$', line.rstrip('\r'))
            if m: self.sections[cur].setdefault(m.group(1).lower(), (i, m.group(2), m.group(1)))
    def get(self, code, key):
        v = self.sections.get(code, {}).get(key.lower())
        return v[1] if v else None
    def set(self, code, key, value) -> bool:
        sec = self.sections.get(code)
        if sec is None: return False
        hit = sec.get(key.lower())
        if hit:
            i = hit[0]; eol = '\r' if self.lines[i].endswith('\r') else ''
            self.lines[i] = f'{hit[2]}={value}{eol}'; sec[key.lower()] = (i, value, hit[2])
        else:
            # Insert right after the section header.
            hdr = next(i for i, l in enumerate(self.lines) if l.rstrip('\r') == f'[{code}]')
            eol = '\r' if self.lines[hdr].endswith('\r') else ''
            self.lines.insert(hdr + 1, f'{key}={value}{eol}')
            self.sections = {}; self.__init__(self.name, self.text())
        return True
    def text(self) -> str: return '\n'.join(self.lines)

def slk(text: str):
    x = y = 1; cells = {}
    for line in text.splitlines():
        if line == 'E': break
        if not line.startswith('C;'): continue
        mx = re.search(r';X(\d+)', line); my = re.search(r';Y(\d+)', line)
        mk = re.search(r';(K(?:"(?:[^"\\]|\\.)*"|[^;]*))', line)
        if mx: x = int(mx.group(1))
        if my: y = int(my.group(1))
        if mk:
            v = mk.group(1); cells[(x, y)] = v[2:-1].replace('\\"', '"') if v.startswith('K"') else v[1:]
    headers = {v: k[0] for k, v in cells.items() if k[1] == 1}
    rows = {cells[(1, r)]: r for (_, r) in cells if (1, r) in cells and r > 1}
    return cells, headers, rows

def slk_set(text: str, x: int, y: int, value) -> str:
    lines = text.split('\n')
    start = next((i for i, l in enumerate(lines) if re.match(rf'^C;(?:X1;Y{y}|Y{y};X1);K', l)), None)
    if start is None: raise ValueError(f'SLK row {y} not found')
    end = next((i for i in range(start + 1, len(lines)) if re.match(r'^C;(?:X1;Y\d+|Y\d+;X1);K', lines[i]) or lines[i].rstrip('\r') == 'E'), len(lines))
    eol = '\r' if lines[start].endswith('\r') else ''
    # Drop earlier overrides of the same cell so the row stays clean.
    lines = lines[:start + 1] + [l for l in lines[start + 1:end] if not re.match(rf'^C;Y{y};X{x};K', l)] + lines[end:]
    end = next((i for i in range(start + 1, len(lines)) if re.match(r'^C;(?:X1;Y\d+|Y\d+;X1);K', lines[i]) or lines[i].rstrip('\r') == 'E'), len(lines))
    # SYLK strings are not JSON: backslashes stay as they are, only quotes are escaped.
    lines.insert(end, f'C;Y{y};X{x};K"{str(value).replace(chr(34), chr(92) + chr(34))}"{eol}')
    return '\n'.join(lines)

# ---------------------------------------------------------------- the map --
class Workshop:
    def __init__(self):
        if not MAP.is_file(): die(f'Карта не найдена: {MAP}. Укажите map в workshop.local.json или HERO_WORKSHOP_MAP.')
        self.mpq = MPQ(MAP)
        self.changes = {}
        self.txt = {}
        for n in self.mpq.list():
            if n.lower().endswith('.txt') and n.lower().startswith('units\\'):
                self.txt[n] = Txt(n, self.mpq.read(n).decode('latin1'))
        self.unit_abils = slk(self.mpq.read('Units\\UnitAbilities.slk').decode('latin1', 'replace'))
        self.unit_ui_text = self.mpq.read('units\\unitUI.slk').decode('latin1', 'replace')
        self.unit_ui = slk(self.unit_ui_text)
        self.items = slk(self.mpq.read('units\\ItemData.slk').decode('latin1', 'replace'))
        self.abil_data = slk(self.mpq.read('Units\\AbilityData.slk').decode('latin1', 'replace'))
        self.script = self.mpq.read('war3map.j').decode('latin1', 'replace')
        self.p3 = {}
        for m in re.finditer(r"call P3\(('?\$?[0-9A-Fa-z]+'?),'(\w{4})','(\w{4})','(\w{4})',\"([^\"]*)\",([-.0-9]+),(\d+)\)", self.script):
            self.p3[m.group(2)] = {'index': m.group(1), 'morph': m.group(3), 'dummy': m.group(4), 'anim': m.group(5), 'scale': float(m.group(6)), 'kind': int(m.group(7)), 'span': m.span(6)}
        self.selection = {e['rawcode']: e for e in json.loads(SELECTION.read_text())} if SELECTION.exists() else {}
        self.state = json.loads((STATE_DIR / 'state.json').read_text()) if (STATE_DIR / 'state.json').exists() else {}
        for k in ('icons', 'scales', 'related'): self.state.setdefault(k, {})
        self._inventory = None
        self._sample_index = None
        self._backed_up = False
        self.dota2 = json.loads(DOTA2_REF.read_text()) if DOTA2_REF.exists() else {'heroes': {}, 'items': {}}
        self.aliases = json.loads(HERO_ALIASES.read_text()).get('aliases', {}) if HERO_ALIASES.exists() else {}
        self._d2_by_name = {norm(v['name']): k for k, v in self.dota2['heroes'].items()}
        self._ability_index = None
        self._groups = None
        self._claimed = None

    # ---- lookups
    def txt_value(self, code: str, key: str, prefer: str):
        """Value from the txt file that wins in game: *Func.txt first, then Strings."""
        order = sorted(self.txt, key=lambda n: (prefer.lower() not in n.lower(), 'strings' in n.lower(), n))
        for n in order:
            v = self.txt[n].get(code, key)
            if v is not None and v.strip() != '': return n, v.split(',')[0].strip().strip('"')
        return None, None
    def name(self, code: str, prefer: str) -> str:
        _, v = self.txt_value(code, 'Name', prefer)
        return strip_color(v) if v else code
    def inventory(self):
        if self._inventory is None:
            self._inventory = {}
            if INVENTORY.exists():
                for r in json.load(gzip.open(INVENTORY))['files']:
                    self._inventory[(r['root'] + '\\' + r['path']).lower()] = r
        return self._inventory
    def resolve(self, art: str | None) -> dict:
        """Where does this art path load from right now?"""
        if not art: return {'where': 'none'}
        cands = [art] if re.search(r'\.(blp|tga|dds|mdx|mdl)$', art, re.I) else [art + '.blp', art + '.tga']
        for c in cands:
            if self.mpq.has(c): return {'where': 'map', 'path': c}
        for c in cands:
            p = GAME / c.replace('\\', '/')
            if p.is_file(): return {'where': 'disk', 'path': c, 'file': str(p)}
        for c in cands:
            if c.lower() in self.inventory(): return {'where': 'disk', 'path': c, 'inventory': True}
        if not MOD_PREFIX.match(art):
            # The HQ mod keeps copies of standard icons under WC3DotaHQTest\A: usable as a sample.
            for c in cands:
                alt = 'WC3DotaHQTest\\A\\' + c
                p = self.disk(alt)
                if p.is_file(): return {'where': 'standard', 'path': c, 'sample': alt, 'file': str(p)}
        return {'where': 'standard' if not MOD_PREFIX.match(art) else 'missing', 'path': cands[0]}
    def sample_index(self):
        """basename (lowercase, no extension) -> inventory records with that basename
        and an image extension. Built once, lazily, so it never slows down `resolve`."""
        if self._sample_index is None:
            idx = {}
            for r in self.inventory().values():
                p = r['path'].replace('\\', '/')
                if Path(p).suffix.lower() not in ('.blp', '.png', '.tga'): continue
                idx.setdefault(Path(p).stem.lower(), []).append(r)
            self._sample_index = idx
        return self._sample_index
    def sample_for(self, art: str) -> str | None:
        """Best-effort stand-in for a standard icon: some other file anywhere under the
        game folder with the same basename, that actually exists on disk."""
        base = Path(art.replace('\\', '/')).stem.lower()
        recs = self.sample_index().get(base)
        if not recs: return None
        rank = {'wc3dotahqtest': 0, 'icon audit': 1}
        for r in sorted(recs, key=lambda r: rank.get(r['root'].lower(), 2)):
            p = GAME / r['root'] / r['path'].replace('\\', '/')
            if p.is_file(): return r['root'] + '\\' + r['path']
        return None
    def read_icon(self, res: dict) -> bytes | None:
        if res.get('where') == 'map': return self.mpq.read(res['path'])
        if res.get('where') == 'disk' and res.get('file'): return Path(res['file']).read_bytes()
        if res.get('where') == 'standard' and res.get('sample'):
            p = GAME / res['sample'].replace('\\', '/')
            if p.is_file(): return p.read_bytes()
        return None
    @staticmethod
    def disk(game_path: str) -> Path:
        """Game-style path (backslashes, relative to the Warcraft folder) -> file on disk."""
        return GAME / game_path.replace('\\', '/')
    @staticmethod
    def disabled_path(path: str) -> str:
        d = re.sub(r'CommandButtons\\BTN', r'CommandButtonsDisabled\\DISBTN', path, flags=re.I)
        d = re.sub(r'PassiveButtons\\PASBTN', r'CommandButtonsDisabled\\DISPASBTN', d, flags=re.I)
        d = re.sub(r'PassiveButtons\\BTN', r'CommandButtonsDisabled\\DISBTN', d, flags=re.I)
        d = re.sub(r'AutocastButtons\\CBTN', r'CommandButtonsDisabled\\DISCBTN', d, flags=re.I)
        return d

    # ---- model
    def art_of(self, key: str):
        kind, code = key.split(':', 1)
        if kind == 'common':
            base = next((b for n, _, b in self.COMMON if n == code), None)
            return ('common', f'ReplaceableTextures\\CommandButtons\\{base}.blp') if base else (None, None)
        if kind == 'unit': return self.txt_value(code, 'Art', 'UnitFunc')
        if kind == 'item': return self.txt_value(code, 'Art', 'ItemFunc')
        file, art = self.txt_value(code, 'Art', 'AbilityFunc')
        return (file, art) if art else self.txt_value(code, 'Researchart', 'AbilityFunc')
    def icon_info(self, key: str) -> dict:
        file, art = self.art_of(key)
        res = self.resolve(art)
        dis = self.resolve(self.disabled_path(art)) if art else {'where': 'none'}
        info = {'art': art, 'art_file': file, 'normal': res, 'disabled': dis}
        ov = self.state['icons'].get(key)
        if ov: info['override'] = ov
        return info
    def hero_like(self):
        """Every unit with hero abilities (uppercase rawcode = hero in Warcraft)."""
        ab, h, rows = self.unit_abils
        return [c for c, r in rows.items() if c[0].isupper() and ab.get((h['heroAbilList'], r), '').strip()]
    def unit_model(self, code):
        cells, h, rows = self.unit_ui
        return cells.get((h['file'], rows[code])) if code in rows else None
    def hero_groups(self):
        """Primary heroes (P3 table / model selection) and their form variants.
        A unit is a variant of a hero when it shares the hero's name or model."""
        if self._groups is None: self._groups = self._hero_groups()
        return self._groups
    def _hero_groups(self):
        primary = [c for c in list(self.p3) + list(self.selection) if c in self.unit_ui[2]]
        primary = list(dict.fromkeys(primary))
        by_name = {}; by_model = {}
        for c in primary:
            by_name.setdefault(self.name(c, 'UnitFunc').lower(), c)
            m = self.unit_model(c)
            if m: by_model.setdefault(m.lower(), c)
        variants = {c: [] for c in primary}; others = []
        for c in self.hero_like():
            if c in variants: continue
            owner = by_name.get(self.name(c, 'UnitFunc').lower()) or by_model.get((self.unit_model(c) or '').lower())
            if owner: variants[owner].append(c)
            else: others.append(c)
        return variants, others
    def hero_codes(self):
        variants, others = self.hero_groups()
        return sorted(variants, key=lambda c: self.hero_name(c).lower()) + sorted(others, key=lambda c: self.hero_name(c).lower())
    def hero_name(self, code):
        sel = self.selection.get(code)
        return sel['hero'] if sel and sel.get('hero') else self.name(code, 'UnitFunc')
    def model_scale(self, code):
        cells, h, rows = self.unit_ui
        r = rows.get(code)
        if not r or 'modelScale' not in h: return None
        v = cells.get((h['modelScale'], r))
        return float(v) if v not in (None, '') else 1.0
    def xy(self, code: str, key: str):
        _, v = self.txt_value(code, key, 'AbilityFunc')
        if not v: return None
        # txt_value keeps the first comma field only; re-read the raw line here.
        for n in self.txt:
            raw = self.txt[n].get(code, key)
            if raw:
                try: return [int(x) for x in raw.split(',')[:2]]
                except ValueError: return None
        return None
    def abilities(self, code):
        ab, h, rows = self.unit_abils
        r = rows[code]; out = []
        for field in ('heroAbilList', 'abilList'):
            for a in ab.get((h[field], r), '').split(','):
                a = a.strip()
                if not a or any(x['code'] == a for x in out): continue
                out.append({'code': a, 'name': self.name(a, 'AbilityFunc'), 'hero': field == 'heroAbilList',
                            'buttonpos': self.xy(a, 'Buttonpos'), 'researchpos': self.xy(a, 'Researchbuttonpos'),
                            'icon': self.icon_info('ability:' + a)})
        return out
    def summoned_by(self, ability: str) -> list[str]:
        """Unit rawcodes an ability creates (UnitID fields of AbilityData.slk)."""
        data, h, rows = self.abil_data
        r = rows.get(ability)
        if not r: return []
        out = []
        for col, x in h.items():
            if re.match(r'UnitID\d+$', col):
                for u in data.get((x, r), '').split(','):
                    u = u.strip().strip('"')
                    if len(u) == 4 and u not in out and u != ability: out.append(u)
        return out
    def unit_card(self, code: str, relation: str) -> dict | None:
        cells, h, rows = self.unit_ui
        _, arows = self.unit_abils[0], self.unit_abils[2]
        if code not in rows and code not in arows: return None
        return {'code': code, 'relation': relation, 'name': self.name(code, 'UnitFunc'),
                'model': cells.get((h['file'], rows[code])) if code in rows else None,
                'scale': self.model_scale(code), 'p3_scale': self.p3[code]['scale'] if code in self.p3 else None,
                'saved_scales': self.state['scales'].get(code),
                'icon': self.icon_info('unit:' + code), 'abilities': self.abilities(code) if code in arows else []}
    def related_units(self, code: str, abilities: list) -> list:
        seen = []; out = []
        def add(u, rel):
            if u and u != code and u not in seen:
                seen.append(u); card = self.unit_card(u, rel)
                if card: out.append(card)
        p3 = self.p3.get(code); sel = self.selection.get(code, {})
        if p3: add(p3['morph'], 'юнит в таверне выбора (P3)')
        add(sel.get('alternative_rawcode'), 'альтернативная модель')
        for u in self.hero_groups()[0].get(code, []): add(u, 'вариант / форма героя')
        for a in abilities:
            for u in self.summoned_by(a['code']): add(u, f'призыв: {a["name"]}')
        for u in self.state['related'].get(code, []): add(u, 'добавлен вручную')
        return out
    def dota2_hero(self, code):
        """Dota 2 reference entry for a map hero (by name or alias)."""
        for nm in (self.hero_name(code), self.name(code, 'UnitFunc')):
            k = norm(nm); k = self.aliases.get(k, k)
            key = self._d2_by_name.get(k) or (k if k in self.dota2['heroes'] else None)
            if key: return key, self.dota2['heroes'][key]
        return None, None
    def ability_index(self):
        """normalized ability name -> [rawcodes] over every ability defined in the map."""
        if self._ability_index is None:
            idx = {}
            for n, t in self.txt.items():
                if 'ability' not in n.lower(): continue
                for c, sec in t.sections.items():
                    if 'name' in sec:
                        idx.setdefault(norm(strip_color(sec['name'][1].split(',')[0])), []).append(c)
            self._ability_index = idx
        return self._ability_index
    def hero(self, code):
        p3 = self.p3.get(code); sel = self.selection.get(code, {})
        alt = sel.get('alternative_rawcode')
        cells, h, rows = self.unit_ui
        abilities = self.abilities(code)
        d2key, d2 = self.dota2_hero(code)
        d2names = [a['name'] for a in d2['abilities']] if d2 else []
        order = {norm(n): i for i, n in enumerate(d2names)}
        # Own abilities in Dota 2 order, the rest by button position.
        abilities.sort(key=lambda a: (order.get(norm(a['name']), 99), (a['buttonpos'] or [9, 9])[1], (a['buttonpos'] or [9, 9])[0]))
        for a in abilities:
            if norm(a['name']) in order: a['dota2'] = d2['abilities'][order[norm(a['name'])]]
        related = self.related_units(code, abilities)
        forms = [u for u in related if u['relation'].startswith(('вариант', 'альтернатив'))]
        summons = [u for u in related if u['relation'].startswith(('призыв', 'добавлен'))]
        tavern = next((u for u in related if u['relation'].startswith('юнит в таверне')), None)
        own = {a['code'] for a in abilities}
        for f in forms:
            # A form repeats most of the hero's kit; show only what is new on it.
            f['abilities'] = [a for a in f['abilities'] if a['code'] not in own]
        taken = own | {a['code'] for u in related for a in u['abilities']}
        if self._claimed is None:
            uab, uh, urows = self.unit_abils
            self._claimed = {c.strip() for hc in self.hero_like() for f in ('heroAbilList', 'abilList') for c in uab.get((uh[f], urows[hc]), '').split(',') if c.strip()}
        claimed = self._claimed
        extra = []
        for nm in d2names:
            if norm(nm) in {norm(a['name']) for a in abilities}: continue
            for c in self.ability_index().get(norm(nm), []):
                # Only map-made abilities (A + uppercase/digits); standard Warcraft ones share these names.
                if not re.match(r'^A[0-9A-Z]{3}$', c): continue
                if c in taken or c in claimed or c in {x['code'] for x in extra}: continue
                info = self.icon_info('ability:' + c)
                if info['art'] is None: continue
                extra.append({'code': c, 'name': self.name(c, 'AbilityFunc'), 'hero': False, 'buttonpos': self.xy(c, 'Buttonpos'),
                              'researchpos': None, 'icon': info, 'dota2': d2['abilities'][order[norm(nm)]]})
        return {'code': code, 'name': self.hero_name(code), 'txt_name': self.name(code, 'UnitFunc'),
                'group': 'hero' if (p3 or code in self.selection) else 'other',
                'dota2': {'key': d2key, 'name': d2['name'], 'img': d2['img']} if d2 else None,
                'model': cells.get((h['file'], rows[code])) if code in rows else None,
                'scale': self.model_scale(code), 'p3_scale': p3['scale'] if p3 else None,
                'morph': p3['morph'] if p3 else None, 'morph_scale': self.model_scale(p3['morph']) if p3 else None,
                'alt': alt, 'alt_scale': self.model_scale(alt) if alt else None,
                'saved_scales': self.state['scales'].get(code),
                'icon': self.icon_info('unit:' + code), 'abilities': abilities,
                'extra_abilities': extra, 'forms': forms, 'summons': summons, 'tavern': tavern,
                'related': related}
    def shops(self):
        """Item shops: units selling dummy units (one per item). Shop entries carry
        the icon seen in the shop; the script converts a bought unit into the item."""
        out = []
        for n, t in self.txt.items():
            for code, sec in t.sections.items():
                if 'sellunits' not in sec or not code[0].islower(): continue
                sold = [x.strip() for x in sec['sellunits'][1].split(',') if x.strip()]
                if len(sold) < 4 or not all(s[0].islower() for s in sold): continue
                if any(s['code'] == code for s in out): continue
                out.append({'code': code, 'name': self.name(code, 'UnitFunc'), 'units': sold})
        return sorted(out, key=lambda s: s['name'].lower())
    @staticmethod
    def item_base_name(name: str) -> str:
        """'Aghanim's Scepter (Zeus)', 'Diffusal Blade Level 2' -> one family name."""
        s = re.sub(r'\s*[\(\[].*$', '', name)
        s = re.sub(r'\s*(level|lvl)\s*\d+\s*$', '', s, flags=re.I)
        s = re.sub(r'\s*-\s*\d+\s*$', '', s)
        return s.strip() or name
    STATE_WORDS = {'on', 'off', 'agility', 'strength', 'intelligence', 'level', 'lvl', 'charged', 'empty', 'full', 'active', 'inactive', 'used', 'unused', 'melee', 'ranged'}
    def item_variant_key(self, name: str) -> str:
        """Cards inside a family: a bracket suffix is a real variant only when it names a
        state (Power Treads (Agility), Armlet (On), Dagon Level 3); anything else, e.g. a
        hero name after Aghanim's Scepter, is the same item."""
        m = re.match(r'^(.*?)\s*\(([^)]*)\)?\s*$', name)
        if m and m.group(2):
            words = [w for w in re.split(r'[^a-z0-9]+', m.group(2).strip().lower()) if w]
            if any(w in self.STATE_WORDS or w.isdigit() for w in words): return norm(name)
            return norm(m.group(1))
        return norm(name)
    def item_list(self):
        """Items grouped into families by base name (all Aghanim's Scepters are one
        family). A family joins its shop entry units (what the shop shows) with its
        item rawcodes (what the inventory shows) and lists variants by distinct icon."""
        data, h, rows = self.items; fam = {}
        def family(base):
            return fam.setdefault(base, {'name': base, 'names': [], 'codes': [], 'shop_units': [], 'variants': {}, 'icon': None, 'icon_item': None})
        for code, r in rows.items():
            name = self.name(code, 'ItemFunc')
            if name == code: continue
            g = family(self.item_base_name(name)); g['codes'].append(code)
            if name not in g['names']: g['names'].append(name)
            info = self.icon_info('item:' + code)
            # one card per distinct full item name (Power Treads (Strength) / (Agility)
            # stay separate, the 243 Aghanim's Scepters collapse into one); the card's
            # icon is the first code's art, set-icon applies to every code of the card
            v = g['variants'].setdefault(self.item_variant_key(name), {'art': info['art'], 'names': [], 'codes': [], 'icon': info})
            if not v['art'] and info['art']: v['art'] = info['art']; v['icon'] = info
            v['codes'].append(code)
            if name not in v['names']: v['names'].append(name)
            if info['art'] and (g['icon_item'] is None or (g['icon_item']['normal']['where'] in ('none', 'standard') and info['normal']['where'] in ('map', 'disk'))):
                g['icon_item'] = info
        by_norm = {norm(n): n for n in fam}
        for shop in self.shops():
            for i, u in enumerate(shop['units']):
                uname = self.name(u, 'UnitFunc'); key = norm(self.item_base_name(uname))
                base = by_norm.get(key) or next((n for k, n in by_norm.items() if k.startswith(key) and len(key) >= 5), None) or self.item_base_name(uname)
                g = family(base)
                info = self.icon_info('unit:' + u)
                g['shop_units'].append({'code': u, 'shop': shop['code'], 'shop_name': shop['name'], 'index': i, 'buttonpos': self.xy(u, 'Buttonpos'), 'icon': info})
                if g['icon'] is None and info['art']: g['icon'] = info
        out = []
        for g in fam.values():
            variants = [v for v in g['variants'].values() if v['art'] or v['codes']]
            for v in variants:
                v['label'] = ', '.join(v['names'][:3]) + (' …' if len(v['names']) > 3 else '')
                v['keys'] = ','.join('item:' + c for c in v['codes'])
            g['variants'] = sorted(variants, key=lambda v: (v['icon']['normal']['where'] in ('none', 'standard'), v['label']))
            if g['icon_item'] is None: g['icon_item'] = self.icon_info('item:' + g['codes'][0]) if g['codes'] else None
            if g['icon'] is None: g['icon'] = g['icon_item'] or self.icon_info('item:----')
            g['code'] = g['codes'][0] if g['codes'] else None
            g['count'] = len(g['codes']); g['distinct_arts'] = len(variants)
            keys = ['unit:' + s['code'] for s in g['shop_units'] if s['icon']['art']] + ['item:' + c for c in g['codes'] if self.art_of('item:' + c)[1]]
            g['keys'] = ','.join(keys)
            g['in_shops'] = sorted({s['shop_name'] for s in g['shop_units']})
            out.append(g)
        return sorted(out, key=lambda x: x['name'].lower())
    COMMON = [('Move', 'Движение', 'BTNMove'), ('Stop', 'Стоп', 'BTNStop'), ('HoldPosition', 'Удерживать позицию', 'BTNHoldPosition'),
              ('Attack', 'Атака', 'BTNAttack'), ('Patrol', 'Патруль', 'BTNPatrol'), ('Cancel', 'Отмена', 'BTNCancel'),
              ('Skillz', 'Изучить способность (+)', 'BTNSkillz'), ('SelectHero', 'Выбор героя', 'BTNSelectHero')]
    def common_icons(self):
        """Command buttons shared by every unit. Their art lives at fixed standard
        paths; a file at that path inside the map overrides the game's own."""
        out = []
        for name, label, base in self.COMMON:
            art = f'ReplaceableTextures\\CommandButtons\\{base}.blp'
            info = self.icon_info('common:' + name)
            out.append({'key': 'common:' + name, 'name': label, 'base': base, 'icon': info})
        info = self.icon_info('ability:A0NR')
        out.insert(0, {'key': 'ability:A0NR', 'name': 'Attribute Bonus (плюс к атрибутам)', 'base': 'StatUp', 'icon': info})
        return out
    # ---- previews
    def preview(self, key: str, res: dict, suffix: str) -> str | None:
        if res.get('where') == 'standard' and 'sample' not in res:
            s = self.sample_for(res.get('path', ''))
            if s: res['sample'] = s
        data = self.read_icon(res)
        if not data: return None
        pdir = WORK / 'previews'; pdir.mkdir(parents=True, exist_ok=True)
        stamp = hashlib.sha1(data).hexdigest()[:10]
        out = pdir / f'{key.replace(":", "_")}_{suffix}_{stamp}.png'
        if not out.exists():
            for old in pdir.glob(f'{key.replace(":", "_")}_{suffix}_*.png'): old.unlink()
            try: blp.decode(data).save(out)
            except Exception as e:
                print(f'WARN: preview {key}: {e}', file=sys.stderr); return None
        return str(out.relative_to(WORK))
    def with_previews(self, key: str, info: dict):
        info['normal']['preview'] = self.preview(key, info['normal'], 'n')
        info['disabled']['preview'] = self.preview(key, info['disabled'], 'd')
        return info
    def export_state(self, previews: bool = True) -> Path:
        heroes = [self.hero(c) for c in self.hero_codes()]
        items = self.item_list()
        if previews:
            for hd in heroes:
                self.with_previews('unit:' + hd['code'], hd['icon'])
                for a in hd['abilities'] + hd['extra_abilities']: self.with_previews('ability:' + a['code'], a['icon'])
                for u in hd['related']:
                    self.with_previews('unit:' + u['code'], u['icon'])
                    for a in u['abilities']: self.with_previews('ability:' + a['code'], a['icon'])
            for it in items:
                self.with_previews('item:' + (it['code'] or 'none'), it['icon'])
                if it['icon_item']: self.with_previews('item:' + (it['code'] or 'none'), it['icon_item'])
                for s in it['shop_units']: self.with_previews('unit:' + s['code'], s['icon'])
                for v in it['variants']: self.with_previews('item:' + v['codes'][0], v['icon'])
        common = self.common_icons()
        if previews:
            for c in common: self.with_previews(c['key'], c['icon'])
        out = {'map': str(MAP), 'game_root': str(GAME), 'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
               'work_dir': str(WORK), 'heroes': heroes, 'items': items, 'shops': self.shops(), 'common': common}
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / 'state.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
        return WORK / 'state.json'

    # ---- writing
    def backup_map(self):
        if self._backed_up: return
        BACKUPS.mkdir(parents=True, exist_ok=True)
        latest = max(BACKUPS.glob(f'{MAP.stem} ????????-??????.w3x'), key=lambda p: p.stat().st_mtime, default=None)
        if latest and time.time() - latest.stat().st_mtime < BACKUP_INTERVAL:
            self._backed_up = True; return
        dst = BACKUPS / f'{MAP.stem} {time.strftime("%Y%m%d-%H%M%S")}.w3x'
        shutil.copy2(MAP, dst); self._backed_up = True
        olds = sorted(BACKUPS.glob(f'{MAP.stem} ????????-??????.w3x'))
        for p in olds[:-KEEP_BACKUPS]: p.unlink()
        print('Backup:', dst)
    def trash(self, path: Path):
        if not path.exists(): return
        dst = TRASH / time.strftime('%Y-%m-%d') / path.relative_to(GAME)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists(): shutil.copy2(path, dst)
    def commit(self):
        """Write pending changes (txt, slk, script, files) into the map."""
        if not self.changes: return
        self.backup_map()
        tmp = MAP.with_suffix('.w3x.tmp')
        self.mpq.save(tmp, self.changes)
        os.replace(tmp, MAP)
        self.changes = {}
        self.mpq = MPQ(MAP)
    def save_state(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / 'state.json').write_text(json.dumps(self.state, ensure_ascii=False, indent=1) + '\n')

    def set_icon(self, key: str, source: Path):
        kind, code = key.split(':', 1)
        file, art = self.art_of(key)
        if file is None: die(f'{key}: не найден Art= в txt-файлах карты')
        normal, dis = blp.to_button_blp(source)
        if kind == 'common':
            target = art; dtarget = self.disabled_path(art)
            self.changes[target] = normal; self.changes[dtarget] = dis
            STATE_DIR.joinpath('icons').mkdir(parents=True, exist_ok=True)
            kept = STATE_DIR / 'icons' / f'{key.replace(":", "_")}{source.suffix.lower()}'
            if source.resolve() != kept.resolve(): shutil.copy2(source, kept)
            self.state['icons'][key] = {'original_art': art, 'where': 'map', 'target': target, 'disabled_target': dtarget, 'source': str(kept.relative_to(ROOT)), 'applied': time.strftime('%Y-%m-%d %H:%M:%S')}
            self.commit(); self.save_state(); print(f'Applied {key}: {target} (в карте)'); return
        STATE_DIR.joinpath('icons').mkdir(parents=True, exist_ok=True)
        kept = STATE_DIR / 'icons' / f'{key.replace(":", "_")}{source.suffix.lower()}'
        if source.resolve() != kept.resolve(): shutil.copy2(source, kept)
        entry = self.state['icons'].get(key, {'original_art': art})
        if MOD_PREFIX.match(art):
            # Unique mod file on disk: overwrite in place, keep the old one.
            tpath = art if re.search(r'\.(blp|tga)$', art, re.I) else art + '.blp'
            dpath = self.disabled_path(tpath)
            target, dtarget = self.disk(tpath), self.disk(dpath)
            for p in (target, dtarget):
                if p.exists(): self.trash(p)
            if not entry.get('original_backup') and target.exists():
                orig = STATE_DIR / 'originals' / f'{key.replace(":", "_")}.blp'
                orig.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, orig); entry['original_backup'] = str(orig.relative_to(ROOT))
            target.parent.mkdir(parents=True, exist_ok=True); dtarget.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(normal); dtarget.write_bytes(dis)
            entry.update({'where': 'disk', 'target': tpath, 'disabled_target': dpath})
        else:
            # Standard or shared path: give this object its own icon inside the map.
            target = f'ReplaceableTextures\\CommandButtons\\BTN_HW_{kind}_{code}.blp'
            dtarget = self.disabled_path(target)
            self.changes[target] = normal; self.changes[dtarget] = dis
            self.set_art(key, file, target)
            entry.update({'where': 'map', 'target': target, 'disabled_target': dtarget, 'art_file': file})
        entry.update({'source': str(kept.relative_to(ROOT)), 'applied': time.strftime('%Y-%m-%d %H:%M:%S')})
        self.state['icons'][key] = entry
        self.commit(); self.save_state()
        print(f'Applied {key}: {entry["target"]}')
    def buffs_of(self, ability: str) -> list[str]:
        """Buff rawcodes an ability applies (BuffID fields of AbilityData.slk)."""
        data, h, rows = self.abil_data
        r = rows.get(ability)
        if not r: return []
        out = []
        for col, x in h.items():
            if re.match(r'BuffID\d+$', col):
                for b in data.get((x, r), '').split(','):
                    b = b.strip().strip('"')
                    if len(b) == 4 and b not in out: out.append(b)
        return out
    def set_art(self, key: str, file: str, value: str):
        kind, code = key.split(':', 1)
        t = self.txt[file]
        akey = next((k for k in ('Art', 'art') if t.get(code, k) is not None), 'Art')
        t.set(code, akey, value)
        if kind == 'ability':
            for rk in ('Researchart', 'researchart'):
                if t.get(code, rk) is not None: t.set(code, rk, value)
            # Status (buff) icons follow the ability icon, no separate file needed.
            for buff in self.buffs_of(code):
                bfile, _ = self.txt_value(buff, 'Buffart', 'AbilityFunc')
                if bfile is None: bfile, _ = self.txt_value(buff, 'Art', 'AbilityFunc')
                if bfile is None: continue
                bt = self.txt[bfile]
                bkey = next((k for k in ('Buffart', 'buffart', 'Art', 'art') if bt.get(buff, k) is not None), 'Buffart')
                bt.set(buff, bkey, value)
                self.changes[bfile] = bt.text().encode('latin1', 'replace')
        self.changes[file] = t.text().encode('latin1', 'replace')
    def clear_icon(self, key: str):
        entry = self.state['icons'].pop(key, None)
        if not entry: die(f'{key}: замены не было')
        if entry['where'] == 'disk':
            target = self.disk(entry['target']); dtarget = self.disk(entry['disabled_target'])
            orig = ROOT / entry['original_backup'] if entry.get('original_backup') else None
            if orig and orig.exists(): shutil.copy2(orig, target)
            else: target.unlink(missing_ok=True)
            dtarget.unlink(missing_ok=True)
        else:
            if entry.get('art_file'): self.set_art(key, entry['art_file'], entry['original_art'])
            self.changes[entry['target']] = None; self.changes[entry['disabled_target']] = None
            self.commit()
        self.save_state(); print(f'Restored {key}')

    def all_icons(self):
        """(key, icon_info) for every icon export_state renders, same order/objects."""
        for hd in [self.hero(c) for c in self.hero_codes()]:
            yield 'unit:' + hd['code'], hd['icon']
            for a in hd['abilities']: yield 'ability:' + a['code'], a['icon']
            for u in hd['related']:
                yield 'unit:' + u['code'], u['icon']
                for a in u['abilities']: yield 'ability:' + a['code'], a['icon']
        for it in self.item_list(): yield 'item:' + it['code'], it['icon']
    def regen_disabled(self, apply: bool, scope: str) -> dict:
        """Rebuild every disabled icon from its normal one (blp.disabled), for icons
        whose normal image is readable (in the map or on disk)."""
        seen = {}
        for _, info in self.all_icons():
            art = info.get('art')
            if art and art not in seen: seen[art] = info
        map_arts = [a for a, i in seen.items() if i['normal']['where'] == 'map']
        disk_arts = [a for a, i in seen.items() if i['normal']['where'] == 'disk']
        skipped = len(seen) - len(map_arts) - len(disk_arts)
        targets = []
        if scope in ('all', 'map'): targets += [seen[a] for a in map_arts]
        if scope in ('all', 'disk'): targets += [seen[a] for a in disk_arts]
        written_map = written_disk = 0
        if apply:
            for info in targets:
                normal = info['normal']
                data = self.read_icon(normal)
                if not data: continue
                im = blp.fit_square(blp.decode(data))
                out = blp.encode(blp.disabled(im))
                dis_path = self.disabled_path(normal['path'])
                if normal['where'] == 'map':
                    self.changes[dis_path] = out; written_map += 1
                else:
                    target = self.disk(dis_path)
                    if target.exists(): self.trash(target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(out); written_disk += 1
            if self.changes: self.commit()
        return {'found': len(seen), 'map': len(map_arts), 'disk': len(disk_arts), 'skipped': skipped,
                'scope': scope, 'apply': apply, 'written_map': written_map, 'written_disk': written_disk}

    def set_unit_ui(self, code: str, values: dict):
        """Write unitUI.slk cells (file, unitSound, modelScale, scale, ...) for one unit."""
        cells, h, rows = self.unit_ui
        if code not in rows: die(f'{code} нет в unitUI.slk')
        text = self.unit_ui_text
        for col, v in values.items():
            if col not in h: die(f'нет колонки {col} в unitUI.slk')
            text = slk_set(text, h[col], rows[code], v); cells[(h[col], rows[code])] = str(v)
        self.unit_ui_text = text; self.changes['units\\unitUI.slk'] = text.encode('latin1', 'replace')
    def set_model(self, code: str, model: str, sound: str | None = None, scale: float | None = None, selection: float | None = None):
        model = model.replace('/', '\\'); model = re.sub(r'\.(mdx|mdl)$', '', model, flags=re.I)
        res = self.resolve(model + '.mdx')
        if res['where'] not in ('map', 'disk'):
            print(f'WARN: модель {model}.mdx не найдена ни в карте, ни на диске ({res["where"]}); записываю как есть')
        values = {'file': model}
        if sound is not None: values['unitSound'] = sound
        if scale is not None: values['modelScale'] = f'{scale:g}'
        if selection is not None: values['scale'] = f'{selection:g}'
        self.set_unit_ui(code, values)
        self.state.setdefault('models', {})[code] = {'model': model, 'applied': time.strftime('%Y-%m-%d %H:%M:%S'), **{k: v for k, v in values.items() if k != 'file'}}
        self.commit(); self.save_state()
        print(f'Model {code}: {model} ({res["where"]})' + (f', sound={sound}' if sound else '') + (f', modelScale={scale:g}' if scale is not None else ''))
    def set_scale(self, code: str, scale: float, morph: float | None = None, alt: float | None = None):
        cells, h, rows = self.unit_ui
        if code not in rows: die(f'{code} нет в unitUI.slk')
        col = h.get('modelScale') or die('нет колонки modelScale')
        if not 0.05 <= scale <= 20: die('масштаб должен быть в диапазоне 0.05–20')
        text = self.unit_ui_text
        targets = {code: scale}
        p3 = self.p3.get(code); sel = self.selection.get(code, {})
        if p3: targets[p3['morph']] = morph if morph is not None else scale
        if sel.get('alternative_rawcode') and alt is not None: targets[sel['alternative_rawcode']] = alt
        for c, v in targets.items():
            if c in rows: text = slk_set(text, col, rows[c], f'{v:g}')
        self.unit_ui_text = text; self.changes['units\\unitUI.slk'] = text.encode('latin1', 'replace')
        if p3:
            s, e = p3['span']
            self.script = self.script[:s] + f'{scale:g}' + self.script[e:]
            self.changes['war3map.j'] = self.script.encode('latin1', 'replace')
        self.state['scales'][code] = {'scale': scale, 'morph': targets.get(p3['morph']) if p3 else None, 'alt': alt, 'applied': time.strftime('%Y-%m-%d %H:%M:%S')}
        self.commit(); self.save_state()
        print(f'Scale {code}: ' + ', '.join(f'{c}={v:g}' for c, v in targets.items()) + (f', P3={scale:g}' if p3 else ''))

def candidates(key: str, w: 'Workshop'):
    """Icon library candidates for one slot key, as JSON to stdout.

    key is unit:<code>, ability:<code> or item:<code> (for items, the first
    of a possibly comma-separated multi-key string, e.g. "item:I0B4,item:I0B5").
    """
    from library_build import LIBRARY
    keys = [k.strip() for k in key.split(',') if k.strip()]
    # Item groups mix shop-unit keys and item keys: the item key names the group.
    first = next((k for k in keys if k.startswith('item:')), keys[0] if keys else key.strip())
    kind, code = first.split(':', 1)
    if kind == 'item':
        target = code
        for g in w.item_list():
            if code in g['codes'] or code == g['name']:
                target = g['name']; break
        want = {('item', target)}
    elif kind == 'unit':
        want = {('unit', code)}
    elif kind == 'common':
        base = next((b for n, _, b in w.COMMON if n == code), code)
        want = {('unassigned', base.lower()), ('unassigned', re.sub(r'^BTN', '', base).lower())}
    else:
        want = {(kind, code)}
    # Fallback pool: the hero's unmatched icons (Icon Audit folder) for its abilities and portrait.
    fallback = set()
    if kind == 'ability':
        owner = next((h for h in w.hero_like() if any(a['code'] == code for a in w.abilities(h))), None)
        if owner: fallback = {('hero-misc', w.hero_groups()[0].get(owner) and owner or owner)}
        for hero, forms in w.hero_groups()[0].items():
            if owner in forms: fallback = {('hero-misc', hero)}
    elif kind == 'unit':
        fallback = {('hero-misc', code)}
    aliases = set()
    if kind == 'unit':
        aliases = {norm(x) for x in (w.hero_name(code), w.name(code, 'UnitFunc')) if x and len(norm(x)) >= 4}
    index_path = LIBRARY / 'index.json'
    if not index_path.is_file():
        print('[]')
        print('Подсказка: библиотека не собрана, запустите python3 library_build.py', file=sys.stderr)
        return
    data = json.loads(index_path.read_text())
    seen = set(); out = []
    for e in data.get('entries', []):
        how = next((m.get('how') for m in e.get('matches', []) if (m.get('kind'), m.get('id')) in want), None)
        rank = 0
        if how is None and fallback:
            how = next((m.get('how') for m in e.get('matches', []) if (m.get('kind'), m.get('id')) in fallback), None)
            if how is None: continue
            base = e.get('base', '')
            if kind == 'unit' and not any(a in base or base in a for a in aliases) and 'hero' not in base: continue
            how = 'папка героя, вручную: ' + how; rank = 1
        if how is None: continue
        files = e.get('files') or []
        if not files: continue
        sha1 = e.get('sha1')
        if sha1:
            if sha1 in seen: continue
            seen.add(sha1)
        blp_file = next((f for f in files if f.lower().endswith('.blp')), None)
        chosen = blp_file or files[0]
        stem = chosen.rsplit('.', 1)[0]
        png_file = next((f for f in files if f == stem + '.png'), None) or next((f for f in files if f.lower().endswith('.png')), None)
        out.append({
            'file': str((LIBRARY / chosen).resolve()),
            'preview': str((LIBRARY / png_file).resolve()) if png_file else str((LIBRARY / chosen).resolve()),
            'set': e.get('set', ''), 'source': e.get('path', ''), 'how': how, 'rank': rank,
        })
    def sort_key(item):
        s = item['set']
        pri = 3 if s.startswith('map-') else 0 if s.startswith('audit-') else 1
        return (item['rank'], pri, s)
    out.sort(key=sort_key)
    print(json.dumps(out, ensure_ascii=False))

# ------------------------------------------------------------------ cli ----
def doctor():
    print('Repo:      ', ROOT); print('Game root: ', GAME, '(ok)' if (GAME / 'Maps').is_dir() else '(нет папки Maps!)')
    print('Map:       ', MAP, '(ok)' if MAP.is_file() else '(не найдена)')
    print('Backups:   ', BACKUPS); print('State:     ', STATE_DIR)
    if MAP.is_file():
        w = Workshop(); print('Heroes:    ', len(w.hero_codes()), ' items:', len(w.item_list()), ' P3 entries:', len(w.p3))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor')
    s = sub.add_parser('state'); s.add_argument('--no-previews', action='store_true')
    s = sub.add_parser('set-icon'); s.add_argument('key'); s.add_argument('file')
    s = sub.add_parser('clear-icon'); s.add_argument('key')
    s = sub.add_parser('set-scale'); s.add_argument('rawcode'); s.add_argument('scale', type=float); s.add_argument('--morph', type=float); s.add_argument('--alt', type=float)
    s = sub.add_parser('set-model', help='сменить модель юнита (unitUI.slk:file)'); s.add_argument('unit'); s.add_argument('model'); s.add_argument('--sound'); s.add_argument('--scale', type=float); s.add_argument('--selection', type=float)
    s = sub.add_parser('add-related'); s.add_argument('hero'); s.add_argument('unit')
    s = sub.add_parser('remove-related'); s.add_argument('hero'); s.add_argument('unit')
    s = sub.add_parser('regen-disabled'); s.add_argument('--apply', action='store_true'); s.add_argument('--scope', choices=['all', 'map', 'disk'], default='all')
    s = sub.add_parser('candidates'); s.add_argument('key')
    a = ap.parse_args()
    if a.cmd == 'doctor': return doctor()
    w = Workshop()
    if a.cmd == 'state': print(w.export_state(not a.no_previews))
    elif a.cmd == 'candidates': candidates(a.key, w)
    elif a.cmd == 'set-icon':
        for key in [k.strip() for k in a.key.split(',') if k.strip()]: w.set_icon(key, Path(a.file).expanduser())
    elif a.cmd == 'clear-icon':
        for key in [k.strip() for k in a.key.split(',') if k.strip()]:
            if key in w.state['icons']: w.clear_icon(key)
    elif a.cmd == 'set-scale': w.set_scale(a.rawcode.strip(), a.scale, a.morph, a.alt)
    elif a.cmd == 'set-model': w.set_model(a.unit.strip(), a.model, a.sound, a.scale, a.selection)
    elif a.cmd in ('add-related', 'remove-related'):
        lst = w.state['related'].setdefault(a.hero, [])
        if a.cmd == 'add-related':
            if a.unit not in w.unit_ui[2]: die(f'{a.unit} нет в unitUI.slk')
            if a.unit not in lst: lst.append(a.unit)
        else:
            if a.unit in lst: lst.remove(a.unit)
        w.save_state(); print('Related units for', a.hero, ':', ', '.join(lst) or '—')
    elif a.cmd == 'regen-disabled':
        r = w.regen_disabled(a.apply, a.scope)
        print(f'Normal icons found (unique art path): {r["found"]}')
        print(f'  in map:                              {r["map"]}')
        print(f'  on disk:                              {r["disk"]}')
        print(f'  skipped (standard/none):              {r["skipped"]}')
        if a.apply:
            print(f'Disabled written to map:              {r["written_map"]}')
            print(f'Disabled written to disk:             {r["written_disk"]}')
        else:
            print('Dry run, nothing written. Re-run with --apply to write the disabled icons.')

if __name__ == '__main__':
    main()
