#!/usr/bin/env python3
"""Pack the merlin boot image (Android boot image v2).

Two hard-won rules baked in (see NOTES.md):
  1. The kernel slot MUST be gzip-compressed: MediaTek LK gunzips it
     (stock Image.gz and every shim that ever booted here is gzip).
     --raw-kernel opts out for experiments only.
  2. The header is cloned VERBATIM from the stock firmware boot.img
     (all 1660 bytes: os_version, cmdline, id field, the tail field at
     0x66C where the vendor packer writes 1660) with only three size
     fields patched. --no-clone builds a spec header instead.

Layout: kernel = shim (gzipped), ramdisk = SWEETXNU payload, dtb = stock
merlin DTB. Slots: kernel 0x40080000, ramdisk 0x47c80000, dtb 0x4bc80000,
page 2048 (the stock merlin mkbootimg parameters).

Usage:
  mkbootimg-merlin.py OUT.img --kernel SHIM --ramdisk PAYLOAD [--dtb DTB]
      [--clone-header STOCK.boot.img] [--no-gzip] [--cmdline "..."]
"""
import argparse
import gzip
import struct

PAGE = 2048
HEADER_SIZE_V2 = 1660
BASE = 0x40078000
KERNEL_OFFSET = 0x8000
RAMDISK_OFFSET = 0x07C08000
TAGS_OFFSET = 0x0BC08000


def align(n, page=PAGE):
    return (n + page - 1) & ~(page - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--kernel', required=True, help='shim binary (will be gzipped)')
    ap.add_argument('--ramdisk', required=True, help='SWEETXNU payload')
    ap.add_argument('--dtb', help='stock merlin DTB')
    ap.add_argument('--clone-header', help='stock boot.img to clone the 1660-byte header from')
    ap.add_argument('--no-gzip', action='store_true', help='put the kernel slot in raw (for experiments)')
    ap.add_argument('--cmdline', default='bootopt=64S3,32N2,64N2 buildvariant=user')
    ap.add_argument('--name', default='')
    args = ap.parse_args()

    kernel = open(args.kernel, 'rb').read()
    ramdisk = open(args.ramdisk, 'rb').read()
    dtb = open(args.dtb, 'rb').read() if args.dtb else b''

    if args.no_gzip:
        kslot = kernel
    else:
        kslot = gzip.compress(kernel, 9, mtime=0)
        assert gzip.decompress(kslot) == kernel, 'gzip round-trip failed'

    if args.clone_header:
        stock = open(args.clone_header, 'rb').read()
        assert stock[:8] == b'ANDROID!', 'clone source is not a boot image'
        hdr = bytearray(stock[:HEADER_SIZE_V2])
    else:
        hdr = bytearray(HEADER_SIZE_V2)
        hdr[0:8] = b'ANDROID!'
        fields = [
            (0x0C, BASE + KERNEL_OFFSET),
            (0x14, BASE + RAMDISK_OFFSET),
            (0x18, 0), (0x1C, 0),                      # second
            (0x20, BASE + TAGS_OFFSET), (0x24, PAGE),
            (0x28, 2), (0x2C, 0x16000157),             # header_version, os_version
        ]
        for off, val in fields:
            struct.pack_into('<I', hdr, off, val)
        cmd = args.cmdline.encode()[:512]
        hdr[0x40:0x40 + len(cmd)] = cmd
        struct.pack_into('<I', hdr, 0x66C, HEADER_SIZE_V2)  # vendor tail convention
        struct.pack_into('<Q', hdr, 0x674, BASE + TAGS_OFFSET)

    # patch ONLY the size fields
    struct.pack_into('<I', hdr, 0x08, len(kslot))
    struct.pack_into('<I', hdr, 0x10, len(ramdisk))
    struct.pack_into('<I', hdr, 0x670, len(dtb))

    out = bytearray(hdr)
    out += b'\0' * (align(HEADER_SIZE_V2) - HEADER_SIZE_V2)
    for blob in (kslot, ramdisk, dtb):
        if blob:
            out += blob
            out += b'\0' * (align(len(blob)) - len(blob))

    open(args.out, 'wb').write(out)
    print(f'{args.out}: {len(out)} bytes (kernel slot {len(kslot)}'
          f'{" gzip" if not args.no_gzip else " RAW"}, ramdisk {len(ramdisk)},'
          f' dtb {len(dtb)}, kernel@{BASE + KERNEL_OFFSET:#x}'
          f' ramdisk@{BASE + RAMDISK_OFFSET:#x})')


if __name__ == '__main__':
    main()
