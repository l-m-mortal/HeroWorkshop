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

FIXES = {'shops': fix_shops, 'doodads': fix_doodads}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fix', choices=list(FIXES) + ['list'])
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--ref', help='эталонная карта для doodads')
    ap.add_argument('--types', help='список типов декораций через запятую для doodads')
    ap.add_argument('--undo', action='store_true', help='doodads: удалить ранее добавленные размещения')
    a = ap.parse_args()
    if a.fix == 'list':
        for k, f in FIXES.items(): print(f'{k:10s} {f.__doc__.strip().splitlines()[0]}')
        return
    w = workshop.Workshop()
    if a.fix == 'doodads' and a.undo: undo_doodads(w, a.apply, a.types)
    elif a.fix == 'doodads': FIXES[a.fix](w, a.apply, a.ref, a.types)
    else: FIXES[a.fix](w, a.apply)

if __name__ == '__main__':
    main()
