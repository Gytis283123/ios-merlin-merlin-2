#!/usr/bin/env python3
"""Pack the merlin boot image (Android boot image v2).

Layout of a merlin test image:
  kernel  = the shim (shim/build-ci.sh artifact), loaded at 0x40080000
  ramdisk = the SWEETXNU payload (tools/mkpayload.py: xnu + ADT + cmdline),
            loaded at 0x47c80000 — the shim finds it there (or via the
            /chosen initrd properties LK publishes)
  dtb     = optional; stock merlin DTB (device artifact, never in git).
            Without it, LK passes its own tree (dtb partition + dtbo merge).

Addresses are the stock merlin mkbootimg parameters (base 0x40078000,
kernel_offset 0x8000, ramdisk_offset 0x07c08000, tags_offset 0x0bc08000,
page size 2048) — the same slot layout LK uses for the stock kernel, so the
shim lands where the stock kernel would.

Usage:
  mkbootimg-merlin.py OUT.img --kernel SHIM --ramdisk PAYLOAD [--dtb DTB]
                             [--cmdline "..."] [--name NAME]
"""
import argparse
import struct

PAGE = 2048
HEADER_SIZE_V2 = 1660
BASE = 0x40078000
KERNEL_OFFSET = 0x8000
RAMDISK_OFFSET = 0x07C08000
TAGS_OFFSET = 0x0BC08000

# Header conventions: LK on this unit wants the AOSP v2 spec values AND a
# DTB. Boot matrix (2026-11-07): no DTB -> ~8 s loop; DTB + tail field 2
# (spec) -> ~25 s loop (LK accepts + jumps, deep path reached); DTB +
# tail 1660 (vendor-clone experiment) -> ~8 s early reject again. The
# vendor packer writes 1660 (= header size) at 0x66C, but this unit's LK
# wants 2 there once a DTB is present.
SPEC_CMDLINE = ''
SPEC_OS_VERSION = 0
TAIL_0x66C = 2


def align(n, page=PAGE):
    return (n + page - 1) & ~(page - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--kernel', required=True, help='shim binary')
    ap.add_argument('--ramdisk', required=True, help='SWEETXNU payload')
    ap.add_argument('--dtb', help='optional stock merlin DTB')
    ap.add_argument('--cmdline', default=SPEC_CMDLINE)
    ap.add_argument('--name', default='merlin-xnu')
    ap.add_argument('--os-version', type=lambda s: int(s, 0), default=SPEC_OS_VERSION)
    ap.add_argument('--tail-0x66c', type=lambda s: int(s, 0), default=TAIL_0x66C)
    args = ap.parse_args()

    kernel = open(args.kernel, 'rb').read()
    ramdisk = open(args.ramdisk, 'rb').read()
    dtb = open(args.dtb, 'rb').read() if args.dtb else b''

    hdr = bytearray(HEADER_SIZE_V2)
    hdr[0:8] = b'ANDROID!'
    fields = [
        (0x08, len(kernel)), (0x0C, BASE + KERNEL_OFFSET),
        (0x10, len(ramdisk)), (0x14, BASE + RAMDISK_OFFSET),
        (0x18, 0), (0x1C, 0),                      # second
        (0x20, BASE + TAGS_OFFSET), (0x24, PAGE),
        (0x28, 2), (0x2C, 0),                      # header_version, os_version
    ]
    for off, val in fields:
        struct.pack_into('<I', hdr, off, val)
    struct.pack_into('<I', hdr, 0x2C, args.os_version)
    name = args.name.encode()[:16]
    hdr[0x30:0x30 + len(name)] = name
    cmd = args.cmdline.encode()[:512]
    hdr[0x40:0x40 + len(cmd)] = cmd
    # v2 tail: recovery_dtbo_size(0) @0x660, recovery_dtbo_offset @0x664,
    # tail field @0x66C (LK wants 2 here — see the boot matrix above),
    # dtb_size @0x670, dtb_addr @0x674.
    struct.pack_into('<I', hdr, 0x660, 0)
    struct.pack_into('<I', hdr, 0x66C, args.tail_0x66c)
    struct.pack_into('<I', hdr, 0x670, len(dtb))
    struct.pack_into('<Q', hdr, 0x674, BASE + TAGS_OFFSET)

    out = bytearray()
    out += hdr
    out += b'\0' * (align(HEADER_SIZE_V2) - HEADER_SIZE_V2)
    for blob in (kernel, ramdisk, dtb):
        if blob:
            out += blob
            out += b'\0' * (align(len(blob)) - len(blob))

    open(args.out, 'wb').write(out)
    print(f'{args.out}: {len(out)} bytes (kernel {len(kernel)}, ramdisk '
          f'{len(ramdisk)}, dtb {len(dtb)}, kernel@{BASE + KERNEL_OFFSET:#x} '
          f'ramdisk@{BASE + RAMDISK_OFFSET:#x})')


if __name__ == '__main__':
    main()
