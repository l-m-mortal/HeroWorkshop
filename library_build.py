#!/usr/bin/env python3
"""Rebuild one icon pool for Hero Workshop out of every icon source on disk.

Sources: mod folders next to the game (WC3DotaHQTest, WC3Dota2Test, ...),
icon packs in `Dota Mod Project/Sources/Packs`, the Icon Audit workspace,
and the icons stored inside every DotA map found. Every file is matched to a
hero, a hero ability or an item of the current map (by the art path the maps
use, by Icon Audit folder, by name), copied once (deduplicated by content)
and gets a PNG preview.

Result: <game>/Dota Mod Project/Library/icons/
    heroes/<Hero>__<code>/hero/<set>__<file>.blp|png
    heroes/<Hero>__<code>/abilities/<Ability>__<code>/<set>__<file>...
    heroes/<Hero>__<code>/misc/...           icons of this hero not tied to an ability
    items/<Item>/<set>__<file>...
    unassigned/<basename>/<set>__<file>...
    index.json                               everything, with matches and sources

    python3 library_build.py --plan          # only report what would be matched
    python3 library_build.py                 # build the pool
    python3 library_build.py --also-map "Maps/Downloads/D85 06 DotaHQv5.w3x"
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, re, sys, time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import workshop
from workshop import GAME, MAP, Txt, slk, strip_color
from mpq import MPQ
import blp

LIBRARY = Path(os.environ.get('HERO_WORKSHOP_LIBRARY') or workshop.CONFIG.get('library') or GAME / 'Dota Mod Project/Library/icons')
INVENTORY_TSV = ROOT / 'HeroWorkshop_inventory' / 'FILES_ALL.tsv'
ICON_DIR = re.compile(r'(CommandButtons|PassiveButtons|Auto[Cc]astButtons|IconsGrouped|/Icons/|\\Icons\\)', re.I)
SOURCE_DIRS = ['WC3DotaHQTest', 'WC3Dota2Test', 'WC3WardotaTest', 'ReplaceableTextures',
               'Dota Mod Project/Sources/Packs', 'Dota Mod Project/Workspaces/Dota2/Icon Audit',
               'Dota Mod Project/Build/DotaHQ/State', 'Dota Mod Project/Archives/GlobalOverrides']
MAP_DIRS = ['Maps/Downloads', 'Dota Mod Project/Sources/Maps']
FROM_INVENTORY = '--from-inventory' in sys.argv
PREFIX = re.compile(r'^(DISPASBTN|DISCBTN|DISBTN|PASBTN|CBTN|BTN|ATC|UPG)', re.I)

def norm(s: str) -> str: return re.sub(r'[^a-z0-9]', '', s.lower())
def base_of(path: str) -> str:
    """Icon identity: file name without folder, extension and BTN/DISBTN prefix."""
    name = re.sub(r'\.(blp|png|tga|dds)$', '', path.replace('\\', '/').split('/')[-1], flags=re.I)
    return PREFIX.sub('', name).lower()
def is_disabled(path: str) -> bool:
    return bool(re.match(r'^DIS', path.replace('\\', '/').split('/')[-1], re.I))
def set_name(rel: str) -> str:
    """Short label of the source set from its top folders."""
    parts = rel.replace('\\', '/').split('/')
    if parts[0] == 'Dota Mod Project':
        if parts[1] == 'Sources' and len(parts) > 4: return 'pack-' + re.sub(r'[^A-Za-z0-9]+', '', parts[4])[:24]
        if parts[1] == 'Workspaces' and 'Icon Audit' in parts:
            i = parts.index('Icon Audit'); tail = [p for p in parts[i + 1:i + 4] if p not in ('ReplaceableTextures',)]
            return 'audit-' + re.sub(r'[^A-Za-z0-9]+', '', '-'.join(tail[:2]))[:32]
        if parts[1] == 'Build': return 'build-' + re.sub(r'[^A-Za-z0-9]+', '', parts[4] if len(parts) > 4 else parts[3])[:24]
        if parts[1] == 'Archives': return 'archive-' + re.sub(r'[^A-Za-z0-9]+', '', parts[3] if len(parts) > 3 else parts[2])[:24]
    if parts[0].startswith('WC3'): return parts[0] + ('-' + parts[1] if len(parts) > 2 and parts[0] == 'WC3DotaHQTest' else '')
    return re.sub(r'[^A-Za-z0-9]+', '', parts[0])[:24] or 'root'

# ------------------------------------------------------------ map tables ---
def map_arts(path: Path) -> dict:
    """art basenames per object from one map: {'unit': {code: [base,..]}, 'ability': ..., 'item': ...}, plus names."""
    m = MPQ(path); txt = {}
    for n in m.list():
        if n.lower().endswith('.txt') and n.lower().startswith('units\\'):
            try: txt[n] = Txt(n, m.read(n).decode('latin1'))
            except Exception: pass
    out = {'unit': defaultdict(set), 'ability': defaultdict(set), 'item': defaultdict(set), 'name': {}}
    for n, t in txt.items():
        low = n.lower()
        kind = 'item' if 'itemfunc' in low or 'itemstrings' in low else 'unit' if 'unit' in low else 'ability'
        for code, sec in t.sections.items():
            for key in ('art', 'researchart', 'unart'):
                if key in sec:
                    for a in sec[key][1].split(','):
                        a = a.strip().strip('"')
                        if a and a.lower() != 'none': out[kind][code].add(base_of(a))
            if 'name' in sec and code not in out['name']: out['name'][code] = strip_color(sec['name'][1].split(',')[0])
    icons = [n for n in m.list() if ICON_DIR.search(n) and n.lower().endswith(('.blp', '.tga'))]
    return out, m, icons

# --------------------------------------------------------------- sources ---
class Entry:
    __slots__ = ('rel', 'set', 'base', 'reader', 'size', 'disabled', 'inmap')
    def __init__(self, rel, set_, reader=None, size=0, inmap=False):
        self.rel = rel; self.set = set_; self.base = base_of(rel); self.reader = reader; self.size = size
        self.disabled = is_disabled(rel); self.inmap = inmap

def disk_entries(plan_only: bool):
    entries = []
    for d in SOURCE_DIRS:
        root = GAME / d
        if root.is_dir():
            for p in root.rglob('*'):
                if p.is_file() and p.suffix.lower() in ('.blp', '.png', '.tga') and ICON_DIR.search(str(p)) and not p.name.startswith('._'):
                    rel = str(p.relative_to(GAME))
                    entries.append(Entry(rel, set_name(rel), (lambda q=p: q.read_bytes()), p.stat().st_size))
    if (not entries or len(entries) < 100 or plan_only and FROM_INVENTORY) and INVENTORY_TSV.exists():
        print('Использую список файлов из HeroWorkshop_inventory/FILES_ALL.tsv (только план).', file=sys.stderr)
        entries = []
        for row in csv.reader(open(INVENTORY_TSV, encoding='utf-8'), delimiter='\t'):
            rel = row[0]
            if rel.startswith('#') or not any(rel.startswith(d + '/') for d in SOURCE_DIRS): continue
            if rel.lower().endswith(('.blp', '.png', '.tga')) and ICON_DIR.search(rel) and not rel.split('/')[-1].startswith('._'):
                entries.append(Entry(rel, set_name(rel), None, int(row[1]) if len(row) > 1 and row[1].isdigit() else 0))
    return entries

# --------------------------------------------------------------- matching --
class Matcher:
    def __init__(self, w: workshop.Workshop, extra_maps: list[Path]):
        self.w = w
        self.targets = {}          # base -> list of (kind, code)
        self.hero_alias = {}       # normalized alias -> hero code
        self.ability_name = {}     # normalized ability name -> [code]
        self.item_name = {}
        self.hero_of_ability = {}
        self.ability_label = {}; self.hero_label = {}; self.item_label = {}
        self.qwer = {}             # hero code -> [ability codes in button order]
        variants, others = w.hero_groups()
        self.heroes = list(variants)
        for hero in self.heroes:
            self.hero_label[hero] = w.hero_name(hero)
            for alias in {w.hero_name(hero), w.name(hero, 'UnitFunc'), (w.unit_model(hero) or '').split('\\')[-1]}:
                if alias and len(norm(alias)) >= 3: self.hero_alias.setdefault(norm(alias), hero)
            abils = []
            for u in [hero] + variants[hero]:
                for a in w.abilities(u):
                    if a['icon']['art'] is None and a['buttonpos'] is None: continue
                    if a['code'] in ('AInv', 'A0NR') or a['code'] in abils: continue
                    abils.append(a['code']); self.hero_of_ability.setdefault(a['code'], hero)
                    self.ability_label[a['code']] = a['name']
                    self.ability_name.setdefault(norm(a['name']), []).append(a['code'])
                    self._add_art(a['icon']['art'], 'ability', a['code'])
            hero_abils = [a for a in w.abilities(hero) if a['hero'] and a['code'] not in ('A0NR',)]
            hero_abils.sort(key=lambda a: ((a['buttonpos'] or [9, 9])[1], (a['buttonpos'] or [9, 9])[0]))
            self.qwer[hero] = [a['code'] for a in hero_abils]
            self._add_art(w.icon_info('unit:' + hero)['art'], 'unit', hero)
            for u in variants[hero]: self._add_art(w.icon_info('unit:' + u)['art'], 'unit', hero)
        for g in w.item_list():
            self.item_label[g['name']] = g['name']
            self.item_name.setdefault(norm(g['name']), g['name'])
            for c in g['codes']: self._add_art(w.icon_info('item:' + c)['art'], 'item', g['name'])
        self.item_by_code = {c: g['name'] for g in w.item_list() for c in g['codes']}
        # Older / other maps: same rawcodes, other art paths.
        for mp in extra_maps:
            try: arts, _, _ = map_arts(mp)
            except Exception as e: print(f'WARN: {mp.name}: {e}', file=sys.stderr); continue
            for code, bases in arts['ability'].items():
                if code in self.hero_of_ability:
                    for b in bases: self.targets.setdefault(b, []).append(('ability', code))
            for code, bases in arts['unit'].items():
                hero = code if code in self.hero_label else None
                if hero:
                    for b in bases: self.targets.setdefault(b, []).append(('unit', hero))
            for code, bases in arts['item'].items():
                if code in self.item_by_code:
                    for b in bases: self.targets.setdefault(b, []).append(('item', self.item_by_code[code]))
    def _add_art(self, art, kind, ident):
        if art: self.targets.setdefault(base_of(art), []).append((kind, ident))
    def match_in_hero(self, hero, base):
        """Match an icon file name against one hero's abilities: 'AbbaCoil' -> Death Coil,
        'AAIceBlast' -> Ice Blast, 'XUlti' -> the ultimate."""
        b = norm(base)
        abils = self.qwer.get(hero, []) + [c for c, h in self.hero_of_ability.items() if h == hero and c not in self.qwer.get(hero, [])]
        # strip a hero prefix: full alias, or an abbreviation that is a prefix of the alias
        rest = b
        for alias in sorted((a for a, h in self.hero_alias.items() if h == hero), key=len, reverse=True):
            if b.startswith(alias): rest = b[len(alias):]; break
        else:
            for k in range(min(6, len(b) - 3), 1, -1):
                if any(alias.startswith(b[:k]) for alias, h in self.hero_alias.items() if h == hero): rest = b[k:]; break
        if (rest in ('ulti', 'ult', 'ultimate') or b.endswith(('ulti', 'ultimate'))) and len(self.qwer.get(hero, [])) >= 4: return (self.qwer[hero][-1], 'ульта по Q/W/E/R')
        best = None
        for a in abils:
            n = norm(self.ability_label.get(a, '')); words = [w for w in re.findall(r'[a-z]+', self.ability_label.get(a, '').lower()) if len(w) >= 4 and w not in ('the', 'with', 'from')]
            score = 0
            if n and (n in b or (rest and rest in n and len(rest) >= 4)): score = 3
            elif any(w in b for w in words): score = 2
            elif rest and n.startswith(rest[:4]) and len(rest) >= 4: score = 1
            if score and (best is None or score > best[0]): best = (score, a)
        return (best[1], 'ключевое слово в папке героя') if best else None
    def match(self, e: Entry):
        """Return list of (kind, ident, how)."""
        hits = []
        for kind, ident in dict.fromkeys(self.targets.get(e.base, [])): hits.append((kind, ident, 'путь в карте'))
        if hits: return hits
        rel = e.rel.replace('\\', '/')
        m = re.search(r'Icon Audit/Heroes/([^/]+)/', rel)
        if m:
            hero = self.hero_alias.get(norm(m.group(1)))
            if hero:
                hit = self.match_in_hero(hero, e.base)
                if hit: return [('ability', hit[0], hit[1])]
                hn = norm(self.hero_label[hero]); b = norm(e.base)
                if b.startswith('hero') or b in hn or hn in b: return [('unit', hero, 'портрет в папке Icon Audit')]
                return [('hero-misc', hero, 'папка Icon Audit')]
        m = re.search(r'IconsGrouped/([^/]+)/', rel)
        if m or re.match(r'^[a-z]+[qwer]$', e.base):
            hero = self.hero_alias.get(norm(m.group(1))) if m else self.hero_alias.get(re.sub(r'[qwer]$', '', e.base))
            if hero:
                slot = 'qwer'.find(e.base[-1]) if e.base[-1] in 'qwer' and norm(self.hero_label[hero]) == e.base[:-1] else -1
                if 0 <= slot < len(self.qwer.get(hero, [])): return [('ability', self.qwer[hero][slot], 'буква Q/W/E/R')]
                return [('unit', hero, 'имя героя')]
        n = norm(re.sub(r'^(ability|inv|spell|hero)[_-]?', '', e.base))
        if n in self.ability_name: return [('ability', c, 'имя способности') for c in self.ability_name[n]]
        if n in self.item_name: return [('item', self.item_name[n], 'имя предмета')]
        if n in self.hero_alias: return [('unit', self.hero_alias[n], 'имя героя')]
        for alias, hero in self.hero_alias.items():
            if len(alias) >= 5 and n.startswith(alias):
                rest = n[len(alias):]
                abils = [c for c, h in self.hero_of_ability.items() if h == hero]
                for a in abils:
                    if rest and rest == norm(self.ability_label.get(a, '')): return [('ability', a, 'герой+способность')]
                for a in abils:
                    an = norm(self.ability_label.get(a, ''))
                    if len(rest) >= 4 and (an.startswith(rest) or rest.startswith(an) and len(an) >= 4): return [('ability', a, 'герой+часть названия')]
                return [('hero-misc', hero, 'префикс героя')]
        return []

# ------------------------------------------------------------------ build --
def safe(s): return re.sub(r'[^A-Za-z0-9_.-]+', '_', s).strip('_') or 'x'
def target_dir(kind, ident, mt: Matcher) -> Path:
    if kind == 'ability':
        hero = mt.hero_of_ability[ident]
        return LIBRARY / 'heroes' / f'{safe(mt.hero_label[hero])}__{hero}' / 'abilities' / f'{safe(mt.ability_label.get(ident, ident))}__{ident}'
    if kind == 'unit': return LIBRARY / 'heroes' / f'{safe(mt.hero_label[ident])}__{ident}' / 'hero'
    if kind == 'hero-misc': return LIBRARY / 'heroes' / f'{safe(mt.hero_label[ident])}__{ident}' / 'misc'
    if kind == 'item': return LIBRARY / 'items' / safe(ident)
    return LIBRARY / 'unassigned' / safe(ident)

def build(plan: bool, extra_maps: list[Path], include_disabled: bool):
    w = workshop.Workshop()
    mt = Matcher(w, extra_maps)
    entries = disk_entries(plan)
    for mp in [MAP] + extra_maps:
        try: _, m, icons = map_arts(mp)
        except Exception as e: print(f'WARN: {mp}: {e}', file=sys.stderr); continue
        for n in icons:
            entries.append(Entry(n, 'map-' + safe(mp.stem)[:28], (lambda q=n, mm=m: mm.read(q)), 0, inmap=True))
    print(f'Файлов-кандидатов: {len(entries)} (из них в картах {sum(1 for e in entries if e.inmap)})', file=sys.stderr)
    index = {}; stats = defaultdict(int); per_target = defaultdict(set)
    for e in entries:
        if e.disabled and not include_disabled: stats['пропущено DISBTN'] += 1; continue
        hits = mt.match(e) or [('unassigned', e.base, '')]
        for kind, ident, how in hits:
            per_target[(kind, ident)].add(e.rel)
        key = e.rel.lower()
        if e.reader and not plan:
            try: data = e.reader()
            except Exception as ex: print(f'WARN: {e.rel}: {ex}', file=sys.stderr); continue
            digest = hashlib.sha1(data).hexdigest()
        else:
            data = None; digest = None
        rec = {'path': e.rel, 'set': e.set, 'base': e.base, 'sha1': digest, 'matches': [{'kind': k, 'id': i, 'how': h} for k, i, h in hits], 'files': []}
        if not plan and data is not None:
            for kind, ident, _ in hits:
                d = target_dir(kind, ident, mt); d.mkdir(parents=True, exist_ok=True)
                ext = e.rel.rsplit('.', 1)[-1].lower()
                stem = f'{e.set}__{safe(e.rel.replace(chr(92), "/").split("/")[-1].rsplit(".", 1)[0])}'
                out = d / f'{stem}.{ext}'
                if not out.exists() or out.stat().st_size != len(data): out.write_bytes(data)
                png = d / f'{stem}.png'
                if ext != 'png' and not png.exists():
                    try: blp.decode(data).save(png) if ext == 'blp' else blp.load_image(out).save(png)
                    except Exception as ex: print(f'WARN preview {e.rel}: {ex}', file=sys.stderr)
                rec['files'].append(str(out.relative_to(LIBRARY)))
        index[key] = rec
        stats[hits[0][0]] += 1
    # Report
    print('\nСводка:', file=sys.stderr)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]): print(f'  {v:6d}  {k}', file=sys.stderr)
    covered = defaultdict(lambda: [0, 0])
    for hero in mt.heroes:
        abils = [c for c, h in mt.hero_of_ability.items() if h == hero]
        covered[hero][1] = len(abils); covered[hero][0] = sum(1 for a in abils if per_target.get(('ability', a)))
    full = sum(1 for h, (c, n) in covered.items() if n and c == n); part = sum(1 for h, (c, n) in covered.items() if 0 < c < n); none = sum(1 for h, (c, n) in covered.items() if c == 0)
    print(f'Героев: {len(mt.heroes)}; все способности с вариантами: {full}, частично: {part}, без вариантов: {none}', file=sys.stderr)
    print('Хуже всего покрыты:', ', '.join(f'{mt.hero_label[h]} {c}/{n}' for h, (c, n) in sorted(covered.items(), key=lambda x: x[1][0] - x[1][1])[:12]), file=sys.stderr)
    items_cov = sum(1 for name in mt.item_label if per_target.get(('item', name)))
    print(f'Предметов с вариантами: {items_cov}/{len(mt.item_label)}', file=sys.stderr)
    out = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'library': str(LIBRARY), 'plan': plan, 'map': str(MAP),
           'heroes': {h: {'name': mt.hero_label[h], 'abilities': {a: mt.ability_label.get(a, a) for a, hh in mt.hero_of_ability.items() if hh == h}} for h in mt.heroes},
           'entries': list(index.values())}
    dest = (LIBRARY / 'index.json') if not plan else (ROOT / '.work' / 'library_plan.json')
    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print('Индекс:', dest, file=sys.stderr)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plan', action='store_true', help='только сопоставить и записать .work/library_plan.json')
    ap.add_argument('--from-inventory', action='store_true', help='в режиме --plan брать список файлов из инвентаря, а не с диска')
    ap.add_argument('--also-map', action='append', default=[], help='дополнительные карты (пути относительно корня игры или абсолютные)')
    ap.add_argument('--all-maps', action='store_true', help='подключить все .w3x из Maps/Downloads и Sources/Maps')
    ap.add_argument('--include-disabled', action='store_true', help='складывать и DISBTN-файлы (по умолчанию серые генерируются заново)')
    a = ap.parse_args()
    extra = []
    for m in a.also_map:
        p = Path(m).expanduser(); extra.append(p if p.is_absolute() else GAME / p)
    if a.all_maps:
        for d in MAP_DIRS:
            extra += [p for p in sorted((GAME / d).glob('*.w3x')) if p.resolve() != MAP.resolve()]
    build(a.plan, [p for p in extra if p.is_file()], a.include_disabled)

if __name__ == '__main__':
    main()
