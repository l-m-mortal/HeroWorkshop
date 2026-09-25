#!/usr/bin/env python3
"""Convert a PNG icon to classic paletted BLP1, without touching the source PNG."""
from __future__ import annotations
import struct, sys
from pathlib import Path
from PIL import Image

def main(src: str, dst: str) -> None:
    image=Image.open(src).convert('RGBA').resize((64,64), Image.Resampling.LANCZOS)
    # Warcraft III command-button BLPs are paletted. Quantization retains the
    # opaque UI art well and avoids relying on external macOS converters.
    indexed=image.convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    # Pillow may return only the palette entries that are actually used. BLP1
    # always reserves all 256 entries, so pad sparse palettes before encoding.
    palette=(indexed.getpalette() or [])[:768]
    palette += [0] * (768-len(palette))
    offsets=[0]*16; sizes=[0]*16; mips=[]; cursor=156+1024
    current=indexed
    for level in range(7):
        raw=current.tobytes(); offsets[level]=cursor; sizes[level]=len(raw); cursor+=len(raw); mips.append(raw)
        if current.width==1: break
        current=current.resize((max(1,current.width//2),max(1,current.height//2)),Image.Resampling.LANCZOS)
    bgra=bytearray()
    for i in range(256):
        r,g,b=palette[i*3:i*3+3]; bgra.extend((b,g,r,255))
    header=b'BLP1'+struct.pack('<6I',1,0,64,64,5,1)+struct.pack('<16I',*offsets)+struct.pack('<16I',*sizes)
    Path(dst).write_bytes(header+bgra+b''.join(mips))
if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit('usage: png_to_blp.py input.png output.blp')
    main(sys.argv[1],sys.argv[2])
