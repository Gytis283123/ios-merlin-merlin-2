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

/* The panel's ACTUAL fetch address: MTK OVL0 (disp_ovl0@1400b000) layer-0
 * source address register (DISP_REG_OVL_L0_ADDR = 0xf40, mt6768
 * ddp_reg_ovl.h). LK leaves it pointing at the buffer the panel is
 * scanning - which the boot ruler proved is NOT the atag videolfb address
 * (the scan window starts a few hundred rows above it; the atag pointer is
 * where LK drew the logo, not where the pipe fetches). Read the register
 * and draw there; fall back to the atag base if it looks bogus. */
#define MERLIN_OVL0_BASE	0x1400b000UL
#define MERLIN_OVL_L0_ADDR	(MERLIN_OVL0_BASE + 0xf40)
/* The primary pipe on mt6768 fetches through RDMA0 (disp_rdma0@1400d000),
 * memory mode: DISP_REG_RDMA_MEM_START_ADDR = base+0xf00 (ddp_reg_dma.h).
 * v12 proved the OVL layer address is not what the panel scans. */
#define MERLIN_RDMA0_BASE	0x1400d000UL
#define MERLIN_RDMA_MEM_START	(MERLIN_RDMA0_BASE + 0xf00)
#define MERLIN_RDMA_SRC_PITCH	(MERLIN_RDMA0_BASE + 0x02c)
#define MERLIN_OVL_L0_SRC_SIZE	(MERLIN_OVL0_BASE + 0x038)
#define MERLIN_OVL_L0_PITCH	(MERLIN_OVL0_BASE + 0x044)

static int addr_plausible(uint32_t a)
{
	return a >= 0x40000000UL && a < 0x80000000UL && (a & 7) == 0;
}

/* Prefer the RDMA fetch address, then OVL, then the atag pointer. */
static uint64_t merlin_scan_base(uintptr_t fdt, uint32_t *rdma_out,
				 uint32_t *ovl_out)
{
	uint64_t atag = merlin_fb_base(fdt);
	uint32_t rdma = rd32(MERLIN_RDMA_MEM_START);
	uint32_t ovl = rd32(MERLIN_OVL_L0_ADDR);
	*rdma_out = rdma;
	*ovl_out = ovl;
	if (addr_plausible(rdma))
		return rdma;
	if (addr_plausible(ovl))
		return ovl;
	return atag;
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
	uint32_t rdma_val = 0, ovl_val = 0;
	uint64_t scan = merlin_scan_base(dtb, &rdma_val, &ovl_val);
	/* Full geometry from the hardware: the RDMA source pitch is what the
	 * panel actually steps per line, the OVL src-size holds (h<<16)|w.
	 * v13 fixed the base; the text smear is the pitch we assumed. */
	uint32_t pitch = rd32(MERLIN_RDMA_SRC_PITCH);
	uint32_t osize = rd32(MERLIN_OVL_L0_SRC_SIZE);
	uint32_t opitch = rd32(MERLIN_OVL_L0_PITCH);
	uint32_t w = osize & 0xffff, h = osize >> 16;
	/* MEM_SRC_PITCH is in PIXELS (v14 evidence: register=1080 used as bytes
	 * shredded the text 4x wide). Convert to bytes for 32bpp; a value that
	 * already looks like bytes (>=2048) passes through. */
	if (pitch < 64 || pitch > 4096)
		pitch = MERLIN_FB_W;
	if (pitch < 2048)
		pitch *= 4;
	if (!w || w > 4096 || !h || h > 8192) {
		w = MERLIN_FB_W;
		h = MERLIN_FB_H;
	}
	con_init(scan, w, h, pitch);
	con_clear(MAGENTA);

	uint64_t fb = merlin_fb_base(dtb);
	con_init(scan, w, h, pitch);
	con_clear(GREEN);

	con_clear(RED);
	con_str("MERLIN", "shim up (toprgu stopped)");
	con_hex2("SCAN", "rdma=", rdma_val, "ovl=", ovl_val);
	con_hex2("GEOM", "pit=", pitch, "osz=", osize);
	con_hex2("GEOM2", "opit=", opitch, "wh=", (w << 16) | h);
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
