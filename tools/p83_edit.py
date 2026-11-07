"""One-off: insert the SWEET_PAINT macro + 3 checkpoints into a start.s copy."""
import io, os

tmp = os.environ['TEMP'].replace('\\', '/')
p = tmp + "/p83/new/start.s"
s = io.open(p, encoding='utf-8', newline='').read()

macro = '''
/*
 * SWEET entry color ladder (merlin bring-up, patch 0083): paint the
 * framebuffer directly at early checkpoints so a photo of the panel shows
 * how far start.s gets without any console. basereg holds the PA of boot
 * args; only x4-x6 are clobbered. All three call sites run with the MMU
 * and caches off, so PA stores land in the scanned framebuffer.
 */
.macro SWEET_PAINT	color, basereg
	ldr	x4, [\\basereg, #40]		// boot_args->Video.v_baseAddr
	mov	x5, #0x40000000			// sanity: RAM window (merlin 0x7d9b0000 fb)
	cmp	x4, x5
	b.lo	91f
	mov	x5, #0x80000000
	cmp	x4, x5
	b.hs	91f
	mov	w5, #(\\color)
	mov	x6, #0x40000			// 1 MB of words
1:	str	w5, [x4], #4
	subs	x6, x6, #1
	b.ne	1b
91:
.endm

'''

anchor = ".macro MSR_VBAR_EL1_X0"
assert s.count(anchor) == 1, "macro anchor"
s = s.replace(anchor, macro.lstrip('\n') + anchor)

old = "LEXT(_start)\n\tb\tEXT(start_first_cpu)"
assert s.count(old) == 1, "_start anchor"
s = s.replace(old, "LEXT(_start)\n\tSWEET_PAINT\t0xff0000ff, x0\n\tb\tEXT(start_first_cpu)")

old = "\tmov\t\tx20, x0\n\tmov\t\tx21, #0\n"
assert s.count(old) == 1, "start_first_cpu anchor"
s = s.replace(old, old + "\tSWEET_PAINT\t0xff00ff00, x20\n")

old = "\t// Enable caches, MMU, ROP and JOP"
assert s.count(old) == 1, "common_start anchor"
s = s.replace(old, "\tSWEET_PAINT\t0xffffff00, x20\n" + old)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print("edited ok")
