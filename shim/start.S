/*
 * sweet boot shim entry: arm64 Linux Image header so Qualcomm ABL treats
 * us like a kernel. ABL enters at EL1, MMU/D-cache off, x0 = DTB pointer.
 */
	.section .text.head, "ax"
	.globl _head
_head:
	b	_start			/* code0 */
	.long	0			/* code1 */
	.quad	0			/* text_offset */
	.quad	_end			/* image_size (linked at 0) */
	.quad	0xa			/* flags: LE, 4K pages, place anywhere */
	.quad	0			/* res2 */
	.quad	0			/* res3 */
	.quad	0			/* res4 */
	.ascii	"ARM\x64"		/* magic */
	.long	0			/* res5 (PE offset) */

	.text
	.globl _start
_start:
	/* Kill the toprgu watchdog as the very first action, before any
	 * state is touched: if LK armed it, nothing else matters until it
	 * is dead. LK itself pets toprgu, so its page tables cover
	 * 0x10007000 and this store works even with the MMU still on.
	 * After this store a ~25 s reset loop is physically impossible
	 * unless our first instruction never executed. */
	movz	x2, #0x7000
	movk	x2, #0x1000, lsl #16	/* x2 = 0x10007000 (toprgu MODE) */
	ldr	w3, [x2]
	bic	w3, w3, #1		/* clear ENABLE, write-key in top byte */
	orr	w3, w3, #0x22000000
	str	w3, [x2]
	dsb	sy
	msr	daifset, #0xf
	/* State-agnostic entry: Qualcomm ABL jumps with MMU and caches off,
	 * MTK LK may jump with them still on (LK runs with the MMU enabled).
	 * Everything below assumes the ABL state, so normalize first. */
	mrs	x2, sctlr_el1
	tbnz	x2, #0, mmu_on_entry
1:	mov	x19, x0			/* DTB pointer from ABL */
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	/* zero .bss */
	adr	x1, _bss_start
	adr	x2, _bss_end
2:	cmp	x1, x2
	b.hs	3f
	str	xzr, [x1], #8
	b	2b
3:	mov	x0, x19
	bl	shim_main
4:	wfe
	b	4b

mmu_on_entry:
	/* Clean+invalidate the whole D-cache by set/way so no dirty line
	 * from LK's cacheable view survives the cache-off, then disable
	 * MMU | C | I, drop the TLB and the I-cache. Clobbers x1-x7. */
	bl	cache_clean_inv_all
	mrs	x2, sctlr_el1
	bic	x2, x2, #(1 << 0)	/* M  */
	bic	x2, x2, #(1 << 2)	/* C  */
	bic	x2, x2, #(1 << 12)	/* I  */
	msr	sctlr_el1, x2
	isb
	tlbi	vmalle1
	dsb	sy
	ic	iallu
	dsb	sy
	isb
	b	1b

/* Clean+invalidate the entire D-cache by set/way (ARMv8, EL1).
 * Operand format: level<<1 | set<<line_shift | way<<way_shift.
 * Clobbers x0-x12; returns with all levels up to LoC flushed. */
	.globl cache_clean_inv_all
cache_clean_inv_all:
	mrs	x0, clidr_el1
	ubfx	x3, x0, #24, #3		/* LoC: level of coherence */
	cbz	x3, 9f
	mov	x10, #0			/* level, 0-based */
1:	add	x2, x10, x10, lsl #1	/* 3*level */
	add	x2, x2, #1
	lsr	x1, x0, x2
	and	x1, x1, #7		/* cache type at this level */
	cmp	x1, #2
	b.lt	8f			/* none / instruction-only */
	lsl	x7, x10, #1
	msr	csselr_el1, x7		/* CSSELR: level<<1 */
	isb
	mrs	x1, ccsidr_el1
	and	x2, x1, #7
	add	x2, x2, #4		/* log2(line bytes) */
	ubfx	x4, x1, #3, #10		/* associativity - 1 */
	clz	w5, w4			/* way shift (32-bit count!) */
	ubfx	x6, x1, #13, #15	/* number of sets - 1 */
	mov	x8, #0			/* set counter */
2:	mov	x9, x4			/* way counter (ways-1) */
3:	lsl	x7, x9, x5
	lsl	x12, x10, #1
	orr	x11, x12, x7		/* level<<1 | way<<way_shift */
	lsl	x7, x8, x2
	orr	x11, x11, x7		/* | set<<line_shift */
	dc	cisw, x11
	subs	x9, x9, #1
	b.ge	3b
	add	x8, x8, #1
	cmp	x8, x6
	b.le	2b
8:	add	x10, x10, #1
	subs	x3, x3, #1
	b.gt	1b
	dsb	sy
9:	ret

/* PSCI CPU_ON target. x0 = context id = cpu index (1..7). */
	.globl secondary_entry
secondary_entry:
	msr	daifset, #0xf
	msr	spsel, #1
	adr	x1, _sec_stacks
	add	x1, x1, x0, lsl #12
	add	x1, x1, #0x1000
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	bl	secondary_main
4:	wfe
	b	4b

/*
 * Exception vectors. Each slot stashes x29/x30, loads its slot number
 * and jumps to the common path, which saves x0-x28 and calls
 * exc_handler(slot, regs). IRQs return; everything else ends in the
 * on-screen panic.
 */
.macro vent slot
	.balign	0x80
	stp	x29, x30, [sp, #-16]!
	mov	x29, #\slot
	b	exc_common
.endm

	.balign	0x800
	.globl vectors
vectors:
	vent 0
	vent 1
	vent 2
	vent 3
	vent 4
	vent 5
	vent 6
	vent 7
	vent 8
	vent 9
	vent 10
	vent 11
	vent 12
	vent 13
	vent 14
	vent 15

exc_common:
	sub	sp, sp, #(30 * 8)
	stp	x0, x1, [sp, #0]
	stp	x2, x3, [sp, #16]
	stp	x4, x5, [sp, #32]
	stp	x6, x7, [sp, #48]
	stp	x8, x9, [sp, #64]
	stp	x10, x11, [sp, #80]
	stp	x12, x13, [sp, #96]
	stp	x14, x15, [sp, #112]
	stp	x16, x17, [sp, #128]
	stp	x18, x19, [sp, #144]
	stp	x20, x21, [sp, #160]
	stp	x22, x23, [sp, #176]
	stp	x24, x25, [sp, #192]
	stp	x26, x27, [sp, #208]
	str	x28, [sp, #224]
	mov	x0, x29
	mov	x1, sp
	bl	exc_handler
	ldp	x0, x1, [sp, #0]
	ldp	x2, x3, [sp, #16]
	ldp	x4, x5, [sp, #32]
	ldp	x6, x7, [sp, #48]
	ldp	x8, x9, [sp, #64]
	ldp	x10, x11, [sp, #80]
	ldp	x12, x13, [sp, #96]
	ldp	x14, x15, [sp, #112]
	ldp	x16, x17, [sp, #128]
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldr	x28, [sp, #224]
	add	sp, sp, #(30 * 8)
	ldp	x29, x30, [sp], #16
	eret
