#!/bin/bash
# CI shim build: the compile/link/objcopy steps of build.sh, without the
# boot.img packaging (the boot image is packed later from the kernel, ADT and
# the stock merlin DTB, which is a device artifact and never in git).
# Baseline = the upstream shim file set (incl. the ufs probe; it only runs
# when no payload is present). The merlin-specific variant is built from the
# -DMERLIN work in progress.
set -euo pipefail
cd "$(dirname "$0")"
CC=${CC:-aarch64-linux-gnu-gcc}
READELF=${READELF:-aarch64-linux-gnu-readelf}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
NM=${NM:-aarch64-linux-gnu-nm}
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
abs=$($READELF -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/shim-merlin.bin
size=$($NM out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/shim-merlin.bin
ls -l out/shim-merlin.bin
