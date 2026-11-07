#!/usr/bin/env python3
"""Repack the merlin boot image with display-knob cmdline values - for
user-driven display iteration. No CI, no shim rebuild: only the payload's
cmdline changes.

Usage:
  try-geometry.py [W] [H] [PITCH] [--scale N] [--base 0xADDR] [--out FILE]

Defaults: W=1080 H=2340 PITCH=4320 scale=2 base=auto(RDMA register).
The shim parses merlinfb_w/h/p/s/b from this cmdline at boot.

After packing: fastboot flash boot <out> ; fastboot reboot
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, 'out')
KERNEL = os.path.join(REPO, 'artifacts/kernel/kernel.development.sweet')
SHIM = os.path.join(REPO, 'artifacts/shim/shim-merlin-v22.bin')
DTB = os.path.join(REPO, 'dtb/stock-merlin.dtb')


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('w', nargs='?', type=int, default=1080)
    ap.add_argument('h', nargs='?', type=int, default=2340)
    ap.add_argument('pitch', nargs='?', type=int, default=4352)
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--base', default=None, help='hex fb base override')
    ap.add_argument('--out', default=os.path.join(OUT, 'try.img'))
    ap.add_argument('--shim', default=SHIM)
    ap.add_argument('--kernel', default=KERNEL)
    args = ap.parse_args()

    base = args.base if args.base else 'auto'
    cmdline = (f'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam '
               f'-noprogress merlinfb_w={args.w} merlinfb_h={args.h} '
               f'merlinfb_p={args.pitch} merlinfb_s={args.scale}')
    if args.base:
        cmdline += f' merlinfb_b={args.base}'

    for f in (args.kernel, args.shim, DTB):
        if not os.path.exists(f):
            sys.exit(f'missing component: {f}')

    adt = os.path.join(OUT, 'merlin.adt')
    payload = os.path.join(OUT, 'payload-try.bin')
    subprocess.run([sys.executable, os.path.join(HERE, 'mkadt-merlin.py'), adt],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'mkpayload.py'),
                    args.kernel, adt, payload, '--cmdline', cmdline],
                   check=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'mkbootimg-merlin.py'),
                    args.out, '--kernel', args.shim, '--ramdisk', payload,
                    '--dtb', DTB], check=True)
    print(f'{args.out}: {args.w}x{args.h} pitch {args.pitch} scale {args.scale}'
          f' base {base}')
    print(f'fastboot flash boot {args.out}')
    print(f'fastboot reboot')


if __name__ == '__main__':
    main()
