#pragma once
#include <stdint.h>

/* MT6768 (Xiaomi Redmi Note 9 "merlin") bring-up facts, from the device's
 * own Android kernel source (arch/arm64/boot/dts/mediatek/mt6768.dts and
 * drivers/watchdog/mediatek/wdt/common/wdt_v2/mtk_wdt.h):
 *
 * - toprgu (AP RGU) watchdog at 0x10007000. MODE is base+0: bit0 ENABLE,
 *   writes need MODE_KEY 0x22000000 in the top byte. LK arms it; if the OS
 *   image never pets it, the box resets ~30 s into the boot.
 * - LK initializes the panel and keeps it scanning (continuous splash). The
 *   boot-logo framebuffer address arrives in the DTB LK passes in x0:
 *   /chosen "atag,videolfb-fb_base_l" (u32; e.g. 0x7e605000) and
 *   "atag,videolfb-fb_base_h" (u32, 0 on this SoC). Panel 1080x2340, 32bpp.
 * - boot.img load addresses (stock merlin mkbootimg args: base 0x40078000,
 *   kernel_offset 0x8000, ramdisk_offset 0x07c08000): the ramdisk we pack
 *   lands at 0x47c80000. LK normally also publishes /chosen
 *   linux,initrd-start/end for the boot ramdisk; try those first.
 */

#define MERLIN_TOPRGU_BASE	0x10007000UL
#define MERLIN_TOPRGU_MODE	(MERLIN_TOPRGU_BASE + 0x0000)
#define MERLIN_WDT_MODE_KEY	0x22000000UL
#define MERLIN_WDT_MODE_ENABLE	0x00000001UL
#define MERLIN_WDT_IRQ_CLR_KEY	0x23000000UL
#define MERLIN_WDT_IRQ_CLR_MASK	0x000001ffUL

#define MERLIN_FB_W		1080
#define MERLIN_FB_H		2340
#define MERLIN_FB_STRIDE	(MERLIN_FB_W * 4)
#define MERLIN_FB_FALLBACK	0x7e605000UL	/* dts atag,videolfb default */
/* atag,videolfb points at the START of the 24.9MB LK vram carve-out
 * (vramSize 0x17e8000). NOTE: drawing at base + (vramSize - fb) broke the
 * boot entirely (v9) - the v6-era raw base is the proven-working one; the
 * v6-photo shear remains unexplained and gets measured, not theorized. */

#define MERLIN_RAMDISK_FALLBACK	0x47c80000UL	/* base 0x40078000 + 0x07c08000 */

void merlin_main(uint64_t dtb) __attribute__((noreturn));
