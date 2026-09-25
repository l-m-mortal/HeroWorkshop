#!/usr/bin/env python3
"""Build HeroWorkshop_inventory/ for the cloud session.

Read-only: walks the Warcraft III root and writes text/JSON reports.
Outputs (all inside --out):
  FILES_ALL.tsv      every file under the game root (rel path, size, mtime, ext)
  FILES_ALL.json     same data as a list of records
  DIRS.tsv           every directory with file count and byte size (recursive)
  TREE.md            per top-level folder: subfolder structure to depth 4 + full lists for small roots
  REFERENCES.md      resolution of map_external_refs.txt / map_other_missing_refs.txt
  ICONS_DOTA2.md     icon folders, naming scheme, image sizes
  HUD.md             HUD files (UI\\Console, UI\\Widgets, UI\\Cursor, ...) with sizes and source set
"""
from __future__ import annotations
import argparse, io, json, os, struct, sys, time
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

try:
    from PIL import Image
except ImportError:
    Image = None

SKIP_NAMES = {'.DS_Store'}
SKIP_DIR_NAMES = {'.git', '__pycache__', '.venv', '.build', '__MACOSX'}
IMAGE_EXT = {'.blp', '.tga', '.png', '.jpg', '.jpeg', '.dds'}


def human(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return str(n)


def walk(root: Path, follow_symlinks=False):
    """Yield (rel_posix, abs_path, size, mtime) for every regular file. Skips AppleDouble and junk."""
    skipped_dirs = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        keep = []
        for d in sorted(dirnames):
            if d in SKIP_DIR_NAMES or d.startswith('._'):
                skipped_dirs.append(os.path.relpath(os.path.join(dirpath, d), root))
                continue
            full = os.path.join(dirpath, d)
            if os.path.islink(full):
                skipped_dirs.append(os.path.relpath(full, root) + ' -> ' + os.readlink(full))
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            if fn.startswith('._') or fn in SKIP_NAMES:
                continue
            p = Path(dirpath) / fn
            try:
                st = p.lstat()
            except OSError:
                continue
            if not os.path.isfile(p):
                continue
            rel = p.relative_to(root).as_posix()
            yield rel, p, st.st_size, st.st_mtime
    walk.skipped_dirs = skipped_dirs


def blp_info(data: bytes):
    if data[:4] == b'BLP1' and len(data) >= 28:
        comp, alpha, w, h = struct.unpack_from('<IIII', data, 4)
        return {'fmt': 'BLP1-' + ('jpeg' if comp == 0 else 'palette'), 'w': w, 'h': h, 'alpha': alpha}
    if data[:4] == b'BLP2' and len(data) >= 20:
        w, h = struct.unpack_from('<II', data, 12)
        return {'fmt': 'BLP2', 'w': w, 'h': h}
    return None


def image_dims(p: Path):
    ext = p.suffix.lower()
    try:
        if ext == '.blp':
            with open(p, 'rb') as f:
                return blp_info(f.read(32))
        if Image is not None and ext in IMAGE_EXT:
            with Image.open(p) as im:
                return {'fmt': im.format or ext[1:].upper(), 'w': im.size[0], 'h': im.size[1]}
    except Exception:
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, help='Warcraft III folder')
    ap.add_argument('--out', required=True)
    ap.add_argument('--refs', default=None, help='map_external_refs.txt')
    ap.add_argument('--other-refs', default=None, help='map_other_missing_refs.txt')
    ap.add_argument('--small-root-limit', type=int, default=300)
    ap.add_argument('--tree-depth', type=int, default=4)
    a = ap.parse_args()

    root = Path(a.root).resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---------- full listing ----------
    files = []  # (rel, size, mtime, ext)
    for rel, p, size, mtime in walk(root):
        files.append((rel, size, mtime, p.suffix.lower()))
    skipped_dirs = walk.skipped_dirs
    print(f'listed {len(files)} files in {time.time()-t0:.0f}s', file=sys.stderr)

    with open(out / 'FILES_ALL.tsv', 'w', encoding='utf-8') as f:
        f.write(f'# root={root}\n# columns: path (relative to root, / separator)\tsize_bytes\tmtime_iso\text\n')
        for rel, size, mtime, ext in files:
            f.write(f'{rel}\t{size}\t{time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mtime))}\t{ext}\n')
    with open(out / 'FILES_ALL.json', 'w', encoding='utf-8') as f:
        json.dump({'root': str(root), 'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'count': len(files), 'skipped_dirs': skipped_dirs,
                   'files': [{'path': r, 'size': s, 'mtime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(m)), 'ext': e}
                             for r, s, m, e in files]}, f, ensure_ascii=False)

    # ---------- directory aggregates ----------
    dir_count = Counter(); dir_size = Counter(); dir_ext = defaultdict(Counter); dir_direct = Counter()
    for rel, size, mtime, ext in files:
        parts = rel.split('/')
        dir_direct['/'.join(parts[:-1]) or '.'] += 1
        for i in range(len(parts)):
            d = '/'.join(parts[:i]) or '.'
            dir_count[d] += 1; dir_size[d] += size; dir_ext[d][ext or '(none)'] += 1
    with open(out / 'DIRS.tsv', 'w', encoding='utf-8') as f:
        f.write('# dir (relative, "." = root)\tfiles_recursive\tbytes_recursive\tfiles_direct\ttop_extensions\n')
        for d in sorted(dir_count):
            exts = ', '.join(f'{e}:{n}' for e, n in dir_ext[d].most_common(8))
            f.write(f'{d}\t{dir_count[d]}\t{dir_size[d]}\t{dir_direct[d]}\t{exts}\n')

    # ---------- TREE.md ----------
    lines = [f'# TREE: {root}', '', f'Generated {time.strftime("%Y-%m-%d %H:%M")}. Total files: {len(files)}, total size: {human(dir_size["."])}.',
             'Excluded from every listing: AppleDouble `._*` files, `.DS_Store`, and contents of `.git`, `__pycache__`, `.venv`, `.build`.',
             'Symlinked directories are listed but not traversed (their targets are listed at the target location).', '',
             '## Skipped / symlinked directories', '']
    for d in skipped_dirs:
        lines.append(f'- `{d}`')
    lines += ['', '## Root files', '']
    for rel, size, mtime, ext in files:
        if '/' not in rel:
            lines.append(f'- `{rel}` ({human(size)})')
    top = sorted({rel.split('/')[0] for rel, *_ in files if '/' in rel})
    lines += ['', '## Top-level folders', '', '| folder | files | size | top extensions |', '|---|---:|---:|---|']
    for t in top:
        lines.append(f'| `{t}` | {dir_count[t]} | {human(dir_size[t])} | {", ".join(f"{e}:{n}" for e, n in dir_ext[t].most_common(6))} |')
    for t in top:
        lines += ['', f'## {t}', '', f'Files: {dir_count[t]}, size: {human(dir_size[t])}', '']
        if dir_count[t] <= a.small_root_limit:
            lines.append('Full file list:'); lines.append('')
            for rel, size, mtime, ext in files:
                if rel.startswith(t + '/'):
                    lines.append(f'- `{rel}` ({human(size)})')
        else:
            lines.append(f'Subfolder structure to depth {a.tree_depth} (files recursive / size / extensions):'); lines.append('')
            subs = sorted(d for d in dir_count if d.startswith(t + '/') and d.count('/') <= a.tree_depth)
            for d in subs:
                depth = d.count('/')
                exts = ', '.join(f'{e}:{n}' for e, n in dir_ext[d].most_common(6))
                lines.append(f'{"  " * (depth - 1)}- `{d.split("/")[-1]}/` — {dir_count[d]} files, {human(dir_size[d])} [{exts}]')
            lines.append(''); lines.append(f'Complete file list for `{t}` is in `FILES_ALL.tsv` (filter by prefix `{t}/`).')
    (out / 'TREE.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # ---------- REFERENCES.md ----------
    index = defaultdict(list)  # lowercase stem without ext -> [(rel, size)]
    index_full = {}            # lowercase full rel path -> (rel, size)
    for rel, size, mtime, ext in files:
        low = rel.lower()
        index_full[low] = (rel, size)
        stem = low[:-len(ext)] if ext else low
        index[stem].append((rel, size))

    by_base = defaultdict(list)  # lowercase basename stem -> [(rel_lower_stem, rel, size)]
    for rel, size, mtime, ext in files:
        low = rel.lower(); stem = low[:-len(ext)] if ext else low
        by_base[stem.rsplit('/', 1)[-1]].append((stem, rel, size))

    def strip_ext(r):
        for e in ('.mdx', '.mdl', '.blp', '.tga', '.dds', '.png', '.jpg', '.wav', '.mp3', '.slk', '.txt', '.fdf', '.toc'):
            if r.endswith(e):
                return r[:-len(e)]
        return r

    def resolve(ref: str, allowed_prefixes=None):
        """Return (direct_hits, suffix_hits). direct = exact path from game root (what the game loads);
        suffix = same relative path found deeper inside an allowed folder (candidate for mapping)."""
        r = ref.strip().replace('\\', '/').strip('/').lower()
        if not r:
            return [], []
        stem = strip_ext(r)
        direct = []
        if r in index_full:
            direct.append(index_full[r])
        for cand in index.get(stem, []):
            if cand not in direct:
                direct.append(cand)
        suffix = []
        if allowed_prefixes:
            base = stem.rsplit('/', 1)[-1]
            for cstem, rel, size in by_base.get(base, []):
                if cstem == stem:
                    continue
                if cstem.endswith('/' + stem) and any(rel.lower().startswith(p.lower() + '/') for p in allowed_prefixes):
                    suffix.append((rel, size))
        return direct, suffix

    def ref_report(title, path, allowed_prefixes=None):
        refs = [l.rstrip('\n') for l in open(path, encoding='utf-8', errors='replace') if l.strip() and not l.startswith('#')]
        rows = []; found = 0; missing_groups = Counter(); missing_list = []
        for ref in refs:
            direct, suffix = resolve(ref, allowed_prefixes)
            if direct or suffix:
                found += 1
                cells = []
                if direct:
                    cells.append('root: ' + ' ; '.join(f'`{h[0]}` ({human(h[1])})' for h in direct[:3]))
                if suffix:
                    cells.append('inside mod folders: ' + ' ; '.join(f'`{h[0]}` ({human(h[1])})' for h in suffix[:3]) + (f' +{len(suffix)-3} more' if len(suffix) > 3 else ''))
                rows.append((ref, '<br>'.join(cells)))
            else:
                parts = ref.replace('\\', '/').split('/')
                missing_groups['/'.join(parts[:2])] += 1
                missing_list.append(ref)
                rows.append((ref, '**НЕ НАЙДЕН**'))
        sec = [f'## {title}', '', f'Source: `{Path(path).name}`, {len(refs)} refs. Found: {found}. Missing: {len(refs)-found}.',
               'Lookup is case-insensitive, `\\` = `/`, extension-less refs match any of .mdx/.mdl/.blp/.tga/.dds/.png. Paths shown relative to the Warcraft III root.', '',
               '"root:" = exists at that exact path under the Warcraft III root (game loads it directly). "inside mod folders:" = same relative path found deeper inside WC3*Test / Dota Mod Project (candidate, not loaded by the game at that ref).', '',
               '| ref in map | found at |']
        sec.append('|---|---|')
        for ref, res in rows:
            sec.append(f'| `{ref}` | {res} |')
        sec += ['', '### Missing, grouped by first two folders', '']
        for g, n in missing_groups.most_common():
            sec.append(f'- `{g}`: {n}')
        sec += ['', '### Missing list', '', '```'] + missing_list + ['```', '']
        return sec, found, len(refs)

    if a.refs or a.other_refs:
        R = ['# REFERENCES', '', f'Root: `{root}`', '']
        if a.refs:
            sec, f_, n_ = ref_report('map_external_refs.txt (WC3*Test namespaces, searched in whole Warcraft III folder)', a.refs, ['WC3DotaHQTest', 'WC3Dota2Test', 'WC3WardotaTest', 'Dota Mod Project'])
            R += sec
        if a.other_refs:
            sec, f_, n_ = ref_report('map_other_missing_refs.txt (searched only inside WC3DotaHQTest, WC3Dota2Test, WC3WardotaTest, Dota Mod Project)',
                                     a.other_refs, ['WC3DotaHQTest', 'WC3Dota2Test', 'WC3WardotaTest', 'Dota Mod Project'])
            R += sec
        (out / 'REFERENCES.md').write_text('\n'.join(R) + '\n', encoding='utf-8')

    # ---------- ICONS_DOTA2.md ----------
    icon_dirs = Counter()
    for rel, size, mtime, ext in files:
        low = rel.lower()
        if ext in ('.png', '.blp', '.tga') and ('commandbuttons' in low or 'passivebuttons' in low or 'autocastbuttons' in low or 'icon' in low or '/btn' in low or 'disbtn' in low):
            icon_dirs[os.path.dirname(rel)] += 1
    I = ['# ICONS_DOTA2', '', f'Root: `{root}`', '', 'Folders containing icon-like images (CommandButtons / PassiveButtons / AutoCastButtons / *Icon* / BTN*):', '',
         '| folder | icon files | sample | dims |', '|---|---:|---|---|']
    for d, n in sorted(icon_dirs.items(), key=lambda kv: (-kv[1], kv[0]))[:400]:
        sample = next((rel for rel, *_ in files if os.path.dirname(rel) == d and rel.lower().endswith(('.png', '.blp', '.tga'))), '')
        dims = image_dims(root / sample) if sample else None
        dims_s = f'{dims.get("fmt")} {dims.get("w")}x{dims.get("h")}' if dims else ''
        I.append(f'| `{d}` | {n} | `{os.path.basename(sample)}` | {dims_s} |')
    I += ['', f'({len(icon_dirs)} folders total; table truncated to 400 rows if longer. Full per-file data in FILES_ALL.tsv.)', '']
    (out / 'ICONS_DOTA2.md').write_text('\n'.join(I) + '\n', encoding='utf-8')

    # ---------- HUD.md ----------
    hud_keys = ('ui/console', 'ui/widgets', 'ui/cursor', 'ui/feedback', 'ui/minimap', 'ui/glues', 'war3mapskin', 'ui/framedef')
    H = ['# HUD', '', f'Root: `{root}`', '', 'All files whose path contains a HUD location or has .fdf/.toc extension, or is war3mapSkin.txt.', '',
         '| path | size | dims | source set (top folders) |', '|---|---:|---|---|']
    n_h = 0
    for rel, size, mtime, ext in files:
        low = rel.lower()
        if ext in ('.fdf', '.toc') or 'war3mapskin' in low or any(k in low for k in hud_keys):
            n_h += 1
            dims = image_dims(root / rel) if ext in IMAGE_EXT else None
            dims_s = f'{dims.get("fmt")} {dims.get("w")}x{dims.get("h")}' if dims else ''
            src = '/'.join(rel.split('/')[:3])
            H.append(f'| `{rel}` | {human(size)} | {dims_s} | `{src}` |')
    H.insert(4, f'Total HUD-related files: {n_h}.')
    (out / 'HUD.md').write_text('\n'.join(H) + '\n', encoding='utf-8')

    print(f'done in {time.time()-t0:.0f}s -> {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
