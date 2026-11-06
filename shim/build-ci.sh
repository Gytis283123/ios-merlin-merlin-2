#!/bin/bash
# Merlin shim build for CI: -DMERLIN selects the MT6768 bring-up (toprgu
# watchdog stop, LK splash framebuffer console, merlin payload discovery).
# ufs.c (the Qualcomm UFS probe) is not linked: merlin is eMMC and the probe
# would poke wrong addresses. Compile/link only — the boot image is packed
# later from this artifact, the xnu kernel artifact and the generated ADT
# (the stock merlin DTB is a device artifact and never in git).
set -euo pipefail
cd "$(dirname "$0")"
CC=${CC:-aarch64-linux-gnu-gcc}
READELF=${READELF:-aarch64-linux-gnu-readelf}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
NM=${NM:-aarch64-linux-gnu-nm}
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra -DMERLIN"
FILES="start.S shim.c merlin.c console.c mmu.c fdt.c loader.c"
mkdir -p out
for f in $FILES; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
# Relocation check on the C objects only (start.S may carry ABS64 relocs —
# the image runs wherever LK puts it with no relocation pass).
COBJ=""
for f in $FILES; do [ "${f##*.}" = c ] && COBJ="$COBJ out/${f%.*}.o"; done
abs=$($READELF -r $COBJ | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	$OBJFILES -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/shim-merlin.bin
size=$($NM out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/shim-merlin.bin
ls -l out/shim-merlin.bin
