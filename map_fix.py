#!/usr/bin/env python3
"""Named fixes for known problems of the DotA 6.85 map. Each fix prints its
plan; nothing is written without --apply.

    python3 map_fix.py list
    python3 map_fix.py shops            # plan
    python3 map_fix.py shops --apply
"""
from __future__ import annotations
import argparse, re, sys
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

def fix_doodads(w: workshop.Workshop, apply: bool, ref: str | None = None, types: str | None = None, near: str | None = None):
    """Copy doodad placements from a reference map (default: DotA v6.77b) for
    doodad types that the reference places but this map does not (stairs, fences...).

    --ref <map.w3x>   reference map (relative to the game root or absolute)
    --types A,B,C     only these doodad type ids (default: every type absent here)
    --near=X,Y,R      only placements within R of (X,Y) (write it with '=' because of the
                      minus signs); placements already present
                      at the same spot (same type, < 8 units away) are skipped"""
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
    # Custom types (D000, B000...) mean different things in each map: never port them blindly.
    wanted = set(types.split(',')) if types else {e['type'] for e in src['entries']} - here - {t for t in {e['type'] for e in src['entries']} if re.match(r'^[DB][0-9A-Z]{3}$', t) and not t[1].isalpha()}
    wanted = {t for t in wanted if types or not re.match(r'^[DB]\d', t)}
    picked = [e for e in src['entries'] if e['type'] in wanted]
    if near:
        import math
        cx, cy, r = [float(v) for v in near.split(',')]
        picked = [e for e in picked if math.hypot(e['x'] - cx, e['y'] - cy) <= r]
        have = [(e['type'], e['x'], e['y']) for e in cur['entries'] if e['type'] in wanted]
        picked = [e for e in picked if not any(t == e['type'] and math.hypot(x - e['x'], y - e['y']) < 8 for t, x, y in have)]
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

def mdx_info(data: bytes) -> dict:
    """Version, chunk sizes, geoset and sequence counts, texture names of an MDX."""
    import struct
    info = {'ok': data[:4] == b'MDLX', 'version': None, 'geosets': 0, 'sequences': 0, 'textures': [], 'chunks': [], 'size': len(data)}
    if not info['ok']: return info
    o = 4
    while o + 8 <= len(data):
        tag = data[o:o + 4]; size = struct.unpack_from('<I', data, o + 4)[0]; o += 8
        info['chunks'].append(tag.decode('latin1', 'replace'))
        if tag == b'VERS': info['version'] = struct.unpack_from('<I', data, o)[0]
        elif tag == b'SEQS': info['sequences'] = size // 132
        elif tag == b'GEOS':
            q = o; n = 0
            while q < o + size:
                gs = struct.unpack_from('<I', data, q)[0]
                if gs <= 0: break
                n += 1; q += gs
            info['geosets'] = n
        elif tag == b'TEXS':
            for i in range(size // 268):
                rid = struct.unpack_from('<I', data, o + i * 268)[0]
                name = data[o + i * 268 + 4:o + i * 268 + 260].split(b'\0')[0].decode('latin1')
                info['textures'].append((rid, name))
        o += size
    return info

def blp_info(data: bytes) -> str:
    """One-line description of a texture: BLP1 paletted/JPEG, BLP2, TGA, size, power of two."""
    import struct
    if data[:4] == b'BLP1':
        comp, alpha, w, h, ptype, mips = struct.unpack_from('<6I', data, 4)
        kind = 'BLP1 JPEG' if comp == 0 else f'BLP1 палитра (alpha {alpha} бит, тип {ptype})'
    elif data[:4] == b'BLP2':
        w, h = struct.unpack_from('<II', data, 12); kind = 'BLP2 (WoW, WC3 не читает!)'
    elif data[:4] == b'\x89PNG':
        w, h = struct.unpack_from('>II', data, 16); kind = 'PNG'
    else:
        return f'неизвестный формат ({data[:4]!r}, {len(data)} байт)'
    p2 = (w & (w - 1) == 0) and (h & (h - 1) == 0)
    return f'{kind} {w}x{h}' + ('' if p2 else '  НЕ степень двойки!')

def probe(w: workshop.Workshop, apply: bool, at: str | None = None, ref: str | None = None):
    """List doodad placements around a point (default: the Radiant fountain) in this
    map and, side by side, in the reference 6.77b map; resolves custom types to models.

    --at=X,Y,R        centre and radius (default -7168,-7168,2600; '=' because of minus signs)
    --ref <map.w3x>   reference map (default: DotA v6.77b next to the packs)"""
    import doo, math, map_audit
    from mpq import MPQ
    from pathlib import Path
    cx, cy, r = (-7168.0, -7168.0, 2600.0) if not at else [float(v) for v in at.split(',')]
    ref_path = _ref_map(ref)
    def load(m):
        d = doo.parse(m.read('war3map.doo'))
        idx = {}
        for f, model, name in (('war3map.w3d', 'dfil', 'dnam'), ('war3map.w3b', 'bfil', 'bnam')):
            if m.has(f): idx.update(map_audit.obj_index(map_audit.parse_obj_file(m.read(f)), model, name))
        near = {}
        for e in d['entries']:
            if math.hypot(e['x'] - cx, e['y'] - cy) <= r:
                t = near.setdefault(e['type'], []); t.append(e)
        return near, idx
    here, hidx = load(w.mpq)
    there, tidx = (load(MPQ(ref_path)) if ref_path else ({}, {}))
    print(f'Точка ({cx:g}, {cy:g}), радиус {r:g}. Здесь: {sum(map(len, here.values()))} размещений; эталон {ref_path.name if ref_path else "—"}: {sum(map(len, there.values()))}.')
    print(f'{"тип":5} {"здесь":>5} {"6.77b":>5}  модель / база')
    for t in sorted(set(here) | set(there), key=lambda t: -(len(there.get(t, [])) + len(here.get(t, [])))):
        i = (hidx.get(t) if t in here else tidx.get(t)) or hidx.get(t) or tidx.get(t) or {}
        desc = ''
        if i.get('model'): desc = f'{i["model"]} (база {i.get("base")})'
        elif i.get('base') and i.get('base') != t: desc = f'база {i["base"]}'
        elif re.match(r'^[DB]\d', t): desc = 'пользовательский тип без модели'
        else: desc = 'стандартная декорация'
        if i.get('model'):
            stem = i['model'].replace('/', '\\')
            if stem.lower().endswith(('.mdx', '.mdl')): stem = stem[:-4]
            paths = [stem + '.mdx', stem + '.mdl']
            desc += '  [в карте]' if any(w.mpq.has(p) for p in paths) else '  [на диске]' if any(w.disk(p).is_file() for p in paths) else '  [файла нет: стандартная]'
        mark = '' if t in here else '  <- нет здесь'
        print(f'{t:5} {len(here.get(t, [])):>5} {len(there.get(t, [])):>5}  {desc}{mark}')
        if i.get('model') or re.match(r'^[DB][0-9A-Z]{3}$', t) and not t[1].isalpha():
            for e in here.get(t, []): print(f"        здесь: #{e['editor_id']} ({e['x']:.0f}, {e['y']:.0f}) z {e['z']:.0f} угол {math.degrees(e['angle']):.0f}° вариация {e['variation']} масштаб {e['sx']:.2f}")

def _ref_map(ref):
    from pathlib import Path
    candidates = [Path(ref)] if ref else [Path('Dota Mod Project/Sources/Packs/DOTA 2 mod/DOTA-HQv5_RePack.part01/Maps/Download/DotA v6.77b.w3x'),
                                          Path('Dota Mod Project/Sources/Maps/DotA v6.77b.w3x')]
    candidates = [p if p.is_absolute() else workshop.GAME / p for p in candidates]
    return next((p for p in candidates if p.is_file()), None)

def mdx_bounds(data: bytes):
    """(radius, min, max) over every geoset's vertices; None when there are none."""
    import struct
    o = 4; pts = []
    while o + 8 <= len(data):
        tag = data[o:o + 4]; size = struct.unpack_from('<I', data, o + 4)[0]; o += 8
        if tag == b'GEOS':
            q = o
            while q < o + size:
                gs = struct.unpack_from('<I', data, q)[0]
                if gs <= 0 or data[q + 4:q + 8] != b'VRTX': break
                n = struct.unpack_from('<I', data, q + 8)[0]
                pts.extend(struct.iter_unpack('<3f', data[q + 12:q + 12 + n * 12]))
                q += gs
        o += size
    if not pts: return None
    mn = tuple(min(p[i] for p in pts) for i in range(3)); mx = tuple(max(p[i] for p in pts) for i in range(3))
    radius = max((x * x + y * y + z * z) ** 0.5 for x, y, z in pts)
    return radius, mn, mx

def mdx_add_stand(data: bytes) -> bytes | None:
    """Give a sequence-less MDX one 'Stand' sequence (0..1000 ms) so the game treats it
    like any other doodad. Extents are computed from the vertices (converted models
    often carry zero bounds in the header, which makes the game cull them at random).
    Returns None when the model already has sequences or is not an MDX."""
    import struct
    if data[:4] != b'MDLX': return None
    o = 4; chunks = []
    while o + 8 <= len(data):
        tag = data[o:o + 4]; size = struct.unpack_from('<I', data, o + 4)[0]
        chunks.append((tag, o, size)); o += 8 + size
    if any(t == b'SEQS' and sz for t, _, sz in chunks): return None
    b = mdx_bounds(data)
    if b is None: return None
    radius, mn, mx = b
    out = bytearray(data)
    for t, off, sz in chunks:
        if t == b'MODL' and sz >= 372:  # fix header extents too when they are empty
            if struct.unpack_from('<f', out, off + 8 + 340)[0] == 0.0:
                struct.pack_into('<f3f3f', out, off + 8 + 340, radius, *mn, *mx)
    seq = b'Stand'.ljust(80, b'\0') + struct.pack('<IIfIfI', 0, 1000, 0.0, 0, 0.0, 0) + struct.pack('<f3f3f', radius, *mn, *mx)
    seqs = b'SEQS' + struct.pack('<I', len(seq)) + seq
    for t, off, sz in reversed(chunks):
        if t == b'SEQS': del out[off:off + 8 + sz]
    o = 4; ins = None
    while o + 8 <= len(out):
        tag = out[o:o + 4]; size = struct.unpack_from('<I', out, o + 4)[0]
        if tag == b'MODL': ins = o + 8 + size; break
        if tag == b'VERS': ins = o + 8 + size
        o += 8 + size
    if ins is None: return None
    out[ins:ins] = seqs
    return bytes(out)

def _hw_stand_zero_bounds(data: bytes) -> bool:
    import struct
    o = 4
    while o + 8 <= len(data):
        tag = data[o:o + 4]; size = struct.unpack_from('<I', data, o + 4)[0]; o += 8
        if tag == b'SEQS' and size == 132 and data[o:o + 5] == b'Stand' and struct.unpack_from('<f', data, o + 104)[0] == 0.0:
            return True
        o += size
    return False

def _strip_seqs(data: bytes) -> bytes:
    import struct
    out = bytearray(data); o = 4
    while o + 8 <= len(out):
        tag = out[o:o + 4]; size = struct.unpack_from('<I', out, o + 4)[0]
        if tag == b'SEQS': del out[o:o + 8 + size]; continue
        o += 8 + size
    return bytes(out)

def fix_static_models(w: workshop.Workshop, apply: bool, match: str | None = None, undo: bool = False):
    """Add an empty 'Stand' sequence to models inside the map that have none.
    (Experimental: on the HQ fences this made the models jitter instead of appearing.)

    --match text   only paths containing text
    --undo         restore every model the map holds from its copy in WC3DotaHQTest\\A"""
    if undo:
        a_root = workshop.GAME / 'WC3DotaHQTest' / 'A'
        plan = []
        for name in w.mpq.list():
            if not name.lower().endswith('.mdx'): continue
            if match and match.lower() not in name.lower(): continue
            src = a_root / name.replace('\\', '/')
            if src.is_file() and src.read_bytes() != w.mpq.read(name): plan.append((name, src))
        for name, _ in plan: print(f'  {name}: восстановить из папки HQ')
        if not plan: print('Все модели в карте совпадают с папкой HQ.'); return
        if not apply: print(f'\nПлан: восстановить {len(plan)} моделей. Запустите с --apply.'); return
        for name, src in plan: w.changes[name] = src.read_bytes()
        w.commit(); print(f'Восстановлено {len(plan)} моделей.'); return
    plan = []
    for name in w.mpq.list():
        if not name.lower().endswith('.mdx'): continue
        if match and match.lower() not in name.lower(): continue
        data = w.mpq.read(name)
        mi = mdx_info(data)
        if not mi['ok']: continue
        if mi['sequences']:
            if not _hw_stand_zero_bounds(data): continue
            data = _strip_seqs(data)  # our earlier Stand with empty bounds: rebuild it
        fixed = mdx_add_stand(data)
        if fixed: plan.append((name, mi['geosets'], fixed))
        else: print(f'  {name}: не удалось исправить')
    for name, g, _ in plan: print(f'  {name}: 0 анимаций, геосетов {g} -> добавить Stand')
    if not plan: print('Моделей без анимаций в карте нет.'); return
    if not apply: print(f'\nПлан: исправить {len(plan)} моделей. Запустите с --apply.'); return
    for name, _, fixed in plan: w.changes[name] = fixed
    w.commit(); print(f'Исправлено {len(plan)} моделей.')

def fix_repack_textures(w: workshop.Workshop, apply: bool, match: str | None = None, folders: str = 'Doodads', opaque: bool = False):
    """Re-encode JPEG BLP textures used by the HQ doodad models in the map as paletted
    BLP1 with mipmaps (JPEG BLPs converted from other games can show up white in
    1.31). Only textures referenced by MDX files under the given folders are touched.

    --match text   only models whose path contains text
    --folders A,B  model folders inside the map (default Doodads)
    --opaque       drop the alpha plane (a model whose texture is fully transparent
                   is invisible; try this when a model does not show at all)"""
    import blp, struct
    tops = tuple(f.strip().lower() + '\\' for f in folders.split(','))
    seen = {}
    for name in w.mpq.list():
        if not name.lower().endswith('.mdx') or not name.lower().startswith(tops): continue
        if match and match.lower() not in name.lower(): continue
        for rid, tex in mdx_info(w.mpq.read(name))['textures']:
            if rid: continue
            t = tex.replace('/', '\\')
            if t.lower() in seen or not w.mpq.has(t): continue
            data = w.mpq.read(t)
            if data[:4] != b'BLP1' or struct.unpack_from('<I', data, 4)[0] != 0: continue  # not JPEG
            seen[t.lower()] = (t, data, name)
    if not seen: print('JPEG-текстур у этих моделей в карте нет.'); return
    out = {}
    for t, data, model in seen.values():
        try:
            im = blp.decode(data)
            lo, hi = im.getchannel('A').getextrema()
            if opaque: im.putalpha(255)
            out[t] = blp.encode(im)
            print(f'  {t}: JPEG {im.size[0]}x{im.size[1]}, альфа {lo}..{hi}{" -> 255" if opaque else ""} -> палитра, {len(data)} -> {len(out[t])} байт   ({model.split(chr(92))[-1]})')
        except Exception as e:
            print(f'  {t}: не удалось декодировать ({e})')
    if not apply: print(f'\nПлан: перепаковать {len(out)} текстур. Запустите с --apply. Вернуть исходные: hq-doodads --apply.'); return
    for t, b in out.items(): w.changes[t] = b
    w.commit(); print(f'Перепаковано {len(out)} текстур.')

_HQ_INDEX = None
def _hq_file(a_root, rel: str):
    """Case-insensitive lookup of a game path under WC3DotaHQTest\\A."""
    global _HQ_INDEX
    if _HQ_INDEX is None:
        _HQ_INDEX = {}
        if a_root.is_dir():
            for q in a_root.rglob('*'):
                if q.is_file(): _HQ_INDEX[str(q.relative_to(a_root)).replace('/', '\\').lower()] = q
    return _HQ_INDEX.get(rel.replace('/', '\\').lower())

def fix_custom_doodads(w: workshop.Workshop, apply: bool, ref: str | None = None, types: str | None = None, near: str | None = None, undo: bool = False):
    """Port the reference map's custom doodad/destructable types (D0xx/B0xx and modified
    standard types) together with their placements. Each ported type gets a fresh id
    here (D0H0.., B0H0..), so nothing existing is touched. Models the types use are
    put into the map: HQ replacements from WC3DotaHQTest\\A at their standard path
    (with textures), imported models copied from the reference map.

    --types A,B     only these type ids of the reference (default: every custom or
                    modified type that has placements)
    --near=X,Y,R    only placements within R of (X,Y)
    --undo          remove everything this fix added (records, placements, files stay)"""
    import doo, math, map_audit
    from mpq import MPQ
    a_root = workshop.GAME / 'WC3DotaHQTest' / 'A'
    cur = doo.parse(w.mpq.read('war3map.doo'))
    objs = {}
    for fn, mf in (('war3map.w3d', 'dfil'), ('war3map.w3b', 'bfil')):
        objs[fn] = map_audit.parse_obj_file(w.mpq.read(fn)) if w.mpq.has(fn) else {'version': 2, 'original': [], 'custom': [], 'shape': 'with_level' if fn.endswith('w3d') else 'without_level'}
    if undo:
        recs = w.state.get('custom_doodads_added', [])
        if not recs: workshop.die('нет записей о перенесённых типах')
        ids = set(); tids = set()
        for r in recs: ids.update(range(r['editor_ids'][0], r['editor_ids'][1] + 1)); tids.update(r['new_types'])
        before = len(cur['entries']); cur['entries'] = [e for e in cur['entries'] if e['editor_id'] not in ids and e['type'] not in tids]
        for fn in objs: objs[fn]['custom'] = [r for r in objs[fn]['custom'] if r['new'] not in tids]
        print(f'Удалить типов {len(tids)} ({", ".join(sorted(tids))}), размещений {before - len(cur["entries"])}.')
        if not apply: print('\nПлан. Запустите с --apply.'); return
        w.changes['war3map.doo'] = doo.serialize(cur)
        for fn in objs: w.changes[fn] = map_audit.serialize_obj_file(objs[fn])
        w.commit(); w.state['custom_doodads_added'] = []; w.save_state(); print('Готово.'); return
    ref_path = _ref_map(ref)
    if ref_path is None: workshop.die('эталонная карта не найдена, укажите --ref')
    rm = MPQ(ref_path); src = doo.parse(rm.read('war3map.doo'))
    robjs = {fn: (map_audit.parse_obj_file(rm.read(fn)) if rm.has(fn) else None) for fn in objs}
    # candidate types: custom records, plus original records with a model change
    cands = {}
    for fn, parsed in robjs.items():
        if not parsed: continue
        for r in parsed['custom']: cands[r['new']] = (fn, r)
        for r in parsed['original']:
            if any(f in ('dfil', 'bfil') for f, _, _ in r['mods']): cands[r['old']] = (fn, r)
    if types: cands = {t: v for t, v in cands.items() if t in set(types.split(','))}
    else:
        # skip types this map already defines the same way (same id, same fields)
        here = {}
        for fn in objs:
            for r in objs[fn]['custom']: here[r['new']] = r['mods']
            for r in objs[fn]['original']: here[r['old']] = r['mods']
        def model_of(mods): return next((v for f, _, v in mods if f in ('dfil', 'bfil')), None)
        cands = {t: v for t, v in cands.items() if not (t in here and model_of(v[1]['mods']) == model_of(here[t]))}
    placed = {}
    for e in src['entries']:
        if e['type'] in cands: placed.setdefault(e['type'], []).append(e)
    if near:
        cx, cy, rr = [float(v) for v in near.split(',')]
        placed = {t: [e for e in es if math.hypot(e['x'] - cx, e['y'] - cy) <= rr] for t, es in placed.items()}
        placed = {t: es for t, es in placed.items() if es}
    if not placed: print('Нет размещений подходящих типов.'); return
    used = {e['type'] for e in cur['entries']} | {r['new'] for fn in objs for r in objs[fn]['custom'] if r['new']}
    def fresh(prefix):
        for i in range(36 * 36):
            cand = prefix + 'H' + '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i // 36] + '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i % 36]
            if cand not in used: used.add(cand); return cand
        workshop.die('нет свободных кодов')
    plan = []; files = {}
    for t, es in sorted(placed.items(), key=lambda kv: -len(kv[1])):
        fn, r = cands[t]
        new_id = fresh('D' if fn.endswith('w3d') else 'B')
        base = r['old']
        model = next((v for f, _, v in r['mods'] if f in ('dfil', 'bfil')), None)
        status = 'стандартная модель'
        if model:
            path = model.replace('/', '\\')
            stem = path[:-4] if path.lower().endswith(('.mdl', '.mdx')) else path
            hq = _hq_file(a_root, stem + '.mdx')
            if rm.has(stem + '.mdx'): files[stem + '.mdx'] = rm.read(stem + '.mdx'); status = 'модель из эталонной карты'
            elif hq is not None:
                files[stem + '.mdx'] = hq.read_bytes(); status = f'HQ-модель {hq.name}'
                for tex in mdx_textures(hq.read_bytes()):
                    tp = tex.replace('/', '\\')
                    if w.mpq.has(tp) or tp in files: continue
                    for c in (a_root / tp.replace('\\', '/'), hq.parent / tp.split('\\')[-1], workshop.GAME / tp.replace('\\', '/')):
                        if c.is_file(): files[tp] = c.read_bytes(); break
                    else: status += f'; текстура {tex} не найдена'
            elif w.mpq.has(stem + '.mdx') or w.mpq.has(stem + '.mdl'): status = 'модель уже в карте'
            else: status = f'модель {model}: файла нет ни в карте, ни в HQ (будет стандартная)'
        plan.append((t, new_id, fn, r, es, status))
        print(f'  {t} (база {base}) -> {new_id}: {len(es)} шт., {status}')
    print(f'Файлов в карту: {len(files)}')
    if not apply: print('\nПлан. Запустите с --apply.'); return
    first_id = max((e['editor_id'] for e in cur['entries']), default=0) + 1; nid = first_id; new_types = []
    for t, new_id, fn, r, es, _ in plan:
        rec = {'old': r['old'], 'new': new_id, 'mods': list(r['mods'])}
        objs[fn]['custom'].append(rec); new_types.append(new_id)
        conv = []
        for e in es:
            c = dict(e); c['type'] = new_id; conv.append(c)
        nid += doo.append(cur, conv, nid)
    w.changes['war3map.doo'] = doo.serialize(cur)
    for fn in objs: w.changes[fn] = map_audit.serialize_obj_file(objs[fn])
    w.changes.update(files); w.commit()
    w.state.setdefault('custom_doodads_added', []).append({'ref': ref_path.name, 'new_types': new_types, 'editor_ids': [first_id, nid - 1], 'applied': __import__('time').strftime('%Y-%m-%d %H:%M:%S')})
    w.save_state()
    print(f'Добавлено типов {len(new_types)}, размещений {nid - first_id}, файлов {len(files)}. Откат: map_fix.py custom-doodads --undo --apply')

def terrain_z(w: workshop.Workshop):
    """Return f(x, y) -> ground height from war3map.w3e."""
    import struct
    b = w.mpq.read('war3map.w3e'); o = 13
    ng = struct.unpack_from('<I', b, o)[0]; o += 4 + ng * 4
    nc = struct.unpack_from('<I', b, o)[0]; o += 4 + nc * 4
    width, height = struct.unpack_from('<II', b, o); o += 8
    ox, oy = struct.unpack_from('<ff', b, o); o += 8
    cells = b[o:]
    def f(x, y):
        i = min(max(int(round((x - ox) / 128)), 0), width - 1); j = min(max(int(round((y - oy) / 128)), 0), height - 1)
        c = cells[(j * width + i) * 7:(j * width + i) * 7 + 7]
        return (struct.unpack_from('<h', c)[0] - 8192) / 4 + ((c[6] & 0xF) - 2) * 128
    return f

def fix_move_doodads(w: workshop.Workshop, apply: bool, types: str | None = None, frm: str | None = None, to: str | None = None, rotate: float = 0.0):
    """Move (and optionally rotate) every placement of the given doodad types: the point
    --from is carried to --to, the rest of the group keeps its shape. Heights follow the
    terrain at the new spot.

    --types A,B     doodad type ids to move (required)
    --from=X,Y      reference point (default: centre of the group)
    --to=X,Y        where the reference point goes (required)
    --rotate DEG    turn the group around the reference point (counter-clockwise)"""
    import doo, math
    if not types or not to: workshop.die('нужны --types и --to=X,Y')
    kinds = set(types.split(','))
    cur = doo.parse(w.mpq.read('war3map.doo'))
    group = [e for e in cur['entries'] if e['type'] in kinds]
    if not group: workshop.die('таких размещений нет')
    tx, ty = [float(v) for v in to.split(',')]
    if frm: fx, fy = [float(v) for v in frm.split(',')]
    else: fx = sum(e['x'] for e in group) / len(group); fy = sum(e['y'] for e in group) / len(group)
    tz = terrain_z(w); rad = math.radians(rotate); ca, sa = math.cos(rad), math.sin(rad)
    print(f'Размещений: {len(group)}; опорная точка ({fx:g}, {fy:g}) -> ({tx:g}, {ty:g}), поворот {rotate:g}°')
    for e in group:
        dx, dy = e['x'] - fx, e['y'] - fy
        nx = tx + dx * ca - dy * sa; ny = ty + dx * sa + dy * ca
        nz = e['z'] - tz(e['x'], e['y']) + tz(nx, ny)
        print(f"  {e['type']} ({e['x']:.0f}, {e['y']:.0f}, z {e['z']:.0f}, {math.degrees(e['angle']):.0f}°) -> ({nx:.0f}, {ny:.0f}, z {nz:.0f}, {(math.degrees(e['angle']) + rotate) % 360:.0f}°)")
        if apply: e['x'], e['y'], e['z'] = nx, ny, nz; e['angle'] = (e['angle'] + rad) % (2 * math.pi)
    if not apply: print('\nПлан. Запустите с --apply.'); return
    w.changes['war3map.doo'] = doo.serialize(cur); w.commit(); print('Перемещено.')

def fix_doodads_z(w: workshop.Workshop, apply: bool, ref: str | None = None, types: str | None = None, offset: float = 0.0):
    """Put ported placements on this map's ground: z = ground_here(x, y) + (z_ref -
    ground_ref) + offset, where z_ref is the same placement in the reference map (0 when
    it has none, e.g. after move-doodads). Idempotent: run it as often as you like.

    --types A,B     only these types (default: every placement recorded by doodads /
                    custom-doodads in the state file)
    --offset N      extra height in game units (sunk models: try 100..200)"""
    import doo, math
    from mpq import MPQ
    ref_path = _ref_map(ref)
    if ref_path is None: workshop.die('эталонная карта не найдена, укажите --ref')
    class _R: pass
    r = _R(); r.mpq = MPQ(ref_path)
    tz_ref = terrain_z(r); tz_here = terrain_z(w)
    src = doo.parse(r.mpq.read('war3map.doo'))
    by_xy = {}
    for e in src['entries']: by_xy.setdefault((round(e['x']), round(e['y'])), []).append(e)
    cur = doo.parse(w.mpq.read('war3map.doo'))
    if types:
        kinds = set(types.split(',')); victims = [e for e in cur['entries'] if e['type'] in kinds]
    else:
        ids = set()
        for rec in w.state.get('doodads_added', []) + w.state.get('custom_doodads_added', []):
            ids.update(range(rec['editor_ids'][0], rec['editor_ids'][1] + 1))
        victims = [e for e in cur['entries'] if e['editor_id'] in ids]
    changed = 0; by_type = {}
    for e in victims:
        rel = 0.0
        for s_ in by_xy.get((round(e['x']), round(e['y'])), []):
            rel = s_['z'] - tz_ref(s_['x'], s_['y']); break
        nz = tz_here(e['x'], e['y']) + rel + offset
        if abs(nz - e['z']) < 0.5: continue
        by_type.setdefault(e['type'], []).append((e['z'], nz))
        if apply: e['z'] = nz
        changed += 1
    for t, v in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        print(f'  {t}: {len(v)} шт., сдвиг по z ' + ', '.join(sorted({f"{b - a:+.0f}" for a, b in v})))
    print(f'Размещений проверено {len(victims)}, требуют поправки {changed}.')
    if not changed: return
    if not apply: print('\nПлан. Запустите с --apply.'); return
    w.changes['war3map.doo'] = doo.serialize(cur); w.commit(); print('Высоты пересчитаны.')

def fix_dump(w: workshop.Workshop, apply: bool):
    """Write the map's structural files (placements, object types, terrain, script,
    file list, unit/item data) into .work/<map>/dump.zip for sharing without models."""
    import zipfile
    names = ['war3map.doo', 'war3mapUnits.doo', 'war3map.w3d', 'war3map.w3b', 'war3map.w3u', 'war3map.w3e', 'war3map.w3i',
             'war3map.j', 'Scripts\\war3map.j', 'war3map.w3r', 'war3map.wpm', 'war3map.shd', 'war3map.mmp', '(listfile)']
    names += [f for f in w.mpq.list() if f.lower().startswith('units\\') and f.lower().endswith(('.slk', '.txt'))]
    out = workshop.WORK / 'dump.zip'; out.parent.mkdir(parents=True, exist_ok=True)
    listing = '\n'.join(f'{f}\t{len(w.mpq.read(f))}' for f in w.mpq.list())
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('FILES.tsv', listing)
        z.writestr('state.json', __import__('json').dumps(w.state, ensure_ascii=False, indent=1))
        for n in names:
            if w.mpq.has(n): z.writestr(n.replace('\\', '/'), w.mpq.read(n))
    print(f'Записано: {out} ({out.stat().st_size / 1e6:.1f} МБ)')

def fix_remove(w: workshop.Workshop, apply: bool, ids: str | None = None, undo: bool = False):
    """Remove single placements by editor id (numbers printed by probe). Removed
    entries are kept in the state file; --undo puts them back.

    --ids 5254,5244   editor ids to remove
    --undo            restore everything removed by this command"""
    import doo
    cur = doo.parse(w.mpq.read('war3map.doo'))
    if undo:
        saved = w.state.get('removed_placements', [])
        if not saved: workshop.die('нечего восстанавливать')
        print(f'Восстановить {len(saved)} размещений: ' + ', '.join(f"{e['type']} {e['editor_id']}" for e in saved))
        if not apply: print('\nПлан. Запустите с --apply.'); return
        have = {e['editor_id'] for e in cur['entries']}
        cur['entries'].extend(e for e in saved if e['editor_id'] not in have)
        w.changes['war3map.doo'] = doo.serialize(cur); w.commit(); w.state['removed_placements'] = []; w.save_state(); print('Готово.'); return
    if not ids: workshop.die('нужен --ids 1,2,3')
    want = {int(v) for v in ids.split(',')}
    victims = [e for e in cur['entries'] if e['editor_id'] in want]
    for e in victims: print(f"  {e['type']} {e['editor_id']} ({e['x']:.0f}, {e['y']:.0f})")
    missing = want - {e['editor_id'] for e in victims}
    if missing: print(f'  нет таких номеров: {sorted(missing)}')
    if not victims: return
    if not apply: print(f'\nПлан: удалить {len(victims)}. Запустите с --apply.'); return
    cur['entries'] = [e for e in cur['entries'] if e['editor_id'] not in want]
    w.changes['war3map.doo'] = doo.serialize(cur); w.commit()
    w.state.setdefault('removed_placements', []).extend(victims); w.save_state()
    print(f'Удалено {len(victims)}. Вернуть: map_fix.py remove --undo --apply')

def fix_hq_doodads(w: workshop.Workshop, apply: bool, into: str = 'map', match: str | None = None, folders: str = 'Doodads', textures: bool = False, models: bool = False):
    r"""Bring the HQ replacements of standard doodads (WC3DotaHQTest\A\Doodads\...) into
    the map at their standard paths, so the map shows them without a root overlay.

    --into map|root   write into the map archive (default) or copy next to the game
    --match text      only paths containing text (e.g. Fence, Stairs, Northrend)
    --folders A,B     top folders under WC3DotaHQTest\A to take (default Doodads)
    --textures        print the textures each model references and where they are
    --models          check each model (MDX version, geosets) and each texture's format
                      as the game will find it (map first, then disk)"""
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
    if models:
        print('Модели и текстуры (как их найдёт игра: сначала карта, потом диск):')
        for rel, p in sorted(files.values()):
            if p.suffix.lower() != '.mdx': continue
            data = w.mpq.read(rel) if w.mpq.has(rel) else p.read_bytes()
            mi = mdx_info(data)
            where = 'в карте' if w.mpq.has(rel) else 'только на диске'
            flag = '' if mi['ok'] and mi['geosets'] else '  ПУСТАЯ/БИТАЯ МОДЕЛЬ'
            print(f'  {rel}  [{where}] MDX v{mi["version"]}, геосетов {mi["geosets"]}, анимаций {mi["sequences"]}, {mi["size"]} байт{flag}')
            for rid, tex in mi['textures']:
                if rid: print(f'      текстура: team/replaceable {rid}'); continue
                t = tex.replace('/', '\\')
                if w.mpq.has(t): print(f'      {tex}  [в карте] {blp_info(w.mpq.read(t))}')
                elif w.disk(t).is_file(): print(f'      {tex}  [на диске] {blp_info(w.disk(t).read_bytes())}')
                else: print(f'      {tex}  [НЕ НАЙДЕНА -> модель будет белой]')
        return
    if textures:
        print('Текстуры моделей:')
        for rel, p in sorted(files.values()):
            if p.suffix.lower() != '.mdx': continue
            for tex in mdx_textures(p.read_bytes()):
                t = tex.replace('/', '\\')
                st = 'в карте' if w.mpq.has(t) else 'на диске' if w.disk(t).is_file() else 'будет добавлена' if t.lower() in extra or t.lower() in files else 'НЕТ НИГДЕ'
                print(f'  {rel}  ->  {tex}  [{st}]')
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

def fix_cooldown_numbers(w: workshop.Workshop, apply: bool, undo: bool = False, font: float = 0.016, parent: str = 'gameui', debug: bool = False):
    """Numeric cooldown counters over the command buttons (JASS block in war3map.j).

    --undo            remove the block again
    --font 0.016      text height (fraction of screen height)
    --parent gameui   text frames belong to the game UI (default) or to the command
                      buttons (--parent button)
    --debug           show slot numbers 0..11 on every button and a status line at
                      the top of the screen (selected unit, abilities found, cooldowns)"""
    import cooldown_jass
    script = w.script
    ids = []; positions = {}
    uab, uh, urows = w.unit_abils
    for hc in w.hero_like():
        for f in ('heroAbilList', 'abilList'):
            for c in uab.get((uh[f], urows[hc]), '').split(','):
                c = c.strip()
                if c and c not in ids and c not in ('AInv', 'A0NR'):
                    ids.append(c)
                    xy = w.xy(c, 'Buttonpos')
                    if xy and 0 <= xy[0] <= 3 and 0 <= xy[1] <= 2: positions[c] = xy[1] * 4 + xy[0]
    # Abilities given to heroes by triggers (Beastmaster's hawk/boar, Invoker's spells...)
    # are not in the unit lists: add every ability of the map that has a cooldown and a
    # command-card position.
    data, ah, arows = w.abil_data
    cool = [c for c in ah if re.match(r'Cool\d+$', c)]
    for code, r in arows.items():
        if code in ids or not re.match(r'^[0-9A-Za-z]{4}$', code): continue
        cd = 0.0
        for col in cool:
            try: cd = max(cd, float(data.get((ah[col], r), '0') or 0))
            except ValueError: pass
        if cd <= 0: continue
        xy = w.xy(code, 'Buttonpos')
        if xy and 0 <= xy[0] <= 3 and 0 <= xy[1] <= 2:
            ids.append(code); positions[code] = xy[1] * 4 + xy[0]
    # Parked: Invoker's invoked spells share one data slot and the game shuffles them
    # at runtime; numbers landed in the wrong cell. Skip them until a better rule exists.
    skip_names = re.compile(r'^(cold snap|ghost walk|tornado|emp|alacrity|chaos meteor|sun strike|forge spirit|ice wall|deafening blast)', re.I)
    parked = [c for c in ids if positions.get(c) == 5 and skip_names.match(w.name(c, 'AbilityFunc') or '')]
    ids = [c for c in ids if c not in parked]
    for c in parked: positions.pop(c, None)
    new = cooldown_jass.remove(script) if undo else cooldown_jass.inject(script, ids, font, positions, parent, debug)
    if not undo:
        print(f'Способностей в списке для опроса: {len(ids)}, с известной позицией кнопки: {len(positions)}; пропущено (Инвокер): {len(parked)}')
        print(f'Родитель текста: {parent}; отладка: {"вкл" if debug else "выкл"}')
    present = 'HW_COOLDOWN_BEGIN' in script
    print(f'Сейчас блок {"есть" if present else "отсутствует"}; после: {"удалён" if undo else "добавлен"} ({len(new) - len(script):+d} байт).')
    if not apply: print('План. Запустите с --apply.'); return
    w.script = new; w.changes['war3map.j'] = new.encode('latin1', 'replace'); w.commit()
    print('Записано. Откат: map_fix.py cooldown-numbers --undo --apply')

FIXES = {'shops': fix_shops, 'doodads': fix_doodads, 'hq-doodads': fix_hq_doodads, 'cooldown-numbers': fix_cooldown_numbers, 'probe': probe, 'static-models': fix_static_models, 'repack-textures': fix_repack_textures, 'custom-doodads': fix_custom_doodads, 'move-doodads': fix_move_doodads, 'doodads-z': fix_doodads_z, 'dump': fix_dump, 'remove': fix_remove}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fix', choices=list(FIXES) + ['list'])
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--ref', help='эталонная карта для doodads')
    ap.add_argument('--types', help='список типов декораций через запятую для doodads')
    ap.add_argument('--near', help='doodads: X,Y,R — только размещения в радиусе R от точки')
    ap.add_argument('--from', help='move-doodads: X,Y опорная точка (писать через =)')
    ap.add_argument('--to', help='move-doodads: X,Y куда (писать через =)')
    ap.add_argument('--ids', help='remove: номера размещений через запятую')
    ap.add_argument('--offset', type=float, default=0.0, help='doodads-z: добавка к высоте')
    ap.add_argument('--rotate', type=float, default=0.0, help='move-doodads: поворот группы в градусах')
    ap.add_argument('--at', help='probe: X,Y,R — точка и радиус')
    ap.add_argument('--opaque', action='store_true', help='repack-textures: убрать альфа-канал')
    ap.add_argument('--models', action='store_true', help='hq-doodads: проверить каждую модель и её текстуры')
    ap.add_argument('--undo', action='store_true', help='doodads: удалить ранее добавленные размещения')
    ap.add_argument('--into', choices=['map', 'root'], default='map', help='hq-doodads: куда класть файлы')
    ap.add_argument('--font', type=float, default=0.016, help='cooldown-numbers: высота шрифта')
    ap.add_argument('--parent', choices=['gameui', 'button'], default='gameui', help='cooldown-numbers: к чему крепить текст')
    ap.add_argument('--debug', action='store_true', help='cooldown-numbers: отладочный режим (номера ячеек и строка состояния)')
    ap.add_argument('--textures', action='store_true', help='hq-doodads: показать текстуры каждой модели и их статус')
    ap.add_argument('--match', help='hq-doodads: только пути, содержащие текст')
    ap.add_argument('--folders', default='Doodads', help='hq-doodads: папки под WC3DotaHQTest\\A через запятую')
    a = ap.parse_args()
    if a.fix == 'list':
        for k, f in FIXES.items(): print(f'{k:10s} {f.__doc__.strip().splitlines()[0]}')
        return
    w = workshop.Workshop()
    if a.fix == 'doodads' and a.undo: undo_doodads(w, a.apply, a.types)
    elif a.fix == 'doodads': FIXES[a.fix](w, a.apply, a.ref, a.types, a.near)
    elif a.fix == 'probe': FIXES[a.fix](w, a.apply, a.at, a.ref)
    elif a.fix == 'remove': FIXES[a.fix](w, a.apply, a.ids, a.undo)
    elif a.fix == 'doodads-z': FIXES[a.fix](w, a.apply, a.ref, a.types, a.offset)
    elif a.fix == 'move-doodads': FIXES[a.fix](w, a.apply, a.types, getattr(a, 'from'), a.to, a.rotate)
    elif a.fix == 'custom-doodads': FIXES[a.fix](w, a.apply, a.ref, a.types, a.near, a.undo)
    elif a.fix == 'static-models': FIXES[a.fix](w, a.apply, a.match, a.undo)
    elif a.fix == 'repack-textures': FIXES[a.fix](w, a.apply, a.match, a.folders, a.opaque)
    elif a.fix == 'hq-doodads': FIXES[a.fix](w, a.apply, a.into, a.match, a.folders, a.textures, a.models)
    elif a.fix == 'cooldown-numbers': FIXES[a.fix](w, a.apply, a.undo, a.font, a.parent, a.debug)
    else: FIXES[a.fix](w, a.apply)

if __name__ == '__main__':
    main()
