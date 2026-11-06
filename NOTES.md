# iOS 16 (XNU) on merlin (Redmi Note 9, MT6768 / Helio G85) — fresh port, working notes

## Project decision record (2026-11-06, user)

- This repo (`Gytis283123/ios-merlin-merlin-2`) is the **single source of
  truth** for the merlin port. Fresh history; the baseline is the upstream
  `dipa-studio/ios-sweet` tree (generic non-PAC arm64 XNU bring-up, patches
  0001–0081).
- The older merlin work that exists elsewhere (forks `Gytis283123/ios-merlin`
  and `Gytis283123/ios-sweet`, patches 0082–0122, packaged images in
  Downloads) is **not to be used** — not as patches, not "for assistance",
  not as images. The merlin-specific layer is being **remade from first
  principles** in this repo. Do not read or diff those patch series.
- The WSL cross-compiler (`~/xnu-cross`) is **banned by the user**: its
  kernels were broken and did not boot. Kernels come from this repo's GitHub
  Actions CI only.
- Device rule unchanged: temporary `fastboot boot` images only. Never flash
  without explicit user confirmation; keep bootloader/recovery/modem/persist
  and partition backups intact.

## Milestone plan (remake, in order)

1. **M1 — kernel executes on merlin**: upstream 0081 kernel + fresh merlin
   ADT + fresh merlin shim (MTK toprgu watchdog stop, LK framebuffer
   console, payload discovery) + HFS RAM-disk root via the existing
   mockfs path (`rd=md0`). Success = `SWEET userspace: init running as
   PID 1` visible on the panel (photo evidence).
2. **M2 — storage**: fresh MSDC eMMC block driver (`rd=msdcroot0`), read
   the iOS 16 root from userdata.
3. **M3 — SMP**: secondary CPUs via PSCI (MTK ATF bl31, `psci-1.0` smc).
4. M4+: display/touch/input drivers, then userland milestones mirror the
   upstream sweet path (Setup, SpringBoard).

## Hardware facts (merlin / MT6768) — sources

From the device's own Android kernel source tree (`D:\things\Merlin\android_kernel_xiaomi_mt6768`,
Xiaomi GPL release) and its device trees; to be re-verified against the live
DTB pulled from the phone itself:

- SoC: MediaTek MT6768 (Helio G85 family), 8 cores: 2× Cortex-A75 + 6×
  Cortex-A55, ARMv8.2, **no PAC** (plain arm64, same class as the upstream
  sweet target). ARMv8 crypto extensions available.
- GIC: **v3**, GICD `0x0c000000` (0x40000), GICR `0x0c040000` (8 PEs ×
  0x40000 stride), sysirq polarity wrapper `0x0c53a650`. Same interrupt
  architecture as sweet (GICv3 sysreg, Group-1 IRQs; TrustZone owns Group 0).
- Timer: arch timer, vtimer PPI 11 → **INTID 27**, CNTFRQ **13 MHz**
  (sweet: INTID 19 @ 19.2 MHz — the ADT/boot code carries per-target values).
- PSCI: `arm,psci-1.0`, conduit **smc** (MTK ATF bl31).
- Watchdog: MTK toprgu (wdt_v2 register map), base `0x10007000` (verify from
  live DTB). If not stopped, it resets the box mid-boot (~30 s).
- Boot: preloader → LK (MTK little-kernel ABL) → boot.img. LK passes a DTB in
  x0 (stock device tree; boot v2 images may carry a `--dtb` the LK prefers).
- Display: LK splash framebuffer at `0x7e605000` (lk atag,videolfb
  `fb_base_l`), panel hx83112b fhdp DSI cmd mode, 1080×2340. Whether LK keeps
  the panel alive when jumping to an OS image is verified on M1 boot.
- Storage: eMMC 5.1 on MSDC0 (MTK msdc controller) — not UFS; the upstream
  `sweet_ufs.c` Qualcomm driver does not apply.
- USB: MTK USB controller (mtu3 family) — not DWC3; bring-up is a later
  milestone, not needed for M1/M2.
- PMIC: MT6358 family (later milestones).
- RAM: 4 GB LPDDR4X at `0x40000000` (verify real usable band from the live
  DTB /memory node; LK patches actual DRAM at boot).

## Current state (end of session 1, 2026-11-06)

- Repo created; baseline = upstream sweet through patch 0081, force-pushed
  clean. CI workflows: `xnu.yml` (kernel, macos-15, proven 9-minute build),
  `shim.yml` (shim cross-build on ubuntu, artifact `merlin-shim`).
- Merlin-specific implementation not started yet in this repo. Next code:
  (a) merlin shim variant (`-DMERLIN`: stop toprgu before touching DTB,
  console on the LK framebuffer, payload discovery from the DTB LK passes),
  (b) `tools/mkadt.py` merlin target (GIC/timer/FB/CPU facts above),
  (c) packaging script (mkpayload + boot v2, no `--dtb` on the first test so
  LK passes its own stock tree; add stock DTB later if needed),
  (d) boot M1 image on the phone (fastboot boot), film the screen.

### Update 2026-11-06 (session 1, continued)

Built and pushed (all on `ios-merlin-merlin-2` main):

- `shim/merlin.{c,h}` — fresh merlin bring-up: toprgu watchdog stop FIRST
  (0x10007000, keyed wdt_v2 writes from the device kernel source), console
  on the LK splash framebuffer (address read live from the DTB /chosen
  `atag,videolfb-fb_base_l/h`, fallback 0x7e605000), payload discovery via
  /chosen initrd with fallback to 0x47c80000 (stock ramdisk load address),
  then the upstream loader; on any failure it HOLDS on screen (watchdog
  off) with a diagnostics banner. `console.c/h` gained runtime geometry
  (`con_init`), loader.c exports it in boot_args Video.
- `tools/mkadt-merlin.py` — fresh merlin ADT: GICv3 0x0c000000/0x0c040000,
  vtimer INTID 27, timebase 13 MHz, 8 CPU nodes (reg 0x000..0x700), kernel
  band 0x50000000+0x2e000000 (clear of shim@0x40080000, ramdisk@0x47c80000,
  LK fb@0x7e605000), fbcon/disp0 native 1080x2340, panic log at top,
  synthetic ECID 'MERL'+1, chip-id 0x8015 (A11 userland identity as sweet).
  Generated locally OK (9948 bytes; no /product until d22ap.adt exists).
- `tools/mkbootimg-merlin.py` — fresh boot v2 packer with the stock merlin
  slots (kernel 0x40080000, ramdisk 0x47c80000, page 2048; dtb optional).
- CI: `shim.yml` green (artifact `merlin-shim`, run 42249609609, shim
  151,552 bytes SHA256 in artifacts/). `xnu.yml` moved to `runs-on:
  macos-15` (macos-14 label retired) + no cancel-in-progress; the whole
  tree was renormalized to LF (CRLF committed shell scripts broke the CI
  patch-staging: `set: pipefail: invalid option name`).
- Kernel build for the baseline (upstream patches 0001–0081): run
  42249609626 in flight at the time of writing.

Hardware-fact corrections from the full merlin kernel-source research
(downloaded to `repo/research/merlin/` outside this repo; USB/panel/boot
facts below supersede earlier guesses):

- USB is **MTK musb**-family USB 2.0 device controller at 0x11200000
  (not mtu3/DWC3) — matters for a later USB milestone.
- Boot.img (stock): header v2, base 0x40078000 → kernel 0x40080000,
  ramdisk 0x47c80000, page 2048, Image.gz + appended DTB + dtbo.img.
- `fastboot boot` confirmed working on unlocked merlin (some flakiness
  reported on XDA); panel = DSI video-mode LCD (NT36672A/FT8719 per unit),
  LK hands it over initialized (continuous splash) — good for early console.
- CPU MPIDR encodings disagree between DT cpu reg (0x000..0x700), node names
  and cpu-map — read MPIDR_EL1 on hardware before SMP (M3).
- A parsed stock-derived runtime DTB exists at
  `repo/research/merlin/merlin-dtb.img` (+ `dtb-full.txt` dump) — a
  cross-check source; the user's choice for the git-of-record DTB is
  extraction from the phone itself.

M1a test plan (next): payload = CI kernel + merlin ADT + cmdline
`debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress`
(no rootfs — expect the kernel boot log on the panel via the fbcon, ending
in mountroot retries = proof of execution). Package with mkpayload +
mkbootimg-merlin, `fastboot boot` (RAM-only). The shim banner prints the
LIVE fb base — compare against the ADT's 0x7e605000 constant afterwards.

## Open items

- Confirm the attached fastboot device (`204719200409`) is the Note 9
  before any boot attempt.
- Stock merlin DTB: extract from the phone (user's choice) for the
  `--dtb` path if LK's own tree proves insufficient; TWRP-derived copy
  exists for cross-check (see above).
- `/product` identity node needs the Apple D22AP device tree
  (`research/ipsw-x/d22ap.adt`, Apple artifact, not in git) — not needed
  for M1; required before userland identity work.


### Device state findings (2026-11-06 evening, user-confirmed + verified)

- **`fastboot boot` is NOT supported on this unit's bootloader** (user;
  web research and older handoffs claiming otherwise are wrong for this
  phone). Test path = flash to the boot partition and restore from backup.
- Booted to TWRP recovery: adb works with root (uid=0). Partition backups
  pulled (in `backup/`, NOT in git): boot 96bc3fe1…, recovery
  (TWRP) 3a32adaa…, vbmeta 8385d0f5….
- **vbmeta flags = 0x03** (hashtree + verification disabled): the October
  "STEP 0" was done; unsigned boot images boot.
- **The boot partition currently contains the old 0117-era XNU test image**
  (190,674-byte shim + 16.7 MB payload, ramdisk slot 0x47c80000 — matches
  the fresh packer's addresses byte-for-byte). Stock Android boot is NOT on
  the phone; restore later = flash boot from the official merlin fastboot
  ROM. The shim bring-up screen color is RED (project signal convention).
