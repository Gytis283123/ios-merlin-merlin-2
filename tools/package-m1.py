#!/usr/bin/env python3
"""Package the merlin M1 boot image from CI artifacts.

M1a (kernel-executes milestone): payload = CI kernel + merlin ADT + the
proven bring-up cmdline, NO rootfs — the kernel boots to mountroot retries
with its log on the panel via the framebuffer console.

Usage:
  package-m1.py KERNEL IMG [--shim SHIM] [--cmdline "..."] [--ramdisk ROOTFS]
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, 'out')
DEFAULT_CMDLINE = ('debug=0xc serial=3 cpus=1 keepsyms=1 '
                   '-enable_kprintf_spam -noprogress')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(cmd):
    print('+', ' '.join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel', help='kernel.development.sweet from CI')
    ap.add_argument('img', help='output boot image path')
    ap.add_argument('--shim', default=os.path.join(OUT, 'shim-merlin.bin'))
    ap.add_argument('--cmdline', default=DEFAULT_CMDLINE)
    ap.add_argument('--ramdisk', help='optional rootfs image (rd=md0)')
    ap.add_argument('--dtb', help='optional stock merlin DTB (device artifact)')
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    adt = os.path.join(OUT, 'merlin.adt')
    payload = os.path.join(OUT, 'payload-m1.bin')

    run([sys.executable, os.path.join(HERE, 'mkadt-merlin.py'), adt])
    payload_cmd = [sys.executable, os.path.join(HERE, 'mkpayload.py'),
                   args.kernel, adt, payload, '--cmdline', args.cmdline]
    if args.ramdisk:
        payload_cmd += ['--ramdisk', args.ramdisk]
    run(payload_cmd)
    bootimg_cmd = [sys.executable, os.path.join(HERE, 'mkbootimg-merlin.py'),
                   args.img, '--kernel', args.shim, '--ramdisk', payload]
    if args.dtb:
        bootimg_cmd += ['--dtb', args.dtb]
    run(bootimg_cmd)

    for p in (args.kernel, args.shim, payload, args.img):
        print(f'{sha256(p)}  {os.path.basename(p)}  ({os.path.getsize(p)} bytes)')


if __name__ == '__main__':
    main()
