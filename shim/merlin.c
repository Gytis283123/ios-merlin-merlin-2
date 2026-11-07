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

/* Framebuffer geometry probe: paints test patterns with two candidate line
 * pitches so one photographed boot reveals the real LK framebuffer stride.
 *   LEFT half  (x < 540):  vertical stripes drawn with pitch 4320 (1080*4)
 *   RIGHT half (x >= 540): same stripes drawn with pitch 4352 (1088*4)
 * Whichever half shows straight vertical bars on the panel has the true
 * pitch; if both shear into diagonals, the slope encodes the difference.
 * Corner squares + top/bottom edge bands check the base and the height
 * mapping (vramSize hints at double buffering). */
static void paint_probe(void)
{
	volatile uint32_t *fb = con_fb;
	const uint32_t w = con_w, h = con_h;

	/* stripes: left half pitch 4320, right half pitch 4352 */
	for (uint32_t y = 0; y < h; y++) {
		volatile uint32_t *row = fb + y * (4320 / 4);
		for (uint32_t x = 0; x < 540; x += 108) {
			uint32_t c = ((x / 108) & 1) ? 0xFFFFFFFF : 0xFF000000;
			for (uint32_t dx = 0; dx < 8 && x + dx < 540; dx++)
				row[x + dx] = c;
		}
		volatile uint32_t *row2 = fb + y * (4352 / 4);
		for (uint32_t x = 540; x < w; x += 108) {
			uint32_t c = ((x / 108) & 1) ? 0xFF00FF00 : 0xFF000000;
			for (uint32_t dx = 0; dx < 8 && x + dx < w; dx++)
				row2[x + dx] = c;
		}
	}
	/* corner squares 80x80: TL white, TR yellow, BL green, BR magenta */
	const struct { uint32_t x0, y0, c; } corners[] = {
		{0, 0, 0xFFFFFFFF}, {w - 80, 0, 0xFFFFFF00},
		{0, h - 80, 0xFF00FF00}, {w - 80, h - 80, 0xFFFF00FF},
	};
	for (unsigned i = 0; i < 4; i++)
		for (uint32_t y = 0; y < 80; y++)
			for (uint32_t x = 0; x < 80; x++)
				fb[(corners[i].y0 + y) * (4320 / 4) + corners[i].x0 + x] = corners[i].c;
	/* top/bottom edge bands (8 rows) drawn with pitch 4320 */
	for (uint32_t x = 0; x < w; x++) {
		for (uint32_t y = 80; y < 88; y++) fb[y * (4320 / 4) + x] = 0xFF0080FF;
		for (uint32_t y = h - 88; y < h - 80; y++) fb[y * (4320 / 4) + x] = 0xFF0080FF;
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
	paint_probe();
	con_str("MERLIN", "shim up (toprgu stopped)");
	con_hex2("DTB", "at=", (uint32_t)dtb, "magic=", dtb ? *(volatile uint32_t *)dtb : 0);
	con_hex2("FB", "at=", (uint32_t)fb, "geom=",
		 (MERLIN_FB_W << 16) | MERLIN_FB_H);
	con_hex2("MPIDR", "val=", (uint32_t)mpidr(), "frq=", (uint32_t)cntfrq());
	con_hex2("RD", "fb=", (uint32_t)merlin_ramdisk(dtb), "initrd=", 0);
	con_skip();

	const char *why = loader_boot(dtb);
	con_str("LOADER", why);
	con_skip();
	con_str("HOLD", "diagnostics on screen, watchdog off");

	for (;;)
		__asm__ volatile("wfe");
}
