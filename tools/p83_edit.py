"""Regenerate 0082 + 0083 against the REAL CI-patched tree (xnu-8796.141.3
+ sweet patches 0001-0081, as shipped in the xnu-buildtree artifact).

Inputs (extracted from artifacts/buildtree/buildtree.tgz):
  xnu/osfmk/arm64/start.s       (pre-0083 state)
  xnu/pexpert/arm/pe_serial.c   (pre-0082 state)
Outputs:
  xnu/patches/0082-merlin-fbcon-live-base.patch   (regenerated)
  xnu/patches/0083-sweet-entry-color-ladder.patch (regenerated)
"""
import io, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TREE = os.path.join(REPO, 'artifacts', 'buildtree', 'xnu')
PATCHES = os.path.join(REPO, 'xnu', 'patches')
TMP = os.environ['TEMP'].replace('\\', '/')

def read(p):
    return io.open(p, encoding='utf-8', newline='').read()

def write(p, s):
    io.open(p, 'w', encoding='utf-8', newline='').write(s)

def edit(s, old, new, tag):
    assert s.count(old) == 1, "anchor not unique/missing: " + tag
    return s.replace(old, new)

# ---------- 0083: start.s ladder ----------
s = read(os.path.join(TREE, 'osfmk/arm64/start.s'))

macro = '''
/*
 * SWEET entry color ladder (merlin bring-up, patch 0083): paint the
 * framebuffer directly at early checkpoints so a photo of the panel shows
 * how far start.s gets without any console. basereg holds the PA of boot
 * args; only x4-x6 are clobbered. All three call sites run with the MMU
 * and caches off, so PA stores land in the scanned framebuffer.
 */
.macro SWEET_PAINT\tcolor, basereg
\tldr\tx4, [\\basereg, #40]\t\t// boot_args->Video.v_baseAddr
\tmov\tx5, #0x40000000\t\t\t// sanity: RAM window (merlin 0x7d9b0000 fb)
\tcmp\tx4, x5
\tb.lo\t91f
\tmov\tx5, #0x80000000
\tcmp\tx4, x5
\tb.hs\t91f
\tmov\tw5, #(\\color)
\tmov\tx6, #0x40000\t\t\t// 1 MB of words
1:\tstr\tw5, [x4], #4
\tsubs\tx6, x6, #1
\tb.ne\t1b
91:
.endm

'''

s = edit(s, ".macro MSR_VBAR_EL1_X0", macro.lstrip('\n') + ".macro MSR_VBAR_EL1_X0", "macro anchor")
s = edit(s, "LEXT(_start)\n\tb\tEXT(start_first_cpu)",
         "LEXT(_start)\n\tSWEET_PAINT\t0xff0000ff, x0\n\tb\tEXT(start_first_cpu)", "_start")
s = edit(s, "\tmov\t\tx20, x0\n\tmov\t\tx21, #0\n",
         "\tmov\t\tx20, x0\n\tmov\t\tx21, #0\n\n\tSWEET_PAINT\t0xff00ff00, x20\n", "sfc")
s = edit(s, "\t// Enable caches, MMU, ROP and JOP",
         "\tSWEET_PAINT\t0xffffff00, x20\n" + "\t// Enable caches, MMU, ROP and JOP", "mmu")
write(TMP + '/p83/start_new.s', s)

# ---------- 0082: pe_serial.c live OVL base ----------
c = read(os.path.join(TREE, 'pexpert/arm/pe_serial.c'))

anchor = "static uint32_t fbcon_width, fbcon_height, fbcon_stride;"
assert c.count(anchor) == 1, "0082 decl anchor"

live = '''
/* merlin: the panel scans ONE contiguous 1088x2340 buffer whose base the
 * OVL layer-0 address register holds at handoff (LK leaves it pointing at
 * the live scan buffer). Read it at probe time; the ADT "reg" is only the
 * fallback for boards without the OVL (sweet/QEMU). */
#define FBCON_OVL0_BASE\t0x1400b000UL
#define FBCON_OVL_L0_ADDR\t(FBCON_OVL0_BASE + 0xf40)

static uint32_t
fbcon_live_base(void)
{
\tvolatile uint32_t const *ovl = (volatile uint32_t const *)
\t    ml_io_map_wcomb(FBCON_OVL0_BASE, 0x1000UL);
\tif (ovl != NULL) {
\t\tuint32_t a = ovl[0xf40 / 4];
\t\tif (a >= 0x40000000UL && a < 0x80000000UL && (a & 7) == 0) {
\t\t\treturn a;
\t\t}
\t}
\treturn 0;
}
'''
c = edit(c, anchor, anchor + live, "0082 live fn")

old = '''\tfbcon_base = (volatile uint32_t *)ml_io_map_wcomb(reg[0], reg[1]);'''
assert c.count(old) == 1, "0082 assign anchor"
new = '''\t{
\t\tuint32_t live = fbcon_live_base();
\t\tif (live) {
\t\t\tfbcon_base = (volatile uint32_t *)
\t\t\t    ml_io_map_wcomb(live, fbcon_height * fbcon_stride);
\t\t}
\t}
\tif (fbcon_base == NULL) {
\t\tfbcon_base = (volatile uint32_t *)ml_io_map_wcomb(reg[0], reg[1]);
\t}'''
c = edit(c, old, new, "0082 assign")
write(TMP + '/p83/pe_serial_new.c', c)

# ---------- generate diffs via git diff --no-index ----------
work = TMP + '/p83/gen'
subprocess.run(['rm', '-rf', work], check=True)
subprocess.run(['mkdir', '-p', work + '/a/osfmk/arm64', work + '/a/pexpert/arm',
                work + '/b/osfmk/arm64', work + '/b/pexpert/arm'], check=True)

import shutil
shutil.copy(os.path.join(TREE, 'osfmk/arm64/start.s'), work + '/a/osfmk/arm64/start.s')
shutil.copy(os.path.join(TREE, 'pexpert/arm/pe_serial.c'), work + '/a/pexpert/arm/pe_serial.c')
shutil.copy(TMP + '/p83/start_new.s', work + '/b/osfmk/arm64/start.s')
shutil.copy(TMP + '/p83/pe_serial_new.c', work + '/b/pexpert/arm/pe_serial.c')

def gen(a, b, out):
    r = subprocess.run(['git', 'diff', '--no-index', '--src-prefix=a/', '--dst-prefix=b/',
                        work + a, work + b], capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    txt = r.stdout
    txt = txt.replace('a/' + work[3:] + a[1:], 'a' + a[1:]) if False else txt
    # rewrite paths: strip the temp prefix
    marker = '/p83/gen/'
    i = txt.index('diff --git')
    lines = txt.splitlines(True)
    out_lines = []
    for ln in lines:
        if ln.startswith('diff --git') or ln.startswith('index '):
            continue
        if ln.startswith('--- '):
            ln = '--- ' + ln[4:].split(marker, 1)[1] + '\n'
        elif ln.startswith('+++ '):
            ln = '+++ ' + ln[4:].split(marker, 1)[1] + '\n'
        out_lines.append(ln)
    write(out, ''.join(out_lines))

gen('/a/osfmk/arm64/start.s', '/b/osfmk/arm64/start.s',
    os.path.join(PATCHES, '0083-sweet-entry-color-ladder.patch'))
gen('/a/pexpert/arm/pe_serial.c', '/b/pexpert/arm/pe_serial.c',
    os.path.join(PATCHES, '0082-merlin-fbcon-live-base.patch'))
print('patches regenerated')
