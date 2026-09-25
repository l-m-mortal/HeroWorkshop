#!/usr/bin/env python3
"""Research module: how this DotA 6.85 (Warcraft III 1.31) map stocks its shops.

FINDING, in short (see the accompanying research report for the full trace):

  war3map.j contains *no* per-shop item catalog at all.

  - The only native shop-stocking call in the whole script,
    `AddItemToStock`, appears exactly once, inside function `x1v`
    (`function x1v takes integer id returns integer`). It stocks item
    `id` for 50000 gold on a hidden, invisible dummy unit (`xr`,
    unit-type 'nshe', created once near the end of map init and never
    shown), immediately "buys" it back with `lS(xr,id)`, and reads off
    how much gold was actually spent. That is a *price oracle* -- "what
    does item X cost" (per ItemData.slk's goldcost, computed by the
    engine) -- used for hero net-worth and sell-back gold calculations
    (see `x4v`, callers at lines ~12821-12846, ~15484, ~15653, ~15938,
    ~15945, ~21854/21856, ~22799). It has nothing to do with which items
    a real shop offers.

  - The real shop units (`n00X` "Enchanted Artifacts", `n01K` "Weapons
    Dealer", `n00V` "Arcane Sanctum", ... 19 non-hero units in total,
    identified by the `Asid` "Sell Items" ability in UnitAbilities.slk)
    are `CreateUnit`'d at runtime by their bare unit-type code. Their
    stock therefore comes from the native "Sellitems" field on that unit
    type in the object database -- a field that is absent from every
    txt/slk file shipped with this Warcraft III 1.31 install (no
    `Sellitems=`/`sellitems=` key exists anywhere, for any unit, even
    though the sibling `sellunits=` key -- used by Taverns to sell
    heroes -- does exist and is populated). So the real item-to-shop
    assignment lives in game data this research task's file set does not
    expose (this map ships no `war3map.w3u` at all -- confirmed with a
    direct MPQ hash lookup, not just a missing-listfile check -- so unit
    data, including Sellitems, is fully inherited from the base,
    already-DotA-patched game install rather than overridden per-map).

  - No custom "shop panel" data structure (no `BlzCreateFrame`/frame API
    use at all, no per-shop hashtable of item ids, no `SetItemTypeSlots`
    or `RemoveItemFromStock`) exists in war3map.j either. The only
    structured, ordered list of item rawcodes the script *does* contain
    is the item-combine ("recipe") table built by functions such as
    `B6e`/`B7e` (arrays `de`/`ae`/`fe`/`De`/`Fe` indexed by `re`): two
    component items -> one combined result item, optionally restricted
    to a specific hero unit `De[re]`. That is recipe-combining logic
    (right-click "combine" on two carried items), not shop stock, and
    `parse_shops` does not treat it as such.

Given that, `parse_shops` does two honest, script-derived things, and one
clearly-marked exception:

  1. It finds the shop units generically, from `script_text` alone, by
     locating the boolean OR-chains the script itself uses to recognise
     "is this unit one of the shop units" (e.g.
     ``if i=='hC95' or i=='n01K' or i=='nC38' or ... then``, guarded by a
     preceding ``local integer i=GetUnitTypeId(...)`` in the same
     function) -- this is genuinely how the map's own code groups shop
     units together (idle/working animation selection, spawn-team-color
     exceptions, etc.), and is the closest thing to a shop registry that
     exists in the script. Names come from `item_names` (a rawcode->name
     dict; despite the parameter name, the caller is expected to pass a
     combined unit+item name table built from the txt files' Name=/name=
     fields, matching `workshop.Workshop.name()`).

  2. It reports the `AddItemToStock`/`x1v` price-oracle mechanism as
     metadata (`mechanism` key in the return value's synthetic first
     entry) so callers can see it was looked for and what it does.

  3. It does NOT invent per-shop item lists: `items` for a discovered
     shop is populated *only* from `FALLBACK_SHOP_ITEMS` below, which is
     hard-coded, clearly marked, and empty by default (fill in from
     external/known-good sources if you have them -- e.g. an actual
     `war3map.w3u`/object-editor export of the shop units, or public
     documentation of this specific build's shop contents). Entries
     sourced this way carry ``"source": "fallback"``; shops found with no
     fallback data carry ``"source": "script"`` and an empty item list.

Usage:
    python3 shops.py path/to/war3map.j [path/to/txt_dir] > shops.json
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- fallback -
# Hard-coded, clearly marked: NOT derived from war3map.j (no such data exists
# there -- see the module docstring). Keyed by the shop unit rawcode. Order
# matters (the order items would appear in-game, left-to-right/top-to-bottom).
# Left empty on purpose: this research task found no trustworthy source for
# these lists (public wikis / the base game's own UnitData.slk were out of
# scope / unavailable here). Populate if/when such a source is available.
FALLBACK_SHOP_ITEMS: dict[str, list[str]] = {
}


def _functions(script_text: str):
    """Yield (name, start, end, body) for each `function ... endfunction` block."""
    starts = list(re.finditer(r'^function (\w+)\b.*$', script_text, re.M))
    for i, m in enumerate(starts):
        name = m.group(1)
        start = m.end()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(script_text)
        yield name, m.start(), end, script_text[start:end]


_UNITTYPE_VAR_RE = re.compile(r'\blocal\s+integer\s+(\w+)\s*=\s*GetUnitTypeId\(')
_CODE = r"[0-9A-Za-z_]{4}"


def _shop_like_groups(script_text: str):
    """Find every boolean OR-chain of >=3 rawcode comparisons against a
    variable that the enclosing function assigned from GetUnitTypeId(...).
    Returns a list of {'function', 'var', 'codes': [...], 'line'}.
    """
    groups = []
    for fname, fstart, fend, body in _functions(script_text):
        unit_vars = set(_UNITTYPE_VAR_RE.findall(body))
        if not unit_vars:
            continue
        for var in unit_vars:
            chain_re = re.compile(
                rf"\b{re.escape(var)}==\s*'({_CODE})'"
                rf"(?:\s*or\s*{re.escape(var)}==\s*'({_CODE})')*"
            )
            for m in chain_re.finditer(body):
                codes = re.findall(rf"{re.escape(var)}==\s*'({_CODE})'", m.group(0))
                if len(codes) < 3:
                    continue
                line = script_text.count('\n', 0, fstart + m.start()) + 1
                groups.append({'function': fname, 'var': var, 'codes': codes, 'line': line})
    return groups


def _find_price_oracle(script_text: str) -> dict | None:
    """Locate the AddItemToStock/x1v price-oracle function and report it."""
    m = re.search(
        r'function (\w+) takes integer (\w+) returns integer.*?'
        r'call AddItemToStock\((\w+),\s*\2,\s*1,\s*1\)',
        script_text, re.S,
    )
    if not m:
        return None
    line = script_text.count('\n', 0, m.start()) + 1
    return {
        'function': m.group(1),
        'dummy_unit_var': m.group(3),
        'line': line,
        'note': ('Computes an item rawcode\'s gold value by stocking it (qty 1) on a '
                 'hidden dummy unit and immediately buying it back, then diffing gold '
                 'spent. Used for hero net-worth / sell-back calculations elsewhere in '
                 'the script -- it is not a real shop and does not represent any '
                 'shop\'s stock.'),
    }


def parse_shops(script_text: str, item_names: dict) -> list[dict]:
    """Return `[{'shop': code, 'name': ..., 'items': [...], 'source': ...}, ...]`.

    See the module docstring for exactly what is and is not derivable from
    `script_text` alone, and why `items` is only ever populated from the
    clearly-marked `FALLBACK_SHOP_ITEMS` table.
    """
    groups = _shop_like_groups(script_text)

    # Union of codes seen in >=1 shop-like group, in first-seen order,
    # restricted to unit-looking rawcodes (start with a lowercase letter,
    # as every Warcraft III unit rawcode does -- item rawcodes in this map
    # all start with 'I').
    seen = []
    seen_set = set()
    for g in groups:
        for c in g['codes']:
            if c[0] == 'I':
                continue  # an item rawcode caught by the same generic regex elsewhere
            if c not in seen_set:
                seen_set.add(c)
                seen.append(c)

    out = []
    oracle = _find_price_oracle(script_text)
    if oracle is not None:
        out.append({
            'shop': None,
            'name': 'AddItemToStock / x1v price oracle (not a real shop)',
            'items': [],
            'mechanism': oracle,
            'source': 'script',
        })

    for code in seen:
        items = FALLBACK_SHOP_ITEMS.get(code, [])
        out.append({
            'shop': code,
            'name': item_names.get(code, code),
            'items': list(items),
            'source': 'fallback' if items else 'script',
        })
    return out


# --------------------------------------------------------------- CLI glue --
def _load_names_from_txt_dir(txt_dir: Path) -> dict:
    """Rebuild the code->display-name table the way workshop.Txt/Workshop.name
    do, from every *Func.txt / *Strings.txt under txt_dir (Name=/name=)."""
    names: dict[str, str] = {}
    if not txt_dir.is_dir():
        return names
    section_re = re.compile(r'\[(\w{4})\]\s*$')
    name_re = re.compile(r'([A-Za-z0-9_]+)=(.*)$')
    for fp in sorted(txt_dir.glob('*.txt')):
        try:
            text = fp.read_text(encoding='latin1', errors='replace')
        except OSError:
            continue
        cur = None
        for line in text.split('\n'):
            line = line.rstrip('\r')
            m = section_re.match(line)
            if m:
                cur = m.group(1)
                continue
            if cur is None:
                continue
            m = name_re.match(line)
            if m and m.group(1).lower() == 'name' and cur not in names:
                v = m.group(2).split(',')[0].strip().strip('"')
                if v:
                    names[cur] = v
    return names


def main(argv):
    if len(argv) < 2:
        print('usage: shops.py <war3map.j> [txt_dir]', file=sys.stderr)
        return 2
    script_path = Path(argv[1])
    txt_dir = Path(argv[2]) if len(argv) > 2 else script_path.parent / 'txt'
    script_text = script_path.read_text(encoding='latin1', errors='replace')
    item_names = _load_names_from_txt_dir(txt_dir)
    result = parse_shops(script_text, item_names)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
