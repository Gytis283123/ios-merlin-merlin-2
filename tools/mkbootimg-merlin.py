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

# Header conventions cloned from the stock/vendor-packed merlin boot images
# (the only format this unit's LK is proven to boot). The vendor packer
# writes 1660 (= header size) into the v2 tail field at 0x66C where the
# AOSP spec says header_version=2, and the stock cmdline/os_version ride
# along. We mimic it field-for-field: deviating from these values is the
# prime suspect for LK refusing to finalize the boot (25 s watchdog loops
# with no code executed).
STOCK_CMDLINE = 'bootopt=64S3,32N2,64N2 buildvariant=user'
STOCK_OS_VERSION = 0x16000157
TAIL_0x66C = HEADER_SIZE_V2


def align(n, page=PAGE):
    return (n + page - 1) & ~(page - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--kernel', required=True, help='shim binary')
    ap.add_argument('--ramdisk', required=True, help='SWEETXNU payload')
    ap.add_argument('--dtb', help='optional stock merlin DTB')
    ap.add_argument('--cmdline', default=STOCK_CMDLINE)
    ap.add_argument('--name', default='')
    ap.add_argument('--os-version', type=lambda s: int(s, 0), default=STOCK_OS_VERSION)
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
    # tail field @0x66C, dtb_size @0x670, dtb_addr @0x674. The tail keeps
    # the vendor packer's convention (see TAIL_0x66C above).
    struct.pack_into('<I', hdr, 0x660, 0)
    struct.pack_into('<I', hdr, 0x66C, TAIL_0x66C)
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
