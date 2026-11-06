#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that the MERLIN xnu needs to boot.

MERLIN = Redmi Note 9 (`merlin`, Xiaomi/MediaTek MT6768 / Helio G85, 8 cores:
6x Cortex-A55 + 2x Cortex-A75, ARMv8.2, no PAC). The kernel is still built
with MACHINE_CONFIG=SWEET (the generic non-PAC arm64 bring-up), so the
platform-expert matching contract and /arm-io layout stay the same; every
hardware fact below is merlin's, sourced from the device's own Android
kernel tree (arch/arm64/boot/dts/mediatek/mt6768.dts, merlin.dts) and the
LK-injected runtime DTB.

Layout for the RAM-disk milestone (M1):
  - The shim runs where LK loaded it (0x40080000), the boot.img ramdisk sits
    at 0x47c08000 and the LK splash framebuffer at 0x7e605000. The kernel is
    therefore loaded and managed at 0x50000000 .. 0x7e000000 (464 MiB).
    M2+ widens this from the live DTB /memory node.
  - The LK framebuffer (0x7e605000, panel 1080x2340) must stay outside the
    kernel band: the kernel's fbcon (ADT node sweet-fbcon) and boot_args
    Video both point there.

Usage:  mkadt-merlin.py OUT.adt [--dump]
"""
import hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# Kernel-managed RAM for M1: clear of the shim (0x40080000), the boot.img
# ramdisk (0x47c08000 + payload size) and the LK framebuffer (0x7e605000).
PHYS_BASE = 0x50000000
MEM_SIZE = 0x2e000000
# Panic log buffer carved from the TOP of the managed range, exposed as
# /pram + /chosen/embedded-panic-log-size (see upstream mkadt.py comment).
PANIC_LOG_SIZE = 0x100000
# /arm-io children are relative to this; must not be 0 (serial_init bails)
SOC_BASE = 0x01000000

# mt6768.dts: arm,gic-v3; distributor 0x0c000000 (0x40000), one
# redistributor region 0x0c040000 (0x200000, 8 PEs). Runtime DTB timer node:
# vtimer PPI 11 -> INTID 27, clock-frequency 0xc65d40 = 13 MHz.
GICD, GICD_SIZE = 0x0c000000, 0x40000
GICR, GICR_SIZE = 0x0c040000, 0x200000
VTIMER_INTID = 27
TIMEBASE = 13000000

# LK splash framebuffer: merlin.dts /chosen atag,videolfb-fb_base_l (the dts
# default; LK patches the live value at boot — cross-check on first boot).
FB, FB_SIZE = 0x7e605000, 0x17e8000
FB_W, FB_H, FB_STRIDE = 1080, 2340, 1080 * 4

# merlin.dts cpus: reg 0x000..0x700 (Aff1:Aff0), A55 1.701 GHz, A75 2.171 GHz
A55_FREQ = 1701000000
A75_FREQ = 2171000000
N_CPUS = 8

# Synthetic ECID 'MERL'+1 (not the phone's); chip-id of the A11 the iPhone X
# userland expects (same identity strategy as the sweet port).
MERLIN_ECID = 0x4D45524C00000001
CHIP_ID = 0x8015

BOOT_MANIFEST_HASH = hashlib.sha384(b'merlin boot manifest').digest()

# The iOS userland is the iPhone X (iPhone10,3 / D22AP) IPSW, exactly like
# the sweet port: MobileGestalt derives product type/device class/UI style
# from the root identity and /product of the real D22AP device tree (Apple
# artifact, kept out of git; extract with tools/remotezip.py + ipsw).
D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt')


def d22ap_product(path=D22AP_ADT):
    """/product properties of the real D22AP tree (see upstream mkadt.py)."""
    if not os.path.exists(path):
        print(f'warning: {path} missing, no /product node', file=sys.stderr)
        return None
    root, _ = adt.parse(open(path, 'rb').read())
    for c in root.children:
        if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
            return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    raise SystemExit(f'{path}: no /product node')


u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None):
    phys_base, mem_size = PHYS_BASE, MEM_SIZE
    # Panic log carved off the top so the kernel never allocates over it.
    panic_base = phys_base + mem_size - PANIC_LOG_SIZE
    mem_size -= PANIC_LOG_SIZE
    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('embedded-panic-log-size', u32(PANIC_LOG_SIZE)),
        ('firmware-version', cstr('merlin-shim')),
        ('system-firmware-version', cstr('merlin-shim')),
        # iBoot stand-ins carried over from the sweet port (same iOS
        # userland): mount -P 1 boot manifest, libimg4 crypto algorithm.
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        ('crypto-hash-method', cstr('sha2-384')),
        # MobileGestalt screen class: 1080x2340 @3x = 360x780 points.
        ('display-scale', u32(3)),
        # IOPlatformUUID from a synthetic ECID (not the phone's) + A11 chip-id.
        ('unique-chip-id', struct.pack('<Q', MERLIN_ECID)),
        ('chip-id', u32(CHIP_ID)),
        # Dev-fused, undemoted security tuple (same as sweet; see mkadt.py).
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        # SIP relaxed (kern_csr.c); unauthenticated root; see upstream comment.
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])

    # CPU order = the device DT reg order (0x000..0x700): cpu0-5 A55, 6-7 A75.
    # reg is the actual MPIDR Aff1:Aff0 per the runtime DTB (MPIDR encodings
    # are re-verified on hardware before SMP work; single-CPU M1 only needs
    # cpu0 to match the boot core).
    cpu_nodes = []
    for core in range(N_CPUS):
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('mediatek,mt6768') + cstr('ARM,v8')),
            ('reg', u32(core << 8)),
            ('cpu-id', u32(core)),
            ('cluster-id', u32(0 if core < 6 else 1)),
            ('cluster-type', u32(0)),
            ('die-cluster-id', u32(0 if core < 6 else 1)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(core)),
            ('l3-cache-id', u32(0)),
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(TIMEBASE)),
            ('clock-frequency', u32(A75_FREQ if core >= 6 else A55_FREQ)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(TIMEBASE)),
            ('fixed-frequency', u32(TIMEBASE)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(VTIMER_INTID)),
        ('reg', u64(gicd - SOC_BASE, GICD_SIZE, gicr - SOC_BASE, GICR_SIZE)),
    ])
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('merlin-io')),
        ('compatible', cstr('merlin-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        # watchdogd reads /arm-io/wdt no-pmu (no PMU stage on this bring-up).
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        # Main display node (IOMobileFramebuffer counts these /arm-io
        # children; native panel geometry for M1).
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('merlin,display')),
            ('canvas-width', u32(FB_W)),
            ('canvas-height', u32(FB_H)),
        ])])

    # Kernel framebuffer console = the LK splash framebuffer (same address
    # the shim console draws to; panel stays alive through the handoff).
    fbcon = node('sweet-fbcon', [
        ph(),
        ('reg', u64(FB, FB_SIZE)),
        ('width', u32(FB_W)),
        ('height', u32(FB_H)),
        ('stride', u32(FB_STRIDE)),
    ])

    # No effaceable storage: keybagd reads systembag.kb as a plain plist.
    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    # MobileGestalt HomeButtonType (D22AP: 2, no Home button).
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    product_props = d22ap_product()
    product = [node('product', [ph()] + product_props)] if product_props else []

    pram = node('pram', [ph(), ('reg', u64(panic_base) + u64(PANIC_LOG_SIZE))])

    # Identity of the iPhone X userland + merlin platform strings. The
    # kernel binary is the SWEET machine config, whose platform expert
    # matches 'xiaomi,sweet' — that string stays until the merlin platform
    # patch replaces the match list.
    return node('device-tree', [
        ph(),
        ('compatible', cstr('D22AP') + cstr('iPhone10,3') + cstr('xiaomi,merlin')
         + cstr('xiaomi,sweet') + cstr('mediatek,mt6768') + cstr('AppleARM')),
        ('model', cstr('iPhone10,3')),
        ('target-type', cstr('D22')),
        ('target-sub-type', cstr('D22AP')),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons, pram] + product)


if __name__ == '__main__':
    root = build()
    blob = adt.serialize(root)
    open(sys.argv[1], 'wb').write(blob)
    if '--dump' in sys.argv:
        adt.dump(adt.parse(blob)[0])
    print(f'{sys.argv[1]}: {len(blob)} bytes', file=sys.stderr)
