#!/usr/bin/env python3
"""Named fixes for known problems of the DotA 6.85 map. Each fix prints its
plan; nothing is written without --apply.

    python3 map_fix.py list
    python3 map_fix.py shops            # plan
    python3 map_fix.py shops --apply
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import workshop

def fix_shops(w: workshop.Workshop, apply: bool):
    """Side shop and Secret Shop models were swapped/broken.

    In 6.77b: u010 Goblin Merchant (side shop) = buildings\\other\\Merchant\\Merchant,
              uC74 Leragas the Vile (secret shop) = units\\custom\\ShopKeeper\\ShopKeeper.
    In 6.85:  u010 got the ShopKeeper model and the SecretShop sound set,
              uC74 got a shrub doodad (invisible, unselectable)."""
    plan = [
        ('u010', 'Goblin Merchant (боковая лавка)', 'WC3DotaHQTest\\A\\Buildings\\Other\\Merchant\\Merchant', 'Merchant', 1.0, 2.5),
        ('uC74', 'Leragas the Vile (потайная лавка)', 'units\\custom\\ShopKeeper\\ShopKeeper', 'SecretShop', 1.2, 1.0),
    ]
    cells, h, rows = w.unit_ui
    for code, label, model, sound, scale, sel in plan:
        cur = cells.get((h['file'], rows[code])); res = w.resolve(model + '.mdx')
        print(f'{code} {label}\n    сейчас:  {cur}\n    станет:  {model}  [{res["where"]}], звук {sound}, modelScale {scale:g}, scale {sel:g}')
    if not apply:
        print('\nПлан. Запустите с --apply, чтобы записать в карту.'); return
    for code, label, model, sound, scale, sel in plan:
        w.set_model(code, model, sound, scale, sel)

def fix_doodads(w: workshop.Workshop, apply: bool, ref: str | None = None, types: str | None = None):
    """Copy doodad placements from a reference map (default: DotA v6.77b) for
    doodad types that the reference places but this map does not (stairs, fences...).

    --ref <map.w3x>   reference map (relative to the game root or absolute)
    --types A,B,C     only these doodad type ids (default: every type absent here)"""
    import doo
    from mpq import MPQ
    from pathlib import Path
    candidates = [Path(ref)] if ref else [Path('Dota Mod Project/Sources/Packs/DOTA 2 mod/DOTA-HQv5_RePack.part01/Maps/Download/DotA v6.77b.w3x'),
                                          Path('Dota Mod Project/Sources/Maps/DotA v6.77b.w3x')]
    candidates = [p if p.is_absolute() else workshop.GAME / p for p in candidates]
    ref_path = next((p for p in candidates if p.is_file()), None)
    if ref_path is None: workshop.die('эталонная карта 6.77b не найдена, укажите --ref <путь к DotA v6.77b.w3x>')
    cur = doo.parse(w.mpq.read('war3map.doo')); src = doo.parse(MPQ(ref_path).read('war3map.doo'))
    here = {e['type'] for e in cur['entries']}
    wanted = set(types.split(',')) if types else {e['type'] for e in src['entries']} - here
    picked = [e for e in src['entries'] if e['type'] in wanted]
    by_type = {}
    for e in picked: by_type[e['type']] = by_type.get(e['type'], 0) + 1
    print(f'Эталон: {ref_path.name}, версия doo {src["version"]}; здесь версия {cur["version"]}, размещений {len(cur["entries"])}')
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]): print(f'  {t}: {n} шт.' + ('' if t not in here else ' (тип уже есть в карте)'))
    if not picked: print('Нечего переносить.'); return
    if not apply: print(f'\nПлан: добавить {len(picked)} размещений. Запустите с --apply.'); return
    first_id = max((e['editor_id'] for e in cur['entries']), default=0) + 1
    doo.append(cur, picked, first_id)
    w.changes['war3map.doo'] = doo.serialize(cur); w.commit()
    w.state.setdefault('doodads_added', []).append({'ref': ref_path.name, 'types': sorted(wanted), 'editor_ids': [first_id, first_id + len(picked) - 1], 'applied': __import__('time').strftime('%Y-%m-%d %H:%M:%S')})
    w.save_state()
    print(f'Добавлено {len(picked)} размещений; теперь {len(cur["entries"])}. Откат: map_fix.py doodads --undo --apply')

def undo_doodads(w: workshop.Workshop, apply: bool, types: str | None = None):
    """Remove doodad placements added by `doodads` (from state) or all placements of --types."""
    import doo
    cur = doo.parse(w.mpq.read('war3map.doo'))
    if types:
        kill = set(types.split(',')); victims = [e for e in cur['entries'] if e['type'] in kill]
    else:
        added = w.state.get('doodads_added', [])
        if not added: workshop.die('нет записей о добавленных декорациях; укажите --types')
        ids = set()
        for rec in added: ids.update(range(rec['editor_ids'][0], rec['editor_ids'][1] + 1))
        victims = [e for e in cur['entries'] if e['editor_id'] in ids]
    by_type = {}
    for e in victims: by_type[e['type']] = by_type.get(e['type'], 0) + 1
    for t, n in sorted(by_type.items()): print(f'  {t}: удалить {n} шт.')
    if not victims: print('Нечего удалять.'); return
    if not apply: print(f'\nПлан: удалить {len(victims)} размещений. Запустите с --apply.'); return
    cur['entries'] = [e for e in cur['entries'] if e not in victims]
    w.changes['war3map.doo'] = doo.serialize(cur); w.commit()
    if not types: w.state['doodads_added'] = []; w.save_state()
    print(f'Удалено {len(victims)}; осталось {len(cur["entries"])}.')

def mdx_textures(data: bytes) -> list[str]:
    """Texture paths referenced by an MDX (TEXS chunk), replaceable ids skipped."""
    import struct
    out = []
    if data[:4] != b'MDLX': return out
    o = 4
    while o + 8 <= len(data):
        tag = data[o:o + 4]; size = struct.unpack_from('<I', data, o + 4)[0]; o += 8
        if tag == b'TEXS':
            for i in range(size // 268):
                rid = struct.unpack_from('<I', data, o + i * 268)[0]
                name = data[o + i * 268 + 4:o + i * 268 + 260].split(b'\0')[0].decode('latin1')
                if not rid and name: out.append(name)
        o += size
    return out

def fix_hq_doodads(w: workshop.Workshop, apply: bool, into: str = 'map', match: str | None = None, folders: str = 'Doodads'):
    r"""Bring the HQ replacements of standard doodads (WC3DotaHQTest\A\Doodads\...) into
    the map at their standard paths, so the map shows them without a root overlay.

    --into map|root   write into the map archive (default) or copy next to the game
    --match text      only paths containing text (e.g. Fence, Stairs, Northrend)
    --folders A,B     top folders under WC3DotaHQTest\A to take (default Doodads)"""
    from pathlib import Path
    a_root = workshop.GAME / 'WC3DotaHQTest' / 'A'
    if not a_root.is_dir(): workshop.die(f'нет папки {a_root}')
    files = {}
    for top in folders.split(','):
        base = a_root / top.strip()
        if not base.is_dir(): print(f'WARN: нет {base}'); continue
        for p in base.rglob('*'):
            if p.is_file() and not p.name.startswith('._'):
                rel = str(p.relative_to(a_root)).replace('/', '\\')
                if match and match.lower() not in rel.lower(): continue
                files[rel.lower()] = (rel, p)
    # textures referenced by the models but living elsewhere under A (or the game root)
    extra = {}
    index = None
    for rel, p in list(files.values()):
        if p.suffix.lower() != '.mdx': continue
        for tex in mdx_textures(p.read_bytes()):
            t = tex.replace('/', '\\')
            if t.lower() in files or t.lower() in extra: continue
            if w.mpq.has(t): continue
            # Models converted for the mod reference textures by their WC3DotaHQTest\A\... path.
            # Put every such texture into the map too: the map must not depend on the folder.
            if w.disk(t).is_file(): extra[t.lower()] = (t, w.disk(t)); continue
            cand = a_root / t.replace('\\', '/')
            if cand.is_file(): extra[t.lower()] = (t, cand); continue
            if index is None:
                index = {}
                for q in a_root.rglob('*'):
                    if q.is_file(): index.setdefault(q.name.lower(), q)
            q = index.get(t.split('\\')[-1].lower())
            if q: extra[t.lower()] = (t, q)
            else: print(f'WARN: текстура {tex} для {rel} не найдена')
    files.update(extra)
    total = sum(p.stat().st_size for _, p in files.values())
    kinds = {}
    for rel, p in files.values(): kinds[p.suffix.lower()] = kinds.get(p.suffix.lower(), 0) + 1
    print(f'Файлов: {len(files)} ({", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))}), {total / 1e6:.1f} МБ, назначение: {"карта" if into == "map" else "корень игры"}')
    for rel, p in sorted(files.values())[:15]: print('  ', rel)
    if len(files) > 15: print('   …')
    if not apply: print('\nПлан. Запустите с --apply.'); return
    if into == 'map':
        for rel, p in files.values(): w.changes[rel] = p.read_bytes()
        w.commit(); print(f'Записано в карту {len(files)} файлов.')
    else:
        import shutil
        for rel, p in files.values():
            dst = workshop.GAME / rel.replace('\\', '/')
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists(): w.trash(dst)
            shutil.copy2(p, dst)
        print(f'Скопировано в корень игры {len(files)} файлов.')

FIXES = {'shops': fix_shops, 'doodads': fix_doodads, 'hq-doodads': fix_hq_doodads}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fix', choices=list(FIXES) + ['list'])
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--ref', help='эталонная карта для doodads')
    ap.add_argument('--types', help='список типов декораций через запятую для doodads')
    ap.add_argument('--undo', action='store_true', help='doodads: удалить ранее добавленные размещения')
    ap.add_argument('--into', choices=['map', 'root'], default='map', help='hq-doodads: куда класть файлы')
    ap.add_argument('--match', help='hq-doodads: только пути, содержащие текст')
    ap.add_argument('--folders', default='Doodads', help='hq-doodads: папки под WC3DotaHQTest\\A через запятую')
    a = ap.parse_args()
    if a.fix == 'list':
        for k, f in FIXES.items(): print(f'{k:10s} {f.__doc__.strip().splitlines()[0]}')
        return
    w = workshop.Workshop()
    if a.fix == 'doodads' and a.undo: undo_doodads(w, a.apply, a.types)
    elif a.fix == 'doodads': FIXES[a.fix](w, a.apply, a.ref, a.types)
    elif a.fix == 'hq-doodads': FIXES[a.fix](w, a.apply, a.into, a.match, a.folders)
    else: FIXES[a.fix](w, a.apply)

if __name__ == '__main__':
    main()
