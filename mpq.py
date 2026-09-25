#!/usr/bin/env python3
"""Minimal pure-Python MPQ reader for Warcraft III maps (.w3x/.w3m).

Supports MPQ format 0/1 archives, encrypted files, sector-compressed files
(zlib, bzip2, PKWARE implode) and single-unit files. It is enough to read
the object data, SLK tables, script and textures of a map without any
platform-specific binaries.
"""
from __future__ import annotations
import bz2, struct, zlib
from pathlib import Path

_CRYPT = []
def _init_crypt():
    seed = 0x00100001
    table = [0] * 0x500
    for i in range(0x100):
        idx = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            t1 = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            t2 = seed & 0xFFFF
            table[idx] = t1 | t2
            idx += 0x100
    return table
_CRYPT = _init_crypt()

def hash_string(s: str, kind: int) -> int:
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in s.upper().encode('latin1'):
        seed1 = (_CRYPT[(kind << 8) + ch] ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (ch + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1

def decrypt(data: bytes, key: int) -> bytes:
    seed = 0xEEEEEEEE
    out = bytearray(len(data))
    n = len(data) // 4
    words = struct.unpack_from('<%dI' % n, data)
    res = []
    for w in words:
        seed = (seed + _CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        v = (w ^ (key + seed)) & 0xFFFFFFFF
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed = (v + seed + (seed << 5) + 3) & 0xFFFFFFFF
        res.append(v)
    out[:n * 4] = struct.pack('<%dI' % n, *res)
    out[n * 4:] = data[n * 4:]
    return bytes(out)

def encrypt(data: bytes, key: int) -> bytes:
    seed = 0xEEEEEEEE
    n = len(data) // 4
    res = []
    for w in struct.unpack_from('<%dI' % n, data):
        seed = (seed + _CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        v = (w ^ (key + seed)) & 0xFFFFFFFF
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed = (w + seed + (seed << 5) + 3) & 0xFFFFFFFF
        res.append(v)
    return struct.pack('<%dI' % n, *res) + data[n * 4:]

def file_key(name: str, offset: int, size: int, flags: int) -> int:
    key = hash_string(name.replace('/', '\\').split('\\')[-1], 3)
    if flags & 0x20000:
        key = ((key + offset) ^ size) & 0xFFFFFFFF
    return key

# ---- PKWARE DCL "explode" (port of zlib contrib/blast.c, binary mode) ----
def _construct(rep):
    lengths=[]
    for b in rep:
        lengths += [b & 15] * ((b >> 4) + 1)
    count=[0]*16
    for l in lengths: count[l]+=1
    offs=[0]*16
    for l in range(1,16): offs[l]=offs[l-1]+count[l-1]
    symbol=[0]*len(lengths)
    for s,l in enumerate(lengths):
        if l: symbol[offs[l]]=s; offs[l]+=1
    return count,symbol
_LENCODE=_construct([2,35,36,53,38,23])
_DISTCODE=_construct([2,20,53,230,247,151,248])
_BASE=[3,2,4,5,6,7,8,9,10,12,16,24,40,72,136,264]
_EXTRA=[0,0,0,0,0,0,0,0,1,2,3,4,5,6,7,8]

def explode(data: bytes) -> bytes:
    if len(data) < 2 or data[0] != 0 or data[1] not in (4,5,6):
        raise ValueError('implode: unsupported header')
    dict_bits=data[1]; pos=2; bitbuf=0; left=0
    out=bytearray()
    def bits(n):
        nonlocal bitbuf,left,pos
        while left < n:
            if pos>=len(data): raise ValueError('implode: input exhausted')
            bitbuf |= data[pos] << left; pos+=1; left+=8
        v=bitbuf & ((1<<n)-1); bitbuf >>= n; left -= n; return v
    def decode(h):
        count,symbol=h; code=first=index=0; ln=1
        while True:
            code |= bits(1) ^ 1
            c=count[ln]
            if code < first + c: return symbol[index + (code-first)]
            index+=c; first+=c; first<<=1; code<<=1; ln+=1
            if ln>15: raise ValueError('implode: bad code')
    while True:
        try:
            flag=bits(1)
        except ValueError:
            break
        if flag:
            sym=decode(_LENCODE); length=_BASE[sym]+bits(_EXTRA[sym])
            if length==519: break
            n=2 if length==2 else dict_bits
            dist=(decode(_DISTCODE)<<n)+bits(n)+1
            if dist>len(out): raise ValueError('implode: distance beyond output')
            for _ in range(length): out.append(out[-dist])
        else:
            out.append(bits(8))
    return bytes(out)

def decompress_sector(data: bytes, expected: int) -> bytes:
    if len(data) >= expected: return data[:expected]
    mask = data[0]; payload = data[1:]
    if mask == 0x02: return zlib.decompress(payload)
    if mask == 0x10: return bz2.decompress(payload)
    if mask == 0x08: return explode(payload)
    if mask & 0x10: payload = bz2.decompress(payload); mask &= ~0x10
    if mask & 0x02: payload = zlib.decompress(payload); mask &= ~0x02
    if mask & 0x08: payload = explode(payload); mask &= ~0x08
    if mask: raise ValueError('unsupported compression mask 0x%02x' % mask)
    return payload

class MPQ:
    HASH_EMPTY = 0xFFFFFFFF
    HASH_DELETED = 0xFFFFFFFE
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.base = self.data.find(b'MPQ\x1a')
        if self.base < 0: raise ValueError('not an MPQ')
        (_, hsize, asize, fmt, bs, htpos, btpos, htsize, btsize) = struct.unpack_from('<4sIIHHIIII', self.data, self.base)
        self.header_size = hsize; self.format = fmt
        self.sector_size = 512 << bs
        raw = self.data[self.base + htpos: self.base + htpos + htsize * 16]
        raw = decrypt(raw, hash_string('(hash table)', 3))
        self.hashes = [struct.unpack_from('<IIHHI', raw, i * 16) for i in range(htsize)]
        raw = self.data[self.base + btpos: self.base + btpos + btsize * 16]
        raw = decrypt(raw, hash_string('(block table)', 3))
        self.blocks = [list(struct.unpack_from('<IIII', raw, i * 16)) for i in range(btsize)]
        self.ht_size = htsize
        self.names = {}
        try:
            for line in self.read('(listfile)').decode('latin1').splitlines():
                line = line.strip().rstrip('\r')
                if line: self.names[line.lower()] = line
        except KeyError:
            pass
    def find(self, name: str):
        name = name.replace('/', '\\')
        idx = hash_string(name, 0) & (self.ht_size - 1)
        a, b = hash_string(name, 1), hash_string(name, 2)
        start = idx
        while True:
            h1, h2, loc, plat, block = self.hashes[idx]
            if block == self.HASH_EMPTY: return None
            if h1 == a and h2 == b and block != self.HASH_DELETED: return block
            idx = (idx + 1) & (self.ht_size - 1)
            if idx == start: return None
    def has(self, name: str) -> bool:
        b = self.find(name)
        return b is not None and bool(self.blocks[b][3] & 0x80000000)
    def read(self, name: str) -> bytes:
        block = self.find(name)
        if block is None: raise KeyError(name)
        offset, csize, fsize, flags = self.blocks[block]
        if not flags & 0x80000000: raise KeyError(name)
        start = self.base + offset
        raw = self.data[start:start + csize]
        encrypted = bool(flags & 0x10000)
        key = file_key(name, offset, fsize, flags) if encrypted else 0
        compressed = bool(flags & 0x300)
        if flags & 0x01000000 or not compressed and not encrypted:
            if encrypted: raw = decrypt(raw, key)
            if compressed: raw = decompress_sector(raw, fsize) if flags & 0x200 else explode(raw[:])
            return raw[:fsize]
        if not compressed:
            return decrypt(raw, key)[:fsize]
        n = (fsize + self.sector_size - 1) // self.sector_size
        table = raw[:(n + 1) * 4]
        if encrypted: table = decrypt(table, (key - 1) & 0xFFFFFFFF)
        offs = struct.unpack_from('<%dI' % (n + 1), table)
        out = bytearray()
        for i in range(n):
            chunk = raw[offs[i]:offs[i + 1]]
            if encrypted: chunk = decrypt(chunk, (key + i) & 0xFFFFFFFF)
            expected = min(self.sector_size, fsize - len(out))
            if flags & 0x200: chunk = decompress_sector(chunk, expected)
            elif flags & 0x100 and len(chunk) < expected: chunk = explode(chunk)
            out.extend(chunk[:expected])
        return bytes(out)
    def list(self):
        return sorted(self.names.values())

if __name__ == '__main__':
    import sys
    m = MPQ(sys.argv[1])
    if len(sys.argv) == 2:
        for n in m.list(): print(n)
    else:
        sys.stdout.buffer.write(m.read(sys.argv[2]))
