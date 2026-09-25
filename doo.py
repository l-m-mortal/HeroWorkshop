#!/usr/bin/env python3
"""war3map.doo (doodad and destructable placements): parse and serialize.

Versions 7 (RoC/TFT 1.0x, no item tables) and 8 (TFT, with item tables) are
supported; entries can be converted between them when copying placements
from one map to another."""
from __future__ import annotations
import struct

def parse(b: bytes) -> dict:
    o = 0
    def u32():
        nonlocal o; v = struct.unpack_from('<I', b, o)[0]; o += 4; return v
    def i32():
        nonlocal o; v = struct.unpack_from('<i', b, o)[0]; o += 4; return v
    def f32():
        nonlocal o; v = struct.unpack_from('<f', b, o)[0]; o += 4; return v
    def tag():
        nonlocal o; v = b[o:o + 4].decode('latin1'); o += 4; return v
    if tag() != 'W3do': raise ValueError('not a war3map.doo')
    version, subversion, count = u32(), u32(), u32()
    entries = []
    for _ in range(count):
        e = {'type': tag(), 'variation': u32(), 'x': f32(), 'y': f32(), 'z': f32(), 'angle': f32(),
             'sx': f32(), 'sy': f32(), 'sz': f32()}
        e['flags'] = b[o]; e['life'] = b[o + 1]; o += 2
        if version >= 8:
            e['item_table'] = i32(); sets = []
            for _ in range(u32()):
                s = []
                for _ in range(u32()): s.append((tag(), u32()))
                sets.append(s)
            e['item_sets'] = sets
        e['editor_id'] = u32()
        entries.append(e)
    special = b[o:]
    return {'version': version, 'subversion': subversion, 'entries': entries, 'special': special}

def serialize(d: dict) -> bytes:
    out = bytearray(b'W3do' + struct.pack('<III', d['version'], d['subversion'], len(d['entries'])))
    for e in d['entries']:
        out += e['type'].encode('latin1') + struct.pack('<I7f', e['variation'], e['x'], e['y'], e['z'], e['angle'], e['sx'], e['sy'], e['sz'])
        out += bytes((e['flags'], e['life']))
        if d['version'] >= 8:
            sets = e.get('item_sets', [])
            out += struct.pack('<iI', e.get('item_table', -1), len(sets))
            for s in sets:
                out += struct.pack('<I', len(s))
                for tid, chance in s: out += tid.encode('latin1') + struct.pack('<I', chance)
        out += struct.pack('<I', e['editor_id'])
    out += d['special']
    return bytes(out)

def append(target: dict, entries: list, next_id: int | None = None) -> int:
    """Add placements to a map (editor ids renumbered). Returns how many were added."""
    if next_id is None: next_id = max((e['editor_id'] for e in target['entries']), default=0) + 1
    for src in entries:
        e = dict(src); e['editor_id'] = next_id; next_id += 1
        if target['version'] >= 8:
            e.setdefault('item_table', -1); e.setdefault('item_sets', [])
        target['entries'].append(e)
    return len(entries)
