#!/usr/bin/env python3
"""Scan local asset folders and build a small, shareable manifest.

The real asset library (models, textures, icons) stays on disk and never
goes to Git. This script walks the folders you point it at and produces:

  <out>/manifest.json   - one record per file: relative path, size, kind,
                          image dimensions, BLP format, sha1
  <out>/thumbs/...      - 64x64 PNG previews for icons, 128px for textures
  <out>.zip             - both of the above in one archive to share

Usage:
  python3 library_scan.py "/Applications/Warcraft III/WC3DotaHQTest" \
                          "/Applications/Warcraft III/WC3Dota2Test" \
                          --out library_manifest

Only PNG thumbnails and JSON leave your disk; MDX and full-size BLP do not.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, shutil, struct, sys, time, zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

IMAGE_EXT = {'.blp', '.tga', '.png', '.jpg', '.jpeg', '.dds'}
MODEL_EXT = {'.mdx', '.mdl'}
SKIP_DIRS = {'.git', '__MACOSX', '.DS_Store'}

def kind_of(rel: str, ext: str) -> str:
    low = rel.lower()
    if ext in MODEL_EXT: return 'model'
    if ext in IMAGE_EXT:
        if 'commandbuttonsdisabled' in low: return 'icon_disabled'
        if 'commandbuttons' in low or 'passivebuttons' in low: return 'icon'
        if low.startswith('ui\\') or '\\ui\\' in low: return 'ui'
        if 'terrainart' in low or 'cliff' in low: return 'terrain'
        if 'portrait' in low: return 'portrait'
        return 'texture'
    if ext in {'.slk', '.txt', '.fdf', '.toc', '.j', '.w3x'}: return 'data'
    if ext in {'.mp3', '.wav', '.flac'}: return 'sound'
    return 'other'

def blp_info(data: bytes):
    if data[:4] == b'BLP1' and len(data) >= 28:
        comp, alpha, w, h = struct.unpack_from('<IIII', data, 4)
        return {'blp': 'jpeg' if comp == 0 else 'palette', 'alpha_bits': alpha, 'width': w, 'height': h}
    if data[:4] == b'BLP2' and len(data) >= 20:
        w, h = struct.unpack_from('<II', data, 12)
        return {'blp': 'blp2', 'width': w, 'height': h}
    return None

def thumbnail(data: bytes, target: Path, size: int) -> bool:
    if Image is None: return False
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert('RGBA')
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            im.save(target, optimize=True)
        return True
    except Exception:
        return False

def scan(roots, out: Path, thumbs: bool, max_thumb_mb: float):
    records = []; thumb_dir = out / 'thumbs'
    total_thumb = 0
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            print(f'SKIP (not a folder): {root}', file=sys.stderr); continue
        label = root.name
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.startswith('._') or fn in SKIP_DIRS: continue
                p = Path(dirpath) / fn
                rel = str(p.relative_to(root)).replace('/', '\\')
                ext = p.suffix.lower()
                try: size = p.stat().st_size
                except OSError: continue
                rec = {'root': label, 'path': rel, 'size': size, 'kind': kind_of(rel, ext)}
                if ext in IMAGE_EXT or size < 4_000_000:
                    try: data = p.read_bytes()
                    except OSError: data = b''
                    rec['sha1'] = hashlib.sha1(data).hexdigest()[:16]
                    if ext == '.blp':
                        info = blp_info(data)
                        if info: rec.update(info)
                    elif ext in IMAGE_EXT and Image is not None:
                        try:
                            with Image.open(io.BytesIO(data)) as im: rec['width'], rec['height'] = im.size
                        except Exception: pass
                    if thumbs and rec['kind'] in {'icon', 'icon_disabled', 'ui', 'terrain', 'portrait', 'texture'} and total_thumb < max_thumb_mb * 1e6:
                        tsize = 64 if rec['kind'].startswith('icon') else 128
                        tpath = thumb_dir / label / (rel.replace('\\', '/') + '.png')
                        if thumbnail(data, tpath, tsize):
                            rec['thumb'] = str(tpath.relative_to(out)); total_thumb += tpath.stat().st_size
                records.append(rec)
        print(f'{label}: {sum(1 for r in records if r["root"] == label)} files', file=sys.stderr)
    manifest = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'roots': [str(Path(r).expanduser().resolve()) for r in roots], 'files': records}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    zpath = out.with_suffix('.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file(): z.write(p, p.relative_to(out.parent))
    by_kind = {}
    for r in records: by_kind[r['kind']] = by_kind.get(r['kind'], 0) + 1
    print('Files by kind:', json.dumps(by_kind, ensure_ascii=False), file=sys.stderr)
    print(f'Manifest: {out / "manifest.json"}\nArchive to share: {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)', file=sys.stderr)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('roots', nargs='+', help='folders to scan (e.g. WC3DotaHQTest, WC3Dota2Test, Icon Audit)')
    ap.add_argument('--out', default='library_manifest', help='output folder name (default: library_manifest)')
    ap.add_argument('--no-thumbs', action='store_true', help='do not render PNG previews')
    ap.add_argument('--max-thumb-mb', type=float, default=150, help='stop rendering previews after this many MB')
    a = ap.parse_args()
    scan(a.roots, Path(a.out).resolve(), not a.no_thumbs, a.max_thumb_mb)

if __name__ == '__main__':
    main()
