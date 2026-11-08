# ios-merlin-merlin-2

**Apple's iOS 16 kernel booting on a Redmi Note 9.**

This project ports Apple's open-source XNU kernel (xnu-8796, the iOS 16 generation) to the Xiaomi Redmi Note 9 (`merlin`, MediaTek MT6768 / Helio G85). The end goal is the same as the upstream [ios-sweet](https://github.com/dipa-studio/ios-sweet) port it builds on: the **unmodified iOS 16.7.16 (20H392) userland of the iPhone X** — launchd, the system daemons, backboardd, SpringBoard — running on Android phone hardware.

The baseline is the upstream `dipa-studio/ios-sweet` tree (generic non-PAC arm64 XNU bring-up, patch series 0001–0081). The merlin-specific layer is **remade from first principles** in this repo: a fresh MT6768 shim, a fresh Apple Device Tree, a fresh boot-image packer, and merlin kernel patches (0082+). The older merlin work in other forks is retired and deliberately not used.

As of **2026-11-08** the full boot chain executes on the phone and **the Darwin kernel boots deep into the system**: through `kernel_bootstrap` (scheduler, IPC, VM, OSLog, KDP) and into the `bsd_init` / IOKit-start era, with a text console on the phone's own display. There is no userland yet — storage and timer-interrupt milestones come first (see below).

> Experimental kernel bring-up, not a usable phone OS. Nothing here is a phone you can use: no apps, no GUI, no radio. Apple's iOS itself is not distributed in this repo.

## What works

| Area | State |
| --- | --- |
| Boot | Stock preloader → LK → our boot.img in the boot partition → shim → XNU. Bootloader/recovery/modem/persist partitions are never touched; the boot partition is restored from backup after testing |
| Shim | Kills the toprgu watchdog first (frozen screen instead of a reset loop), console on the LK splash framebuffer, payload discovery, kernel copy, EL2→EL1 drop |
| Kernel | XNU executes: entry ladder → MMU on → `kernel_bootstrap` complete → `bsd_init` / IOKit start. `iBoot version: merlin-shim` in the boot log — Darwin reads our shim's identity |
| Console | Kernel text on the panel (fbcon). No serial port on this board — **the screen is the UART**; a photo of the display is the log |
| Display | LK's panel stays alive through the handoff; 1080×2340 at a 4352-byte pitch; console clears and restarts at the top on wrap so the newest output is always at the bottom |
| Faults | Shim-installed exception vectors: any pre-kernel fault paints a blue PANIC screen with ESR/ELR/FAR/SPSR/HCR and a stage marker naming the failing step |
| CPU | One core (the boot Cortex-A55), 16K pages, GICv3 |
| CI | Kernel builds on GitHub's macOS runners; QEMU smoke test boots each green kernel automatically |

## What does not work (yet)

- **Timer interrupts.** The current wall: kernel output stops where the first timeout-based wait needs the virtual-timer PPI (INTID 27) to fire. The GICR readback/probe patch (0088) is built; its flash test (`v50`) is pending. Boot stops silently after the IOKit/battery lines.
- **Storage.** No eMMC (MSDC) driver yet — milestone M2. The 16 GiB HFS+ iOS root image is already built and staged, but the kernel cannot read it until MSDC exists.
- **SMP** (secondary cores via PSCI), touch, buttons, USB, Wi-Fi, audio, camera: later milestones.
- **No userland at all**: no launchd, no SpringBoard. This repo has not reached the upstream sweet milestone chain yet (that port boots to the iOS home screen on a Redmi Note 10 Pro — the goal here is to walk the same path on merlin).

## How it boots

```
preloader → LK (MediaTek little kernel, AArch32)
  → ATF "K64" SMC handoff (delivers the kernel at EL2!)
    → boot.img v2: gzip(shim) kernel slot + SWEETXNU payload ramdisk + stock merlin DTB
       → shim: stop toprgu watchdog → save DTB ptr → purge LK's dirty D-cache lines
         → MMU/caches off → console on the LK framebuffer → find payload in the ramdisk
         → copy kernel segments to 0x50000000 → boot_args + ADT
         → ERET drop EL2→EL1 with HCR_EL2.RW=1 (the ERET is illegal without it)
            → XNU: entry ladder (0083) → MMU on → fbcon on the live OVL framebuffer (0082)
               → kernel_bootstrap → bsd_init → IOKit start → (current wall: timer PPI)
```

### Hard-won boot-format rules (merlin)

1. **The kernel slot must be gzip-compressed.** MediaTek LK gunzips the kernel slot; a raw slot is rejected before the shim's first instruction (six bootloops taught us this).
2. **The boot.img header is cloned verbatim from the stock firmware** (all 1660 bytes) with only the three size fields patched.
3. **vbmeta**: after any stock reflash, verification comes back on. Xiaomi's LK honors AVB flag **bits 24/25 at byte offset 123** — patch those, not the standard AVB bits.
4. **`fastboot boot` is not supported on this unit.** The test path is flashing the boot partition (keeping backups) and restoring afterwards.

## How to do it yourself

You need a Redmi Note 9 (`merlin`, MT6768) with an **unlocked bootloader**, a Linux PC, and a GitHub account for the kernel build (public forks get free macOS minutes). Kernels come from this repo's GitHub Actions only — a local cross-compiler produced broken kernels and is banned.

### 0. Back up the phone first

Boot TWRP (temporarily) with adb root and pull at least `boot`, `recovery`, `vbmeta`, `modemst1`, `modemst2`, `fsg`, `fsc`, `persist`. They contain per-device calibration data. Keep them out of git (`.gitignore` covers `backup/`, `dtb/`, `recovery/`). The stock ROM's `boot.img` (from the official fastflash package) is the real restore image — the phone's boot partition holds test images during bring-up.

Patch vbmeta per rule 3 above (your `patch-vbmeta.py`), then every build in this README is: `fastboot flash boot out/shim-boot-merlin-*.img`, watch/photograph the screen, restore when done.

### 1. Build the kernel (CI)

```sh
gh workflow run xnu.yml -R YOU/ios-merlin-merlin-2
gh run download RUN_ID -R YOU/ios-merlin-merlin-2 -n xnu-kernel -D xnu/out
```

The workflow fetches xnu-8796 via [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build), applies `xnu/patches/` in order (staging libpthread/HFS/BearSSL), installs a sha256-verified KDK, and **fails the run if any numbered patch is silently skipped** (a real class of bug here — see NOTES.md 2026-11-07). A packaged build tree is attached for local single-file compile checks via `tools/xnu-cc.py`.

### 2. Build the shim (CI) and the QEMU smoke test

`shim.yml` cross-builds the merlin shim (artifact `merlin-shim`). `qemu.yml` runs automatically after each green xnu build: it builds a QEMU-ADT payload and boots it on QEMU `virt`, capturing the framebuffer console. QEMU passing while the phone fails cleanly separates kernel-binary bugs from hardware/entry-state issues.

### 3. Package the boot image

```sh
python3 tools/mkadt-merlin.py out/merlin.adt
python3 tools/mkpayload.py xnu/out/kernel.development.sweet out/merlin.adt out/payload.bin \
    --cmdline 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress'
python3 tools/mkbootimg-merlin.py out/shim-boot-merlin.img \
    --kernel shim-merlin.bin --ramdisk out/payload.bin \
    --dtb dtb/stock-merlin.dtb --clone-header backup/stock-boot.img
```

`mkbootimg-merlin.py` gzips the kernel slot (rule 1) and clones the stock header (rule 2). Boot slots: kernel 0x40080000, ramdisk 0x47c80000, page 2048. The stock DTB is a device artifact (pulled from the phone, kept out of git).

### 4. Flash and observe

```sh
fastboot flash boot out/shim-boot-merlin.img
# ...watch the panel: red MERLIN banner = shim; text lines = XNU; blue PANIC = fault captured
```

There is no serial port. Take a photo of the screen; the console's clear-on-wrap behavior keeps the newest 73 lines visible in order. `tools/sweet-crash.py` symbolicates console crash reports against the kernel artifact when you get that far.

### 5. The iOS root image (staged for M2)

Built with the upstream sweet toolchain from the iPhone X (iPhone10,3) iOS 16.7.16 (20H392) IPSW:

```sh
tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root.img 16G
sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot     # after mounting (see upstream README)
img2simg ios16-root.img ios16-root.simg
fastboot flash -S 512M userdata ios16-root.simg          # erases Android userdata!
```

The merlin kernel cannot mount it yet (no MSDC driver — M2), so flashing it now is pointless. Known gaps vs the sweet images: no mobileactivationd data ark, no USB-network preferences.

## Repository layout

| Path | What |
| --- | --- |
| `shim/` | Bare-metal boot shim (C + asm) packed as an Android boot.img v2 |
| `shim/merlin.c`, `shim/merlin.h` | The MT6768 bring-up: toprgu stop, LK framebuffer console, payload discovery |
| `shim/build-ci.sh` | CI cross-build of the merlin shim (`build.sh` is the legacy sweet/host-render path) |
| `xnu/patches/` | The XNU patch series: 0001–0081 upstream sweet + the merlin layer (0082+), applied in order by CI |
| `.github/workflows/xnu.yml` | Kernel CI build (macOS runner, patch-skip guard, verified KDK) |
| `.github/workflows/shim.yml` | Shim cross-build (ubuntu) |
| `.github/workflows/qemu.yml` | QEMU smoke test after each green kernel |
| `tools/mkadt-merlin.py` | Generates the merlin Apple Device Tree (GICv3, 13 MHz timer, fbcon, iPhone X identity) |
| `tools/mkbootimg-merlin.py` | The merlin boot v2 packer (gzip kernel slot, stock header clone) |
| `tools/validate-repo.py` | Repo integrity checks (patch sequence incl. reverted numbers, script syntax) |
| `tools/mkpayload.py` | Packs kernel + ADT + boot-args into the SWEETXNU payload |
| `tools/mkiosroot.sh`, `sweet-root-tweaks.py` | Upstream sweet root-image toolchain (used for the staged merlin root) |
| `tools/qemu-sweet.py` | QEMU harness (qemu.yml derives a merlin-geometry twin at run time) |
| `tools/xnu-cc.py` | Local single-file compile check from a CI log |
| `tools/unpack_bootv2.py`, `remotezip.py`, `adt.py`, `sparsediff.py` | Helpers |
| `NOTES.md` | The engineering log: every boot, crash, root cause and decision. Read this first |
| `AGENTS.md` | Working rules (builds from CI only, device safety, commit discipline) |

Not in git: partition backups, the stock/live DTBs, recovery images, Apple firmware, root images, and build trees (device serials and calibration data, or Apple's copyrighted files).

## Kernel patches

| # | What |
| --- | --- |
| 0001–0081 | The upstream ios-sweet series (see its README): toolchain compatibility, SWEET machine config (generic non-PAC arm64), early framebuffer console, PRNG, device-tree platform expert, mockfs RAM-disk root, HFS+, the Qualcomm UFS driver (unused on merlin — eMMC here), AMFI/sandbox relaxations, IOSurface, HID, SMP-PSCI, diagnostics |
| 0082 | **merlin fbcon live base**: the kernel console reads the panel's actual fetch address from the OVL layer-0 register (ADT `reg` is the fallback) |
| 0083 | Entry color ladder in `start.s`: BLUE at `_start`, GREEN after boot-args handoff, YELLOW before MMU enable — bisects pre-console deaths |
| 0085 | Careful subsystem-transition trace (one line per `STARTUP_SUB_*`; 0084's fuller trace regressed and was reverted) |
| 0087 | fbcon clears and restarts at the top on wrap (0086's scroll tore on this panel and was reverted) |
| 0088 | **GIC boot probe**: redistributor/CPU-interface readback + a one-shot virtual-timer pending test — decides the next fix for the timer wall |

(0084 and 0086 were reverted; their numbers are retired, never reused.)

## Key hardware facts (merlin / MT6768)

- SoC: MediaTek MT6768 (Helio G85): 2× Cortex-A75 @ 2.171 GHz + 6× Cortex-A55 @ 1.701 GHz, ARMv8.2, **no PAC**. Boot MPIDR `0x81000000`.
- GICv3: GICD `0x0c000000`/0x40000, GICR `0x0c040000`/0x200000 (Linux's `arm,gic-v3` node — the legacy `gic_cpu@0c400000` node reads all-ones for NS and is a decoy). Timer via Group-1 IRQ, not FIQ.
- Timer: arch timer, virtual-timer PPI → **INTID 27**, CNTFRQ **13 MHz** (measured `0x00C65D40`).
- PSCI 1.0 via `smc` (MTK ATF bl31). ATF's "K64" handoff delivers the OS at **EL2** — the shim ERETs to EL1 with `HCR_EL2.RW=1`.
- Watchdog: toprgu at `0x10007000` (wdt_v2 keyed writes) — stopped by the shim's first instructions, or the box resets mid-boot.
- Display: LK splash panel stays alive; the panel fetches ONE contiguous 1088×2340 buffer at the **OVL L0 address register** (`0x1400bf40`, read live; 0x7D9B0000 observed) with pitch 4352 bytes. The `atag,videolfb` pointer (0x7e605000) is LK's logo buffer, not the scan address. Never write MEM_SRC_PITCH or the OVL CON registers.
- Storage: eMMC 5.1 on MSDC0 — the Qualcomm UFS driver does not apply; M2 is a fresh MSDC driver.
- USB: MTK musb-family USB 2.0 device controller at `0x11200000` (later milestone).
- RAM: 4 GB LPDDR4X from `0x40000000` (stock DTB `/memory` size `0x3e605000` — it ends exactly at the LK framebuffer). The kernel band is `0x50000000`+`0x2e000000`, clear of the shim, ramdisk and framebuffer.
- Boot chain: preloader → LK (AArch32) → boot.img v2 (base 0x40078000, kernel 0x40080000, ramdisk 0x47c80000, page 2048, kernel slot gzipped).

More — with sources, per-build results and root-cause analyses — in [`NOTES.md`](NOTES.md).

## Credits

Built on the upstream [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) port (itself: Apple's open-source releases — xnu, IOHIDfamily, libpthread, hfs — BearSSL, [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build), [ipsw](https://github.com/blacktop/ipsw)), plus Xiaomi's published GPL kernel sources for the MT6768 hardware details and TWRP for device access. iOS itself is Apple's and is not distributed here.
