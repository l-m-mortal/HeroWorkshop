#!/usr/bin/env python3
"""BLP1 helpers: decode any BLP to PIL (via Pillow), encode PIL to paletted
BLP1 with 8-bit alpha and mipmaps, build Warcraft-style disabled icons."""
from __future__ import annotations
import io, struct, sys
from pathlib import Path
from PIL import Image, ImageEnhance

BUTTON = 64

def decode(data: bytes) -> Image.Image:
    """Decode BLP1. Paletted images are decoded here (Pillow ignores their
    separate alpha plane); JPEG BLPs go through Pillow."""
    if data[:4] == b'BLP1' and struct.unpack_from('<I', data, 4)[0] == 1:
        alpha_bits, w, h = struct.unpack_from('<III', data, 8)
        offsets = struct.unpack_from('<16I', data, 28)
        sizes = struct.unpack_from('<16I', data, 92)
        pal = data[156:156 + 1024]
        palette = [(pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4]) for i in range(256)]
        level = data[offsets[0]:offsets[0] + sizes[0]]
        n = w * h
        idx = Image.frombytes('P', (w, h), level[:n])
        flat = []
        for r, g, b in palette: flat += [r, g, b]
        idx.putpalette(flat)
        im = idx.convert('RGB').convert('RGBA')
        if alpha_bits == 8 and len(level) >= 2 * n:
            im.putalpha(Image.frombytes('L', (w, h), level[n:2 * n]))
        elif alpha_bits in (1, 4) and len(level) > n:
            bits = level[n:]
            a = bytearray(n)
            for i in range(n):
                if alpha_bits == 1:
                    a[i] = 255 if (bits[i // 8] >> (i % 8)) & 1 else 0
                else:
                    v = (bits[i // 2] >> (4 * (i % 2))) & 15; a[i] = v * 17
            im.putalpha(Image.frombytes('L', (w, h), bytes(a)))
        return im
    if data[:4] == b'BLP1' and struct.unpack_from('<I', data, 4)[0] == 0:
        return decode_jpeg(data)
    with Image.open(io.BytesIO(data)) as im:
        return im.convert('RGBA')

def decode_jpeg(data: bytes) -> Image.Image:
    """JPEG BLP1: a shared JPEG header plus per-mipmap JPEG bodies, stored as a
    4-channel (CMYK-tagged) JPEG holding B, G, R, A. Pillow's own BLP plugin drops
    the alpha plane; this keeps it."""
    from PIL.JpegImagePlugin import JpegImageFile
    alpha_bits, w, h = struct.unpack_from('<III', data, 8)
    offsets = struct.unpack_from('<16I', data, 28)
    sizes = struct.unpack_from('<16I', data, 92)
    hsize = struct.unpack_from('<I', data, 156)[0]
    jpeg = data[160:160 + hsize] + data[offsets[0]:offsets[0] + sizes[0]]
    im = JpegImageFile(io.BytesIO(jpeg))
    if im.mode == 'CMYK':
        name, extents, offset, args = im.tile[0]
        im.tile = [(name, extents, offset, (args[0], 'CMYK'))]  # raw channels
        from PIL import ImageChops
        b, g, r, a = (ImageChops.invert(ch) for ch in im.split())  # stored inverted (Adobe CMYK style)
    else:
        r, g, b = im.convert('RGB').split(); a = Image.new('L', im.size, 255)
    if alpha_bits == 0: a = Image.new('L', im.size, 255)
    out = Image.merge('RGBA', (r, g, b, a))
    if out.size != (w, h): out = out.resize((w, h))
    return out

def load_image(path) -> Image.Image:
    """Open PNG/BMP/TGA/JPG/BLP as RGBA."""
    path = Path(path)
    if path.suffix.lower() == '.blp':
        return decode(path.read_bytes())
    with Image.open(path) as im:
        return im.convert('RGBA')

def fit_square(im: Image.Image, size: int = BUTTON) -> Image.Image:
    """Center-crop to a square, then resize. Non-square Dota 2 art is cropped."""
    w, h = im.size
    if w != h:
        side = min(w, h)
        left = (w - side) // 2; top = (h - side) // 2
        im = im.crop((left, top, left + side, top + side))
    if im.size != (size, size):
        im = im.resize((size, size), Image.Resampling.LANCZOS)
    return im

def encode(im: Image.Image, mipmaps: bool = True) -> bytes:
    """Paletted BLP1 (compression 1) with 8-bit alpha; any size up to 512."""
    im = im.convert('RGBA')
    w, h = im.size
    rgb = im.convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = (rgb.getpalette() or [])[:768]
    palette += [0] * (768 - len(palette))
    alpha_used = im.getchannel('A').getextrema()[0] < 255
    alpha_bits = 8 if alpha_used else 0
    levels = []
    cur_idx, cur_alpha = rgb, im.getchannel('A')
    while True:
        block = cur_idx.tobytes()
        if alpha_bits: block += cur_alpha.tobytes()
        levels.append(block)
        if not mipmaps or cur_idx.width == 1 and cur_idx.height == 1: break
        nw, nh = max(1, cur_idx.width // 2), max(1, cur_idx.height // 2)
        # Downsample in RGBA space and re-map to the same palette to keep colors stable.
        small = im.resize((nw, nh), Image.Resampling.LANCZOS)
        cur_idx = small.convert('RGB').quantize(palette=rgb, dither=Image.Dither.NONE)
        cur_alpha = small.getchannel('A')
        if len(levels) == 16: break
    offsets = [0] * 16; sizes = [0] * 16
    cursor = 156 + 1024
    for i, block in enumerate(levels):
        offsets[i] = cursor; sizes[i] = len(block); cursor += len(block)
    picture_type = 4 if alpha_bits else 5
    header = b'BLP1' + struct.pack('<6I', 1, alpha_bits, w, h, picture_type, 1 if mipmaps else 0)
    header += struct.pack('<16I', *offsets) + struct.pack('<16I', *sizes)
    pal = bytearray()
    for i in range(256):
        r, g, b = palette[i * 3:i * 3 + 3]
        pal += bytes((b, g, r, 255))
    return header + bytes(pal) + b''.join(levels)

def disabled(im: Image.Image) -> Image.Image:
    """Approximate Warcraft III's DISBTN look: desaturated and darkened."""
    im = im.convert('RGBA')
    gray = ImageEnhance.Color(im).enhance(0.15)
    dark = ImageEnhance.Brightness(gray).enhance(0.45)
    dark.putalpha(im.getchannel('A'))
    return dark

def to_button_blp(source, size: int = BUTTON) -> tuple[bytes, bytes]:
    """Return (normal, disabled) BLP bytes for a command button from any image."""
    im = fit_square(load_image(source), size)
    return encode(im), encode(disabled(im))

def to_texture_blp(source) -> bytes:
    """Encode keeping the source dimensions (HUD tiles, textures)."""
    return encode(load_image(source))

if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit('usage: blp.py encode SRC DST.blp | decode SRC.blp DST.png | disabled SRC DST.blp')
    cmd, src, dst = sys.argv[1:4]
    if cmd == 'encode': Path(dst).write_bytes(encode(fit_square(load_image(src))))
    elif cmd == 'texture': Path(dst).write_bytes(to_texture_blp(src))
    elif cmd == 'decode': load_image(src).save(dst)
    elif cmd == 'disabled': Path(dst).write_bytes(encode(disabled(fit_square(load_image(src)))))
