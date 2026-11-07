#pragma once
#include <stdint.h>

/* Boot the SWEETXNU payload found in the ABL ramdisk; returns only on error. */
const char *loader_boot(uintptr_t dtb);

/* Jump into XNU (entry PA) with x0 = boot_args PA; drops EL2->EL1 via ERET
 * when LK/ATF delivered the shim at EL2 (XNU early code is EL1-only).
 * Implemented in start.S; never returns. */
void enter_xnu(uint64_t entry_pa, uint64_t boot_args_pa);
