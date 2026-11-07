/*
 * Merlin (MT6768) platform bring-up for the shim. Runs before anything
 * else: stop the toprgu watchdog, put the console on the LK splash
 * framebuffer, locate the SWEETXNU payload, boot it; on any failure keep
 * the diagnostics on the panel and hold (the watchdog is off, nothing
 * reboots under us and the screen is the UART).
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"
#include "merlin.h"

static inline uint32_t rd32(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr32(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }

static inline uint64_t mpidr(void)
{
	uint64_t v;
	__asm__ volatile("mrs %0, mpidr_el1" : "=r"(v));
	return v;
}

static inline uint64_t cntfrq(void)
{
	uint64_t v;
	__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(v));
	return v;
}

/* wdt_v2 disable: clear any pending IRQ (keyed write), then clear MODE
 * ENABLE with the key set (mtk_wdt_v2.c wdt_config / mtk_wdt.h). */
static void merlin_wdt_stop(void)
{
	wr32(MERLIN_TOPRGU_MODE, MERLIN_WDT_IRQ_CLR_KEY | MERLIN_WDT_IRQ_CLR_MASK);
	wr32(MERLIN_TOPRGU_MODE,
	     (rd32(MERLIN_TOPRGU_MODE) & ~MERLIN_WDT_MODE_ENABLE) | MERLIN_WDT_MODE_KEY);
}

static uint64_t merlin_fb_base(uintptr_t fdt)
{
	uint64_t lo = 0, hi = 0;
	if (fdt_chosen_u64(fdt, "atag,videolfb-fb_base_l", &lo) &&
	    fdt_chosen_u64(fdt, "atag,videolfb-fb_base_h", &hi))
		return (hi << 32) | lo;
	return MERLIN_FB_FALLBACK;
}

/* Payload discovery: prefer what LK published in /chosen, fall back to the
 * known ramdisk load address of the boot image we pack; both are verified
 * against the payload magic by the caller. */
static uint64_t merlin_ramdisk(uintptr_t fdt)
{
	uint64_t s = 0, e = 0;
	if (fdt_chosen_u64(fdt, "linux,initrd-start", &s) &&
	    fdt_chosen_u64(fdt, "linux,initrd-end", &e) && s && e > s)
		return s;
	return MERLIN_RAMDISK_FALLBACK;
}

/* memory-map report: the live values LK patched into the DTB it hands us.
 * This is the authoritative DRAM map (reserved TEE/SCP/SSPM regions and
 * all) - the ADT's kernel band must avoid every no-map entry. */
static int mem_lines;
static int mem_cb(const struct fdt_mem_ent *e, void *ctx)
{
	(void)ctx;
	if (mem_lines >= 12)
		return 1;
	char label[6];
	const char *kind = "RVD";
	if (e->kind[0] == 'm')
		kind = "MEM";
	else if (e->nomap)
		kind = "RVDN";	/* reserved, no-map: the dangerous ones */
	for (int i = 0; i < 4 && kind[i]; i++)
		label[i] = kind[i];
	label[4] = '0' + (mem_lines % 10);
	label[5] = 0;
	con_hex2(label, "b=", (uint32_t)e->base, "s=", (uint32_t)e->size);
	mem_lines++;
	return 0;
}

/* Display ruler: markers at KNOWN fb coordinates. One photo of the sheared
 * result encodes the panel's true scan pitch and origin: where each marker
 * lands vs where it was drawn is the mapping, and the vertical marker
 * columns reveal the pitch directly (a wrong pitch turns columns into
 * diagonals whose slope is pitch_draw/pitch_scan). */
static void paint_ruler(void)
{
	volatile uint32_t *fb = con_fb;
	const uint32_t w = con_w, h = con_h, pitch = con_stride / 4;

	/* full-height 6px vertical lines every 120 px -> pitch readout */
	for (uint32_t x = 0; x + 6 <= w; x += 120)
		for (uint32_t y = 0; y < h; y++)
			for (uint32_t dx = 0; dx < 6; dx++)
				fb[y * pitch + x + dx] = 0xFFFFFFFF;
	/* full-width 6px horizontal lines every 240 px -> row mapping */
	for (uint32_t y = 0; y + 6 <= h; y += 240)
		for (uint32_t x = 0; x < w; x++)
			for (uint32_t dy = 0; dy < 6; dy++)
				fb[(y + dy) * pitch + x] = 0xFF00C8FF;
	/* origin marker: 40px red-on-white block at (0,0) and at (w-40, h-40) */
	for (uint32_t y = 0; y < 40; y++)
		for (uint32_t x = 0; x < 40; x++) {
			fb[y * pitch + x] = 0xFFFF0000;
			fb[(h - 40 + y) * pitch + (w - 40 + x)] = 0xFF00FF00;
		}
}

void merlin_main(uint64_t dtb)
{
	/* Kill the watchdog fuse FIRST: from here on any death is a frozen
	 * screen (no reboot), which is the observable. A ~25 s reset loop
	 * after this build means we never executed past start.S. */
	merlin_wdt_stop();

	/* Color ladder for the post-entry stages (last color on screen marks
	 * the stage that died; the fuse is off, so it stays for photographing):
	 *   MAGENTA - C entry reached, painting the dts-default framebuffer
	 *             (no DTB touched yet, nothing before it can fault on a
	 *             bad pointer)
	 *   GREEN   - LK DTB parsed, painting the live framebuffer address
	 *   RED     - full banner, payload loading
	 */
	con_init(MERLIN_FB_FALLBACK, MERLIN_FB_W, MERLIN_FB_H, MERLIN_FB_STRIDE);
	con_clear(MAGENTA);

	uint64_t fb = merlin_fb_base(dtb);
	con_init(fb, MERLIN_FB_W, MERLIN_FB_H, MERLIN_FB_STRIDE);
	con_clear(GREEN);

	con_clear(RED);
	paint_ruler();
	con_str("MERLIN", "shim up (toprgu stopped)");
	con_hex2("DTB", "at=", (uint32_t)dtb, "magic=", dtb ? *(volatile uint32_t *)dtb : 0);
	con_hex2("FB", "at=", (uint32_t)fb, "geom=",
		 (MERLIN_FB_W << 16) | MERLIN_FB_H);
	con_hex2("MPIDR", "val=", (uint32_t)mpidr(), "frq=", (uint32_t)cntfrq());
	con_hex2("RD", "fb=", (uint32_t)merlin_ramdisk(dtb), "initrd=", 0);
	con_skip();
	mem_lines = 0;
	con_str("MEMMAP", "LK DTB memory map:");
	con_skip();
	fdt_walk_mem(dtb, mem_cb, 0);
	con_skip();

	const char *why = loader_boot(dtb);
	con_str("LOADER", why);
	con_skip();
	con_str("HOLD", "diagnostics on screen, watchdog off");

	for (;;)
		__asm__ volatile("wfe");
}
