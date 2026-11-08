#!/usr/bin/env python3
"""Verify a packed merlin boot image against its exact inputs.

  verify-bootimg.py IMG --stock STOCK.img --shim SHIM.bin --payload PAYLOAD.bin
      --adt ADT.bin --dtb DTB.bin [--cmdline "..."]

Hard checks (any failure = exit 1, no partial pass):
  1. Boot magic ANDROID!, header version 2, page size 2048.
  2. Header clone rule: IMG[0:1660] == STOCK[0:1660] byte-for-byte except
     the three size fields (0x08 kernel_size, 0x10 ramdisk_size, 0x670
     dtb_size). The merlin rule is "clone the stock header verbatim, patch
     only the sizes" (NOTES.md: six bootloops of format forensics).
  3. Kernel slot is gzip and inflates to exactly the shim binary.
  4. Ramdisk slot == payload file bytes; payload magic SWEETXNU, version 1;
     cmdline field (optional --cmdline for an exact assert).
  5. The ADT embedded in the payload == the ADT file, and its gic node reg
     carries the Linux arm,gic-v3 addresses of this SoC (GICD
     0x0c000000/0x40000, GICR 0x0c040000/0x200000, arm-io relative) - the
     v49 lesson (GICR 0x0c400000 is the decoy that reads all-ones),
     guarded forever.
  6. dtb slot == DTB file bytes; FDT magic.
  7. The image ends exactly at the paged end of the dtb slot.
"""
import argparse
import gzip
import hashlib
import struct
import sys

HEADER_SIZE_V2 = 1660
# the three 4-byte size fields the packer patches (kernel, ramdisk, dtb)
SIZE_FIELDS = ((0x08, 4, 'kernel_size'), (0x10, 4, 'ramdisk_size'),
               (0x670, 4, 'dtb_size'))
ALLOWED = set(i for off, n, _ in SIZE_FIELDS for i in range(off, off + n))
GIC_REG = struct.pack('<4Q', 0x0b000000, 0x40000, 0x0b040000, 0x200000)


def ok(msg):
    print(f'  ok  {msg}')


def die(msg):
    print(f'FAIL  {msg}', file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('img')
    ap.add_argument('--stock', required=True)
    ap.add_argument('--shim', required=True)
    ap.add_argument('--payload', required=True)
    ap.add_argument('--adt', required=True)
    ap.add_argument('--dtb', required=True)
    ap.add_argument('--cmdline')
    a = ap.parse_args()

    img = open(a.img, 'rb').read()
    stock = open(a.stock, 'rb').read()
    shim = open(a.shim, 'rb').read()
    payload = open(a.payload, 'rb').read()
    adt = open(a.adt, 'rb').read()
    dtb = open(a.dtb, 'rb').read()

    if img[:8] != b'ANDROID!':
        die('no ANDROID! boot magic')
    ks = struct.unpack_from('<I', img, 0x08)[0]
    rs = struct.unpack_from('<I', img, 0x10)[0]
    ss = struct.unpack_from('<I', img, 0x18)[0]
    ps = struct.unpack_from('<I', img, 0x24)[0]
    ver = struct.unpack_from('<I', img, 0x28)[0]
    ds = struct.unpack_from('<I', img, 0x670)[0]
    if ver != 2:
        die(f'header version {ver}, expected 2')
    if ps != 2048:
        die(f'page size {ps}, expected 2048')
    ok(f'boot magic, header v2, page 2048 (kernel {ks} gzip, '
       f'ramdisk {rs}, second {ss}, dtb {ds})')

    # 2. header clone, modulo the three 4-byte size fields
    if stock[:8] != b'ANDROID!':
        die('stock clone source is not a boot image')
    diff = [i for i in range(HEADER_SIZE_V2) if img[i] != stock[i]]
    extra = [i for i in diff if i not in ALLOWED]
    if extra:
        die(f'header bytes mutated outside the 3 size fields: {extra[:8]}...')
    names = [nm for off, n, nm in SIZE_FIELDS
             if any(off <= i < off + n for i in diff)]
    ok(f'header cloned verbatim from stock (patched fields: {", ".join(names) or "none"})')

    # slot layout
    align = lambda n: (n + ps - 1) // ps * ps
    off = ps
    kslot = img[off:off + ks]
    off += align(ks)
    rslot = img[off:off + rs]
    off += align(rs) + align(ss)
    rds = struct.unpack_from('<I', img, 1632)[0]      # recovery_dtbo (v1+)
    off += align(rds)
    doff = off
    dslot = img[off:off + ds]

    # 3. kernel slot = gzip(shim)
    if kslot[:2] != b'\x1f\x8b':
        die('kernel slot is not gzip (merlin rule 1: LK gunzips the slot)')
    if gzip.decompress(kslot) != shim:
        die('kernel slot does not inflate to the shim binary')
    ok(f'kernel slot: gzip, inflates to the shim ({len(shim)} bytes)')

    # 4. ramdisk slot = payload
    if rslot != payload:
        die('ramdisk slot != payload file')
    if payload[:8] != b'SWEETXNU':
        die('payload magic is not SWEETXNU')
    pver, _nsegs = struct.unpack_from('<II', payload, 8)
    if pver != 1:
        die(f'payload version {pver}, expected 1')
    cmd = payload[0x48:0x48 + 608].split(b'\0')[0].decode('ascii', 'replace')
    if a.cmdline is not None and cmd != a.cmdline:
        die(f'payload cmdline {cmd!r} != expected {a.cmdline!r}')
    ok(f'ramdisk slot: payload, SWEETXNU v1, cmdline {cmd!r}')

    # 5. embedded ADT + the GICR guard
    adt_off, adt_size = struct.unpack_from('<2Q', payload, 0x20)
    emb = payload[adt_off:adt_off + adt_size]
    if emb != adt:
        die('the ADT embedded in the payload != the ADT file')
    if GIC_REG not in emb:
        die('ADT gic reg does not carry GICD 0x0c000000/0x40000 + '
            'GICR 0x0c040000/0x200000 (the v49 decoy guard)')
    ok(f'payload ADT == ADT file ({adt_size} bytes), GICR v49 guard passed')

    # 6. dtb slot
    if dslot != dtb:
        die('dtb slot != DTB file')
    if struct.unpack_from('>I', dtb, 0)[0] != 0xD00DFEED:
        die('dtb slot has no FDT magic')
    ok(f'dtb slot: FDT magic, {ds} bytes')

    # 7. exact end
    if len(img) != doff + align(ds):
        die(f'image has {len(img) - doff - align(ds)} trailing bytes past the dtb slot')
    ok('image ends exactly at the paged dtb slot end')

    print('verify-bootimg: PASS')
    for name, blob in (('img', img), ('shim', shim), ('payload', payload),
                       ('adt', adt), ('dtb', dtb)):
        print(f'  sha256 {name:8} {hashlib.sha256(blob).hexdigest()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
