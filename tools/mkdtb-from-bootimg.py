#!/usr/bin/env python3
"""Extract the plain-FDT stock merlin DTB from a stock boot.img.

The boot images this repo packs (mkbootimg-merlin.py) carry a plain FDT in
the Android boot v2 dtb slot - the field-tested merlin recipe since v5.
Stock firmware boot.imgs carry an MTK-wrapped multi-DTB blob in that slot
instead (no FDT magic at offset 0; NOTES.md 2026-11-07), and the stock
kernel slot is Image.gz with a raw DTB appended after the gzip stream.
This tool scans the whole image for embedded FDTs, validates the device
tree structure of every candidate, and writes out the merlin/mt6768 tree,
logging every candidate it saw (offset, region, size, model, compatible).

Selection: candidates whose root model/compatible identify the device
(merlin / mt6768), which contain a /chosen and a /memory node (LK patches
those at boot; the shim walks them), and among them the LARGEST one (the
full SoC tree - overlays and sidecar tables are smaller).

Fails loudly (exit 1) when no valid merlin DTB is found: never pack a
garbage dtb (same philosophy as the xnu.yml patch-skip guard).

Usage: mkdtb-from-bootimg.py STOCK_BOOT.img OUT.dtb
"""
import hashlib
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
MAX_DTB = 4 << 20        # the merlin SoC dtb is ~180 KB
MIN_NODES = 8            # a real dts has hundreds; junk blobs do not


def boot_regions(b):
    """Named slot boundaries of a boot.img v0-v2 (offset, size) dict."""
    assert b[:8] == b'ANDROID!', 'not an Android boot image'
    ks, _ka, rs, _ra, ss, _sa, _ta, ps, ver, _osv = struct.unpack_from('<10I', b, 8)
    align = lambda n: (n + ps - 1) // ps * ps
    parts = [('header', ps), ('kernel', ks), ('ramdisk', rs), ('second', ss)]
    if ver >= 1:
        rds, _rdo, _hs = struct.unpack_from('<IQI', b, 1632)
        parts.append(('recovery_dtbo', rds))
    if ver >= 2:
        ds, _da = struct.unpack_from('<IQ', b, 1648)
        parts.append(('dtb', ds))
    off, out = 0, {}
    for name, sz in parts:
        out[name] = (off, off + align(sz))
        off += align(sz)
    out['trailing'] = (off, len(b))
    return out


def region_of(regions, off):
    for name, (lo, hi) in regions.items():
        if lo <= off < hi:
            return name
    return '?'


def fdt_parse(buf, off):
    """Validate an FDT at off. Return an info dict or None."""
    if off + 40 > len(buf):
        return None
    (_magic, totalsize, off_struct, off_strings, off_rsv, version,
     _last_comp, _cpuid, size_strings, size_struct) = struct.unpack_from('>10I', buf, off)
    if _magic != FDT_MAGIC or not (40 <= totalsize <= MAX_DTB):
        return None
    if off + totalsize > len(buf):
        return None
    if version < 16 or version > 99:
        return None
    if off_struct < 40 or size_struct < 8:
        return None
    if off_struct + size_struct > totalsize or off_strings + size_strings > totalsize:
        return None
    # the memory reservation block sits 8-aligned between header and end
    if not (40 <= off_rsv < totalsize and off_rsv % 8 == 0):
        return None

    strings = buf[off + off_strings: off + off_strings + size_strings]
    p, end = off + off_struct, off + off_struct + size_struct
    depth, names, root_props, state, saw_end = 0, [], {}, 'pre', False
    while p + 4 <= end:
        (tok,) = struct.unpack_from('>I', buf, p)
        p += 4
        if tok == FDT_NOP:
            continue
        if tok == FDT_BEGIN_NODE:
            try:
                nul = buf.index(b'\0', p, end)
            except ValueError:
                return None
            name = buf[p:nul].decode('ascii', 'replace')
            p = (nul + 4) & ~3
            if p > end:
                return None
            names.append(name)
            depth += 1
            if state == 'pre':
                state = 'root'
            elif state == 'root':
                state = 'kids'
        elif tok == FDT_END_NODE:
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                state = 'done'
        elif tok == FDT_PROP:
            if p + 8 > end:
                return None
            lenp, nameoff = struct.unpack_from('>II', buf, p)
            p += 8
            if p + lenp > end or nameoff >= len(strings):
                return None
            if state == 'root':
                try:
                    nm = strings[nameoff:strings.index(b'\0', nameoff)]
                except ValueError:
                    return None
                root_props[nm.decode('ascii', 'replace')] = bytes(buf[p:p + lenp])
            p = (p + lenp + 3) & ~3
        elif tok == FDT_END:
            saw_end = True
            break
        else:
            return None
    if depth != 0 or not saw_end or state != 'done' or len(names) < MIN_NODES:
        return None
    # LK patches /chosen at boot and the shim walks /memory - a tree
    # without them is not the stock merlin system dtb.
    if 'chosen' not in names or not any(n.split('@')[0] == 'memory' for n in names):
        return None

    def slist(v):
        return [s.decode('ascii', 'replace') for s in v.split(b'\0') if s]
    return dict(off=off, totalsize=totalsize, version=version,
                model=(root_props.get('model', b'').split(b'\0')[0]
                       .decode('ascii', 'replace')),
                compatible=slist(root_props.get('compatible', b'')),
                node_count=len(names), nodes=names)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    buf = open(sys.argv[1], 'rb').read()
    regions = boot_regions(buf)

    cands, pos = [], 0
    while True:
        pos = buf.find(struct.pack('>I', FDT_MAGIC), pos)
        if pos < 0:
            break
        info = fdt_parse(buf, pos)
        if info:
            info['region'] = region_of(regions, pos)
            cands.append(info)
        pos += 4

    if not cands:
        print('mkdtb: no valid FDT found anywhere in the image', file=sys.stderr)
        return 1

    print(f'{"off":>10} {"region":>14} {"size":>9}  model / compatible')
    for c in sorted(cands, key=lambda c: c['off']):
        print(f'{c["off"]:>10} {c["region"]:>14} {c["totalsize"]:>9}  '
              f'{c["model"]!r} {" ".join(c["compatible"])!r}')

    # drop candidates nested inside a bigger one
    cands.sort(key=lambda c: c['totalsize'], reverse=True)
    kept = []
    for c in cands:
        if any(k['off'] <= c['off'] and c['off'] + c['totalsize'] <= k['off'] + k['totalsize']
               for k in kept):
            continue
        kept.append(c)

    def is_merlin(c):
        hay = [c['model'].lower()] + [s.lower() for s in c['compatible']]
        return any('merlin' in s or 'mt6768' in s for s in hay)

    merlins = [c for c in kept if is_merlin(c)]
    if not merlins:
        print('mkdtb: FDTs found but none identifies as merlin/mt6768 - '
              'refusing to pack a foreign dtb', file=sys.stderr)
        return 1
    best = merlins[0]  # largest of the kept, non-overlapping merlin trees
    blob = buf[best['off']:best['off'] + best['totalsize']]
    open(sys.argv[2], 'wb').write(blob)
    print(f'mkdtb: wrote {sys.argv[2]}: {best["totalsize"]} bytes from the '
          f'{best["region"]} slot @ {best["off"]:#x} (fdt v{best["version"]}, '
          f'{best["node_count"]} nodes, model {best["model"]!r}, '
          f'compatible {best["compatible"]})', file=sys.stderr)
    print(f'mkdtb: sha256 {hashlib.sha256(blob).hexdigest()}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
