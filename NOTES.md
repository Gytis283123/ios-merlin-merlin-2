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

## Open items

- Stock merlin DTB: user chose to extract it **from the phone** (pending:
  needs Android+adb root or a bootable recovery; not required if the first
  test boots without `--dtb`).
- `/product` identity node for the ADT needs the Apple D22AP device tree
  (`research/ipsw-x/d22ap.adt`, Apple artifact, not in git) — not needed for
  M1; required before userland identity work.
- Fastboot device `204719200409` is attached to this PC — confirm with the
  user it is the Note 9 before any boot attempt.
