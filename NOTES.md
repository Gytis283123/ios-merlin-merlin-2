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

### M1a boot result (2026-11-07 morning): BOOTLOOP

- The user flashed `out/shim-boot-merlin-m1a.img` (SHA256 c991f630…) to
  boot: device bootloops. No screen observation captured yet (red banner
  seen or not, loop period unknown) — the color-ladder shim below is the
  instrumented redo. vbmeta was verified 0x03 = verity+verification
  disabled, so vbmeta is an unlikely cause; prime suspects are (a) the
  shim's entry-state assumptions (start.S assumes the Qualcomm ABL jump
  state; MTK LK may jump with a different CPU state) or (b) the toprgu
  stop sequence.
- The user is reflashing the stock OS (their call; phone unusable with the
  test image). NOTE: after a stock reflash vbmeta returns to verification
  ENABLED — flash vbmeta-disabled again before any unsigned boot test.
  The stock boot.img from the Mi Flash ROM package (images/boot.img)
  becomes the real "restore" backup we never had.
- Diagnostic image ready: `out/shim-boot-merlin-m1a-diag.img` (SHA256
  0404cce8…, kernel 4b657ed9… unchanged, ladder shim bc42d13d…): paints
  MAGENTA at C entry (fallback fb, no DTB), GREEN after the toprgu stop,
  YELLOW after the DTB parse (live fb), RED at the full banner. Last
  color on screen during a reset = failing stage.
- Housekeeping: local out/ and artifacts/ now gitignored (the first
  ladder commit accidentally tried to push the 130 MB CI kernel link
  archive — GitHub rejected it; nothing large was pushed).

### LK reverse engineering + the real boot-format story (2026-11-07)

- lk.img (stock V12.5.1.0.RJOMIXM package, extracted to
  `D:\things\Merlin\stock-rom\`): MTK IMG wrapper, payload = **ARM32
  (Thumb-2) LK** — MediaTek LK runs AArch32 and jumps to the 64-bit kernel
  via the "K64" path ("[LK]jump to K64 0x%x", "smc jump" — the jump goes
  through ATF via SMC). VA base 0x4C400000 = file offset 0x200 (ARM32
  vectors); VA = 0x4C400000 + file_off - 0x200; literal pools confirm
  (2,748 string-region pointers). The mboot debug strings ("boot image
  header magic error", "no mkimg header…") are unreferenced leftovers —
  direct xref hunting dead-ends; the ANDROID! magic constants sit in pools
  at 0xaa464 (data table) and 0xb8430. RE continues (lkre2.py).
- **The 0117-era image in the boot slot was a CORRUPTED GZIP**: kernel slot
  starts with a valid gzip header but the deflate stream is invalid — the
  "gzip corrupted images before" rule in the old kit README came from this.
  That image could never boot; the phone falling to TWRP on first probe was
  its only honest behavior.
- Stock boot.img (this firmware): kernel = Image.gz (real gzip), header
  tail@0x66C = 1660, os_version 0x16000157, stock cmdline; its "dtb" region
  is MTK-wrapped (no plain FDT magic). The verbatim stock DTB (181,203 B,
  plain FDT) from the old image stays our DTB of choice.
- **The October kit's v17 probe painted colors with: RAW kernel slot +
  VERBATIM stock header clone (patch only kernel/ramdisk/dtb sizes) +
  raw payload + stock DTB.** That recipe is field-tested on this unit.
- **v5** (`out/shim-boot-merlin-m1a-v5.img`, SHA256 787f648a…): stock
  header verbatim (verified: zero byte diffs outside the three sizes) +
  v3 shim (asm watchdog kill + MMU hardening + color ladder) + raw payload
  + stock DTB. This is the next flash test.

### ROOT CAUSE FOUND (2026-11-07, v5 loop + msdc-image comparison)

- The msdc-era images that demonstrably booted (0120/0121 — "SpringBoard
  doing real I/O" per their commit messages) have kernel slots starting
  `1f 8b 08` — **GZIP**, byte-identical convention to the stock
  Image.gz kernel. The earlier "corrupted gzip" conclusion was an
  analysis bug: the gzip header bytes were fed to a raw-deflate
  decompressor; the stream is valid (dynamic Huffman).
- **This LK requires the kernel slot gzipped.** Every one of our five
  bootloops (M1a, diag, m1a-dtb, v2, v3, v5) had a RAW kernel slot — LK's
  decompressor rejected it before the shim's first instruction. The header
  experiments (8 s vs 25 s cycles) were LK failing at different stages of
  a path that was doomed anyway.
- **v6** (`out/shim-boot-merlin-m1a-v6.img`, SHA256 d784677e…): stock
  header verbatim + kernel slot = gzip -9 (shim, 151,552 → 5,172 bytes,
  round-trip verified) + raw payload + stock DTB. Flash test pending.
- v17 probe images: raw kernel slots — their README "6 colors" table was a
  decision tree, NOT a recorded success; every v9-v17 probe bootlooped too.

### MILESTONE 2026-11-07: THE FRESH BOOT CHAIN EXECUTES ON THE PHONE (v6 + vbmeta flags)

- **Root cause of all bootloops, final: TWO independent locks.**
  1. vbmeta: after the stock-firmware reflash, Xiaomi's disable flag bits
     were reset. The October kit's `patch-vbmeta.py` (user-provided) writes
     0x03 to byte offset 123 = AVB flags bits 24/25 — **Xiaomi's LK honors
     those bits**, not the standard AVB bits 0/1. Re-applying it fixed the
     boot rejection. (Explains why a previously-working image bootlooped
     after the reflash.)
  2. The kernel slot must be gzipped (stock Image.gz and all booted shims
     are gzip; raw slots were rejected — see previous section).
- **v6 = stock-header clone + gzip(shim) + raw payload + stock DTB** booted
  once vbmeta was re-patched. Photo evidence (user): the RED MERLIN banner
  on the panel with the full diagnostic readout:
  DTB 0x4BC80000 magic valid; FB 0x7E605000; MPIDR 0x81000000 (Aff=0, MT
  bit set, RES1 — matches ADT cpu0 reg 0x000); CNTFRQ 0x00C65D40 = 13 MHz
  exact; initrd props ABSENT from LK's DTB — the shim's 0x47c80000 fallback
  located the payload; hi-lo = 16,609,776 = payload size exact; 10 segments
  copied to 0x50000000 (end 0x524C8000); boot_args at 0x524CC000; JUMP to
  0x51490488 executed. Phone frozen (watchdog off) — no loop.
- **Remaining walls:**
  1. Kernel entry: jumped, zero console output — died/hung before the
     early-framebuffer hook. Prime suspect: the LK "K64"/ATF SMC handoff
     delivers EL1 in a different CPU state (MMU/caches) than the Qualcomm
     ABL path the kernel was hardened for. Fresh patch 0082 territory.
  2. Display shear: text renders sheared — LK fb stride is likely
     1088*4=4352, not 1080*4=4320 (MTK 64-byte pitch alignment). One shim
     constant; also check vramSize-based double buffering.
- The UEFI side quest (edk2-mt6765-uefi repo) is moot for now — the boot
  chain works; parked.

### DISPLAY SOLVED (2026-11-07 evening, v27-v30 + user hardware validation)

The panel's scan geometry, established through 25 builds and proven by the
user's photos:
- **Pitch 4352 bytes (1088 px)** — 1080 content + 8 px of 64-byte
  alignment. User A/B'd 4320 vs 4352 with the cache fix active: 4352 wins.
- **Two-layer framebuffer**: rows 0-1439 fetch from the OVL L0 address
  (register 0x1400bf40, read live), rows 1440+ from the atag videolfb
  buffer (0x7e605000 - LK's logo buffer; the v19 photo showed the Redmi
  logo displaying there). OVL L1 register reads 0 (unused by LK).
- **Resolution 1080x2340** unchanged; font scale 3 (host-render proven).
- **The D-cache purge at shim entry is MANDATORY**: LK leaves dirty D-cache
  lines that evict over our non-cached writes (stale logo data clobbering
  the console - every "partial render" symptom). The purge must run before
  the first framebuffer write, and the DTB pointer must be saved to x19
  BEFORE the purge (the flush clobbers x0-x12; v28 shipped both fixes
  but only one worked - the pointer bug produced a blank screen).
- The RDMA MEM_START register reads 0 (the RDMA is not the active fetch
  engine); MEM_SRC_PITCH reads 1080 (pixels) - DO NOT write either
  register (v21's write compressed the scan 4x and invalidated the knob
  sweeps; v15's pixel-to-byte heuristic shredded the text).
- The console C code is proven correct via the host render (shim/out/
  host_test.exe -> out/host.ppm): identical code renders pixel-perfect
  on the host - all phone-side artifacts were environmental.

### DIAGNOSIS + FIX: EL2→EL1 drop before the XNU jump (2026-11-07 late, session on the Windows copy)

- Re-verified the v34 photo readout offline: `out/payload-try.bin` header
  decodes to entry VA 0xFFFFFE0007490488 → jump PA 0x51490488, **8-byte
  aligned** (the photo's `...048B` was a blurry digit). The entry address is
  NOT the bug; the kernel genuinely dies/hangs before its first kprintf.
- **Prime suspect identified: exception level.** `shim/start.S` documented
  "ABL enters at EL1" (the Qualcomm assumption). Merlin's LK jumps the shim
  via MTK ATF's "smc jump", which may deliver **EL2**. XNU xnu-8796
  `osfmk/arm64/start.s` (`_start` → `start_first_cpu` → `common_start`) is
  EL1-only: VBAR_EL1, SPSel/SP_EL1, tlbi vmalle1. At EL2, the first early
  exception vectors through UNSET VBAR_EL2 (= 0) → silent instant death —
  exactly "banner, jump, nothing".
- **Fix (shim-only, commit 5d37d64, shim CI run 42400125367 green):**
  `enter_xnu(entry_pa, ba_pa)` in start.S — at EL1 it is a plain `br x0`
  (identical to before, so sweet/QEMU behavior is unchanged); at EL2 it
  ERETs to EL1h with DAIF masked, CNTVOFF=0, CNTHCTL EL1PCTEN|EL1PCEN,
  HCR_EL2=0, SCTLR_EL1/VBAR_EL1 at reset values, x0 = boot_args PA.
  The banner now prints `BOOTEL el=` (1=EL1, 2=EL2) before the jump —
  photo evidence of what ATF actually delivered either way.
- **Flash test ready: `out/shim-boot-merlin-v35-el.img`** SHA256
  bf2692ca…cbf73 (kernel 0082b 05429bcd… unchanged, new shim 58cfa6cf…,
  payload rebuilt 312a6f3f… same size, stock DTB, stock header clone).
  Flash to boot (user), phone → look for `BOOTEL el=` on the banner and
  whether kernel kprintf output now appears on the panel.
- If still dead WITH `BOOTEL el= 2` shown → the drop ran; next suspect is
  the kernel-side entry paint ladder (patch 0083: color at `_start`'s first
  instructions) to bisect how far XNU gets.
- If still dead WITH `BOOTEL el= 1` → ATF already delivers EL1 and the EL
  theory is dead; revisit CPU state (CNTCR/timer gating, GIC state) or go
  straight to the 0083 entry ladder.

### v35-el RESULT + entry color ladder 0083 (2026-11-07 night)

- **v35-el flashed: banner showed `BOOTEL el= 00000002` — MTK ATF really
  does deliver EL2, the shim's ERET drop ran, and the kernel STILL dies
  before its first kprintf.** So EL was real (the drop was needed and is
  now in), but it is not the whole wall.
- **Patch 0083 (commit, xnu CI run 42401305835): SWEET entry color ladder
  in `osfmk/arm64/start.s`.** A `SWEET_PAINT color, basereg` macro writes
  1 MB of a color word straight to boot_args->Video.v_baseAddr (only
  x4-x6 clobbered; PA sanity window 0x40000000-0x80000000 so it is a
  no-op on sweet/QEMU panels at 0x9c000000). Checkpoints, all pre-MMU:
  BLUE (0xff0000ff) at `_start` (x0), GREEN (0xff00ff00) in
  `start_first_cpu` after `x20 = boot args`, YELLOW (0xffffff00) in
  `common_start` immediately before the MMU is enabled (x20).
  Patch generated from pristine xnu-8796.101.5 (the CI source version);
  `git apply` verified locally (tools/p83_edit.py is the generator).
- **v36 flash test = CI kernel (with 0083) + current shim (EL drop) +
  payload-try cmdline + stock DTB/header.** Decision tree from the photo:
  - BLUE → PC reaches XNU _start; death is after entry. Wait for GREEN.
  - GREEN → boot args read + early init running. Wait for YELLOW.
  - YELLOW → kernel reached MMU enable; death at/after MMU on or the
    console path (0082 fbcon) — pivot to pe_serial/fbcon on merlin.
  - nothing (red/blank) → XNU's first instructions never execute even at
    EL1 with a clean drop: suspect the SMC handoff path itself (ATF may
    re-clean/lock, or the jump target register state) — next: have the
    SHIM paint the kernel's first 16 bytes region verification, or ERET
    into a stub first, or dump ELR/ESR via a shim-installed EL1 vector.
- If YELLOW + no kprintf: strongest suspect is the fbcon probe in patch
  0082 (ml_io_map of the OVL block before VM init) — test by booting with
  `serial=0` variant or temporarily reverting to the ADT-reg fallback.

### CRITICAL DISCOVERY: CI was silently skipping 0082 AND 0083 (2026-11-07 night, run 42401305835 log)

- The xnu.yml Build log showed `Skipping patch ... 0082-merlin-fbcon-live-base.patch` AND `... 0083-...` —
  **every kernel since the 0082 commit was effectively a 0081 kernel** (no live-OVL fbcon, no ladder).
  Causes: 0083 was generated from pristine **xnu-8796.101.5**, but darwin-xnu-build clones
  **xnu-8796.141.3** (+ our 0001-0081 already applied); 0082's pe_serial.c context never matched the
  0003-patched file either. `git apply` failures are warnings in blacktop's build.sh, not errors.
- Fixes (commit, CI run 42402981771 GREEN):
  1. Both patches regenerated from the REAL tree (extracted `osfmk/arm64/start.s` +
     `pexpert/arm/pe_serial.c` from the run's `xnu-buildtree` artifact — the pre-skip state;
     `tools/p83_edit.py` is the generator). Both verified with `git apply --check` against those files.
  2. xnu.yml now tees `build.log` and **fails the run** if any numbered `00NN-` patch is skipped.
  Confirmed in the run log: `Applying patch: ...0082...` and `...0083...`, guard passed.
- **v36 flash test: `out/shim-boot-merlin-v36-ladder.img`** SHA256 ba7be133…00e5
  (kernel 0082+0083 ff23caad…, shim EL-drop 58cfa6cf… unchanged, stock header/DTB).
  This is the first kernel that actually CONTAINS the fbcon live-base fix AND the entry ladder.
- Photo decision tree (ladder paints the panel directly, boot_args->Video.v_baseAddr):
  BLUE at `_start` → GREEN after boot-args handoff in start_first_cpu → YELLOW in
  common_start just before MMU enable. Full tree in the previous section.

### v36 RESULT + shim probes v37 (2026-11-07 night 2)

- **v36-ladder flashed: banner `BOOTEL el= 00000002`, "jumping" — and NO
  BLUE.** The kernel's first instructions never executed even at EL1 after
  a verified drop. (Banner text still on screen = kernel fbcon never ran.)
- Offline checks: stock DTB (dtb/stock-merlin.dtb) — RAM
  0x40000000 size 0x3e605000 (ends AT the LK fb 0x7e605000), NO
  reserved-memory nodes, kernel band 0x50000000-0x7DF00000 fits. Expected
  entry words from the kernel Mach-O at file off 0x48c870:
  d503201f x4 (NOPs).
- **Shim v37 (commit, shim CI 42404782951, image
  `out/shim-boot-merlin-v37-probe.img` SHA256 803eba16…60e5) adds two
  probes printed/painted BEFORE the jump:**
  1. `ENTW w0..w3` = first instruction words at entry_pa — verifies the
     segment copy (expect d503201f d503201f d503201f d503201f).
  2. `EXECT ok at=…` after blr'ing a cyan-paint stub copied into the
     kernel band's unused gap (phys_base+0x1000, dcvau/icivau). A cyan
     block at panel row ~2000 = the band IS executable in the ATF/LK
     state; missing cyan = the band is not executable (firewall/XN), the
     true wall. If EXECT ok prints AND the kernel still dies: the
     ERET/EL1 state itself — next instrument a shim-installed EL1 vector
     + ESR/ELR print.
- Photo decision tree: cyan bottom block + `EXECT ok` -> band fine, state
  problem; no cyan, no EXECT -> band execution fault (probe never
  returned); `ENTW` mismatch -> payload copy bug.

### v37 RESULT decoded + v38 layered probes (2026-11-07 night 3)

- v37 photo, ENTW decoded (blurry digits resolved by instruction encoding):
  w0=F9401404 (ldr x4,[x0,#40]) w1=52A08005 (mov x5,#0x40000000)
  w2=EB05009F (cmp) w3=54000123 (b.lo) = the 0083 paint prologue itself.
  **The payload copy is byte-perfect; the ladder is the first code.**
- Photo ends at ENTW: no EXECT line, no cyan -> the band blr never
  returned. (Banner confirms con uses ONE contiguous buffer at l0=
  0x7D9B0000 via con_init(split=0xFFFFFFFF), so a row-2000 paint would
  have been visible.) Suspects left: fetch blocked in the band, or the
  probe's store row (now known fine), or an exception dying at PC 0.
- **Shim v38 (CI 42406073592, `out/shim-boot-merlin-v38-probes.img`
  SHA256 9260feb8…e71e)**: before the jump —
  1. `STRT ok` = shim stores 64 cyan words at panel row 2050 directly
     (store + visibility, no execution).
  2. `EXR ok` = bare `ret` stub copied into the band (0x50001000) and
     blr'd — pure instruction-fetch test.
  3. `EXP ok` = full cyan-paint stub into the same probe row.
  Plus: set_vbars() points VBAR_EL1 AND VBAR_EL2 at the shim vectors
  before the probes, and exc_handler now reads the CURRENT EL's
  ESR/ELR/FAR (old code read elr_el1 unconditionally = trap at EL2).
  **Any fault in the probes or pre-jump path now prints a blue PANIC
  screen with esr/ec/elr/far instead of vanishing.**
- Decision tree: PANIC screen ec/FAR = the fault identified directly.
  All three ok + no kernel = the ERET/EL1 state itself. STRT ok but
  no EXR = fetch-blocked band. No STRT = store/visibility problem.

### v38 RESULT: PANIC CAPTURED — instruction abort, L1 translation fault (2026-11-07 night 4)

- v38 flashed: **blue PANIC screen** (fault capture worked!). Decoded:
  `SYNC` slot 4 (current EL SPx sync), taken **to EL2** (ELR2/FAR2 bank
  printed), `esr=96000021` -> **EC=0x25 = Instruction Abort from a lower
  EL**, IL=1, IFSC=**0x21 = translation fault, level 1**.
  `ELR2=40801AA8` `FAR2=4080218C` (blurry digits; also plausible
  0x40081AA8/0x4008218C = inside the shim itself, or kernel-band
  addresses - confirm on the next, evidence-preserving panic).
- KEY DEDUCTION: **a translation fault is impossible with the MMU off.**
  An MMU was already ON at fault time. The shim runs with the MMU off
  the whole loader path, and the only code that enables an MMU is the
  KERNEL in common_start (SCTLR_EL1 bootstrap MMU). So the fault is very
  likely AFTER the EL2->EL1 drop, in the kernel, after MMU enable - much
  further than the "no BLUE" v36 result suggested. (Why v36 showed no
  BLUE: the ladder paints BEFORE the MMU enable; BLUE may have flashed
  and been replaced by the kernel's early output attempts/panic path.)
  EC=0x25 (from lower EL, to EL2) is still puzzling: with HCR_EL2=0 an
  EL1 sync should vector via VBAR_EL1 - which set_vbars points at the
  SHIM vectors, running the handler at EL1 and printing the EL1 bank.
  The EL2 bank on screen means the handler ran at EL2. Open question.
- **Shim v39 (CI 42407263368, `out/shim-boot-merlin-v39-stage.img`
  SHA256 0127b25c…df38)**: stage is now a global; the loader sets
  `loader-exr` / `loader-exp` / `loader-ic` before each step; the panic
  handler NO LONGER clears the screen (the banner/probe lines above the
  panic block survive and name the exact failing step) and prints SPSR.
- Next flash: photo of the full screen (panic block AND the lines above
  it). STAGE tells which probe or jump failed; ELR/FAR/SPSR tell where
  and in what CPU state. If STAGE=loader-ic / XNU jumping visible, the
  fault is in the kernel after the drop -> we debug XNU early init with
  a kernel-side ladder AFTER MMU enable (checkpoints in common_start).

### v39 RESULT: BAND IS EXECUTABLE; the "wall" was the probe's own runaway paint (2026-11-07 night 5)

- v39 photo, fully decoded:
  - `STRT ok at=7E232200` (store + display fine), **`EXR ok at=50001000`**
    — the bare ret stub EXECUTED in the kernel band and returned. The
    band is executable in the ATF/LK state; firewall/XN theory dead.
  - `PANIC SYNC`, STAGE=loader-exr, esr=96000021 = **data abort, current
    EL (SPSR2 M=EL2h confirms), IFSC 0x21 L1 translation fault**,
    FAR2=0x400821BC ELR2=0x40081AC8 X30=0x40083050 (shim addresses).
  - ROOT CAUSE of the probe panics: the EXP (v37 EXECT) probe painted
    0x40000 words = **1 MB from row ~2000 = 0x7E232200+1 MB, which
    crosses the RAM top at 0x7e605000** — a store past the end of DRAM
    aborts. In v37 (VBAR_EL2=0) the same abort was the silent death.
- IMPORTANT consequence: the panic pre-empted the jump in v37/v39 — the
  REAL kernel jump (with the EL drop + 0083 ladder) has not actually
  been tested since v36 (whose kernel, CI-skip discovery, contained NO
  ladder at all). The 0083 kernel ladder itself paints fb_base+1 MB =
  0x7DA9B000, INSIDE RAM — safe.
- **Shim v40 (CI 42407986018, `out/shim-boot-merlin-v40-jump.img`
  SHA256 3604f0eb…8e73)**: paint stub takes a word count (64 words =
  one cyan dash), CP1/CP2/CP3 checkpoints, stage `loader-jump` before
  the real enter_xnu. All probe evidence now points to the jump working;
  expect BLUE/GREEN/YELLOW ladder or kernel text on the next flash.
- If the next flash still panics pre-jump: the CP lines + stage name the
  exact instruction; if it panics with STAGE=loader-jump, the fault is
  in the kernel and ELR/FAR/SPSR (now printed) identify it precisely.

### v40 RESULT + capstone identification: the dc cvau/ic ivau trap (2026-11-07 night 6)

- v40 photo: STRT ok, EXR ok, PANIC at STAGE loader-exr BEFORE CP1 -
  same window as v39 (EXR print -> copy64 -> dcvau/icivau -> CP1).
- Disassembled the shim binary locally (capstone): ELR2=0x40081AC8 is
  the ldr of the INLINED second copy64; X1 = n+7 in BOTH v39 (0x23 =
  28+7) and v40 (0x1F = 24+7) = the copy64 rounding numerator; FAR2 =
  the stub's own source bytes (0x400821BC / 0x4008213C).
- **Conclusion: dc cvau / ic ivau BY VA WITH THE MMU OFF is
  architecturally UNDEFINED and traps on this CPU.** It is the common
  factor of every death since v37 (silent in v37 - VBAR_EL2 was 0;
  a blue PANIC in v38+ thanks to set_vbars). The fault surfaces in the
  copy loop AFTER the first cache-op pair (the first pair for the ret
  stub survived twice - marginal/implementation detail, irrelevant now).
- **Shim v41 (CI 42408871481, `out/shim-boot-merlin-v41-jump.img`
  SHA256 112fe358…fd99)**: per-VA cache ops REMOVED everywhere before
  the jump (with the MMU off, copied bytes are uncached; a global
  `ic iallu` provides I-coherency - the MMU-off-safe form); EXP paint
  probe dropped (EXR already proved the band executes); exec_ret_stub
  .balign 8. Flow now: BOOTEL -> vbars -> ENTW -> STRT -> EXR -> CP3
  -> ic iallu -> enter_xnu (EL2->EL1 drop) -> XNU.
- THE REAL JUMP HAS STILL NEVER EXECUTED (v37/v39/v40 died inside the
  probe; v36's kernel had no ladder due to the CI skip). v41 is the
  first full clean shot: expect the 0083 ladder (BLUE at _start, GREEN
  after boot-args handoff, YELLOW before MMU enable - all painted with
  fb_base+1MB = 0x7DA9B000, safely inside RAM) or kernel kprintf text.
- If a panic appears with STAGE=loader-jump: the kernel faulted; ESR/
  ELR/FAR/SPSR (EL-aware) identify it - extend the kernel ladder past
  MMU enable next.

### ROOT CAUSE #2 FOUND AND FIXED: HCR_EL2.RW wiped by the drop (v41 -> v42, 2026-11-07 night 7)

- v41 photo: STRT ok, EXR ok, CP3 pre-jump ok, "XNU jumping", then PANIC
  with **ec=0000001E = EC 0x1e ILLEGAL EXECUTION STATE**, taken at the
  ERET (ELR2=kernel entry 0x51490488, no BLUE paint, STAGE=loader-jump).
- **ROOT CAUSE: enter_xnu wrote `msr hcr_el2, xzr`, which cleared
  HCR_EL2.RW (bit 31, "EL1 is AArch64").** MTK ATF set RW=1 for its K64
  jump; with RW=0, EL1 is AArch32-only, so the ERET to EL1 in AArch64
  state is an ILLEGAL exception return (EC 0x1e) routed back to EL2.
  The kernel was NEVER entered on any drop build (v35-v41). This was
  the true wall behind "BOOTEL el=2 then nothing".
- **Shim v42 (CI 42409922655, `out/shim-boot-merlin-v42-rwfix.img`
  SHA256 46f7d68b…bceb, shim 288cf8b1…): enter_xnu now sets
  HCR_EL2 = 0x80000000 (RW=1, everything else 0: no stage 2, no traps,
  TGE=0) before the ERET.** HCR printed on the panic screen.
- Expectations for the v42 flash: with the drop finally legal, the
  kernel should execute: BLUE (paint at _start) -> GREEN (boot args
  handoff) -> YELLOW (pre-MMU) -> kernel kprintf text on the panel
  (0082 fbcon live-OVL base). If a panic shows instead, STAGE=loader
  -jump + the ESR/ELR/FAR/SPSR/HCR dump (now EL-aware) identifies the
  next wall precisely; the likely suspects are kernel-side (MMU enable
  path, fbcon probe) and get kernel patches (0083+), not shim work.

### MILESTONE 2026-11-07 late: THE DARWIN (XNU) KERNEL EXECUTES ON MERLIN 🎉

- **User-confirmed after flashing v42 (shim-boot-merlin-v42-rwfix.img):
  the phone reached the Darwin kernel.** The full chain works:
  LK -> gzip(shim) -> payload discovery -> segment copy to 0x50000000 ->
  boot_args/ADT -> HCR_EL2.RW=1 ERET drop to EL1 -> XNU _start ->
  start_first_cpu -> common_start (0083 ladder + 0082 fbcon kernels).
- What it took across the day (final root-cause list):
  1. CI silently skipped patches 0082/0083 (wrong source version + stale
     context) -> regenerated from the real xnu-buildtree, CI now FAILS
     if a numbered patch is skipped.
  2. dc cvau/ic ivau BY VA with the MMU off is UNDEFINED and traps on
     MT6768 -> removed (global ic iallu instead).
  3. **HCR_EL2.RW was wiped by the drop's `msr hcr_el2, xzr` -> illegal
     ERET (EC 0x1e) -> kernel never entered (v35-v41). Fixed: HCR_EL2 =
     RW (0x80000000) only.**
- Diagnostic infrastructure that got us here (keep for future walls):
  shim color/word probes (ENTW/STRT/EXR/CP3), VBAR_EL1+EL2 pointed at
  the shim vectors, EL-aware PANIC dump (ESR/EC/ELR/FAR/SPSR/HCR,
  screen NOT cleared), stage markers (loader-exr/exp/ic/jump).
- NEXT (per the milestone plan in this file): confirm how far the kernel
  gets (photo: ladder colors and/or kprintf text, mountroot retries =
  M1a proof), then M2 = MSDC eMMC block driver (rd=msdcroot0) to mount
  the iOS 16 root from userdata, M3 = SMP via PSCI, M4+ display/touch.

### v43: kernel startup-hook trace (0084) - bisecting the post-bootstrap silence (2026-11-07 night 8)

- v42 result (user photo): Darwin runs DEEP into boot - scheduler,
  OSLog firehose, telemetry, KDP ("iBoot version: merlin-shim" - the
  kernel reads our shim identity!), SWEET platform expert, AppleKeyStore
  (no passcode, unlocked), IOWatchdog, IOCoreSurfaceRoot, HID
  buttons+touch, static battery, then the VM zone maps, ending at
  **"VM bootstrap done: 85 maps, 165 entries and 591 holes left"**
  (vm_kernel_boostraped, STARTUP_SUB_ZALLOC) with the red cursor line
  below it. No panic printed. The console wraps (45 visible rows, top
  row cut mid-line), so the exact dying hook is not identifiable from
  the photo alone.
- **Patch 0084 (CI 42412559363, applied, guard passed):** every STARTUP
  hook from STARTUP_SUB_LOCKS up now prints
  `SWEET STARTUP: [subsys rank] func` (printf - the fbcon early console
  is proven up at this point), plus `SWEET STARTUP: reached phase N` at
  every kernel_startup_initialize_upto exit. func addresses symbolicate
  against artifacts/kernel-0084/kernel.development.sweet.link.
- **Flash test: `out/shim-boot-merlin-v43-trace.img`** SHA256
  7f8f329e...2e18 (kernel 0084 62490e13..., shim v42 288cf8b1...
  unchanged). Photo the screen END (the last lines above the red
  cursor): the last `SWEET STARTUP:` line names the hook that never
  returned.

### v43 REGRESSION + REVERT (2026-11-07 night 9, user call)

- v43 (kernel 0084 + startup trace) REGRESSED: the boot died between the
  ladder's GREEN paint (start_first_cpu) and the first kernel console
  output - well before where v42 (kernel 0083, identical shim) sailed
  through to "VM bootstrap done". Only change: the 0084 startup-trace
  printfs (binary layout shift). User called it: revert.
- **Reverted (commit ac6fdaa "Revert xnu 0084...").** xnu/patches is
  back to 0001-0083. CI 42414140948 green.
- **Flash test: `out/shim-boot-merlin-v44-restore.img`** SHA256
  381de908...7d6d (kernel 7a614a68... - the 0083 source rebuilt; the
  binary is not byte-identical to ff23caad but is built from the same
  patches; shim 288cf8b1... unchanged). Expected: back to the v42 deep
  boot ending at "VM bootstrap done".
- LESSON: treat kernel-side layout-affecting instrumentation as risky on
  this port; any future trace must be minimal (subsystem-transition
  marks only, ~8 lines, own commit, built only after the restore is
  confirmed) and dropped at the first regression.

### v44 restore CONFIRMED + careful 0085 (2026-11-07 night 10)

- v44 restore confirmed by the user: back to the v42 deep boot, silent
  after the VM-zone phase (the 'SWEET BATTERY' line is just the last
  distinctive line before the wrapped tail; true last output = 'VM
  bootstrap done').
- **Patch 0085 (careful form, CI 42415491414, applied, kernel 6433d833
  - same 17205024 size class as the proven 0083 builds):** one line per
  SUBSYSTEM transition in kernel_startup_initialize_upto only:
  `SWEET SUBSYS: entering N (hook p)` from STARTUP_SUB_KMEM up (~12
  lines per boot). Nothing else. Own commit - single revert drops it.
- **Flash test: `out/shim-boot-merlin-v45-subsys.img`** SHA256
  30055cfd…b639 (shim/DTB/header unchanged). Photo the screen tail: the
  last `SWEET SUBSYS:` line names the subsystem that never finishes.
  Subsystem ids: 5=KPRINTF 6=PMAP_STEAL 7=KMEM 8=ZALLOC 9=KTRACE
  10=PERCPU 11=EVENT 13=CODESIGNING 14=OSLOG 15=MACH_IPC 16=THREAD_CALL
  17=SYSCTL 18=EARLY_BOOT.
- If it dies INSIDE a subsystem (no next SUBSYS line): the (hook p) on
  the last line symbolicates against
  artifacts/kernel-0085/kernel.development.sweet.link.

### BREAKING INSIGHT + 0086: the console WRAPS - the kernel was never "stuck" (2026-11-08)

- v45 photo decode + pe_serial.c audit: the sweet fbcon console WRAPS
  after fbcon_rows lines (`fbcon_row = (fbcon_row + 1) % fbcon_rows`,
  73 rows at scale 2 on merlin) - it does NOT scroll. Every boot photo
  past ~73 lines was a TWO-PASS MOSAIC: newest lines at the TOP, oldest
  at the bottom. That explains ALL of it:
  - the "impossible" line order in the v45 photo (PMAP_ACTIVATE_KERNEL/
    mac_policy/vnguard ABOVE the zone-init lines = newest on top),
  - "stuck on the SWEET BATTERY log" = the wrap seam,
  - the "multiple walls" (zone maps / VM bootstrap done): the kernel
    was most likely RUNNING PAST them while the display showed a stale
    mosaic. The v45 photo's top rows prove MACH_IPC (15) and
    PMAP_ACTIVATE_KERNEL were reached - far past the supposed wall.
- **Patch 0086 (CI 42463916371, applied, kernel e6723de2): fbcon
  scrolls by one row per newline (~140 KB memmove) instead of wrapping;
  cursor parks on the second-to-last row so the newest output is always
  at the bottom.** Own commit; reverts alone if it regresses.
- **Flash test: `out/shim-boot-merlin-v46-scroll.img`** SHA256
  ec0e5dee…29bd (kernel 0086 e6723de2..., shim 288cf8b1... unchanged).
  The boot log should now read normally top-to-bottom, newest at the
  bottom. Photo the BOTTOM of the screen after it stops: that is now
  the TRUE last output. Whatever it names is the real next wall - no
  more mosaic forensics.

### ROOT CAUSE #3 FOUND AND FIXED: ADT GICR base was wrong - the vtimer PPI was never delivered (2026-11-08, v48 photo analysis)

- v48 photo (kernel 0087 clear-at-wrap, read chronologically, newest at the
  bottom): output stops after `SWEET BATTERY: static fallback ...` with the
  cursor parked below it, no panic. BOTH console experiments (0086 scroll
  first landing, 0087 clear-at-wrap) stop at the SAME line, so this is a
  real wall, not a display artifact. Source-order mapping
  (osfmk/kern/startup.c): the photo's tail (vnguard -> trust caches ->
  PE -> AKS/WDT/SURF/HID/BATTERY) is PE_init_iokit + kernel_bootstrap past
  STARTUP_SUB_EARLY_BOOT; the bootstrap thread was already inside bsd_init.
  With a working timer, IOFindBSDRoot would print `!BSD` / `Waiting on
  <dict>` / `Still waiting for root device` and finally
  `panic("Failed to mount root device")` within ~90 s (no `rd=` in the
  cmdline, no IOMedia driver). Nothing printed => the FIRST timeout-based
  wait (`waitForMatchingService(..., 30 s)`, iokit/bsddev/IOKitBSDInit.cpp)
  never returned => **timer callouts dead**.
- Root cause: **mkadt-merlin.py gave the kernel GICR = 0x0c040000
  (0x200000)**. The stock DT (mt6768.dts:1474, confirmed in the parsed
  runtime DTB `repo/research/merlin/dtb-full.txt`) puts the redistributors
  at **0x0c400000, size 0x40000** ("gic_cpu@0c400000"); 0x0c040000 is
  INSIDE the GICD's 0x400000 window (reads 0, NS writes silently dropped).
  pe_init_fiq (pexpert/arm/pe_fiq.c) therefore "found" cpu0's GICR at the
  wrong address (GICR_TYPER reads 0, affinity 0 == boot MPIDR Aff 0) and
  programmed a dead region: GICR_WAKER wake, IGROUPR0 Group-1 and
  ISENABLER0 bit 27 (vtimer PPI, patch 0017 ADT value) never reached the
  real redistributor. QEMU was unaffected (QEMU_GICR constant matched
  QEMU's layout), which is why every QEMU smoke test passed.
- **Fix (commit 1b15752, no kernel change, kernel 0087 5300d19b and shim
  v42 288cf8b1 unchanged): mkadt-merlin.py GICR = 0x0c400000,
  GICR_SIZE = 0x40000** (PE0 RD+SGI frames, GICR_PE_SIZE = 0x20000; extend
  if M3/SMP needs more PEs). Verified: new reg bytes in the payload at
  0xfd6de4, old bytes gone.
- **Flash test: `out/shim-boot-merlin-v49-gicr.img`** SHA256
  777e1b17f3725014e347b26ad67b1018f389412a6de5d11ab45b4ee94f0f921c
  (payload 2c4c23c6..., shim re-extracted from the v48 image and
  round-trip verified = 288cf8b1, stock DTB/header clone).
- Expected if the fix is right: the boot gets PAST the silent wall -
  `!BSD` and/or `Waiting on <dict>...` (IOMedia Apple_HFS match), then
  `Still waiting for root device` + `panic("Failed to mount root device")`
  (expected - M2 = eMMC/MSDC root driver is the next milestone and the
  cmdline has no rd=), or mountroot retries if a ramdisk is added. A panic
  screen with a readable message = SUCCESS for this test (timer works;
  panic is the honest no-root-device outcome). Battery/vsync timers
  (IOTimerEventSource) should also start working.

### v49 RESULT: GICR 0x0c400000 was WRONG - revert + probe patch 0088 (2026-11-08, photo)

- v49 flashed: **panic at `find_gicr_pe_base: cannot find GICR base for
  core 0 @pe_fiq.c:73`** early in boot (console + panic output fine at
  that stage). So 0x0c400000 reads all-ones for NS = unmapped, and the
  walk found no affinity-0 TYPER.
- Cross-check in the BSP kernel source
  (`repo/research/merlin/Xiaomi_Kernel_OpenSource-merlin-r-oss`): NO
  driver binds `mediatek,gic500`/`mediatek,gic_cpu` - Linux's
  irq-gic-v3.c binds the runtime DTB's `/interrupt-controller`
  (arm,gic-v3) node: **GICD 0x0c000000/0x40000, GICR 0x0c040000/0x200000,
  sysirq 0x0c53a650**. The stock OS boots with GICR = 0x0c040000, so the
  ORIGINAL ADT was right and the timer wall is NOT the GICR address.
  (The gic500@0c000000/gic_cpu@0c400000 nodes are legacy MTK-internal.)
- IMPORTANT: the earlier "match" at 0x0c040000 never proved the
  redistributor is real - GICR_TYPER reads 0 on a dead region too
  (affinity 0 == boot MPIDR affinity 0 = false positive). The wall could
  be (a) the whole 0x0c040000 window dead for NS (unlikely - Linux uses
  it), (b) redistributor writes silently dropped by the ATF security
  state (GICR_NSACR), or (c) programming fine and delivery broken
  (GICD/CPU-interface state, CNTHCTL, ...).
- **Patch 0088 (commit 72322a7, CI 42480655936): pe_init_fiq boot probe**
  after the SWEET GIC programming: readback prints
  `SWEET GIC: mpidr= typer= waker= igrp= isen=` (TYPER must carry PPIDR
  = MPIDR 0x81000000<<32 if the redistributor is real),
  `SWEET GIC: gicd_ctlr= igrpen1= sre=`, and a one-shot vtimer pending
  test (`SWEET GIC: tick istatus= pend= ctl=` - CVAL=now+100us, poll
  CNTV_CTL.ISTATUS, read GICR_ISPENDR0 bit 27; values restored after).
  Decision tree: typer=0 -> GICR window dead; isen/igrp not sticking ->
  NSACR-class denial; istatus=0 -> timer/counter itself dead; istatus=1
  + pend bit27 -> GICR fine, delivery path broken; istatus=1 + no pend
  -> enable/group routing lost.
- **mkadt-merlin.py GICR reverted to 0x0c040000/0x200000** (same commit).
- Flash test after CI: **v50** = kernel 0088 + shim v42 (288cf8b1) +
  reverted ADT + stock DTB/header. Photo the screen; the three SWEET GIC
  lines decide the next fix.
- **v50 READY: `out/shim-boot-merlin-v50-gicprobe.img`** SHA256
  75d72f060d313927e9489219285e365320abcfc8571599d7fae26a7a7cfe33d7
  (kernel 0088 8532cdfc..., payload 071a8b8f..., shim 288cf8b1...,
  reverted GICR verified in the payload). CI run 42480655936 green,
  0088 applied+guard passed.

### v45 top-of-screen decode: NO WALL - Darwin marched through kernel_bootstrap (2026-11-08)

- User photographed the TOP of the stuck screen (newest lines under the
  wrap console). Decoded chronologically: VM bootstrap done -> SUBSYS 9
  (KTRACE) -> 10 (PERCPU) -> 11 (EVENT) -> OSLog configured (firehose 16
  chunks, queues 8x32768) -> Telemetry -> Scheduler quanta -> SUBSYS 13
  -> mach_kobj_count=374, IPC_PTHREAD_PRIORITY init -> SUBSYS 14
  (panic_trace, kdp_core zlib) -> serial KDP init -> SUBSYS 15
  (MACH_IPC, "iBoot version: merlin-shim" - Darwin reads our shim
  identity from the boot args!) -> "boot"/"name"/"ABPL_phandle" not a
  kext (kext scanning!) -> SUBSYS 16 (THREAD_CALL, thread_max=2560) ->
  SWEET PRNG/pthread/AMFI registered -> vnguard MAC policy loaded ->
  trust caches unavailable -> ... platform expert, AppleKeyStore,
  IOSurface, HID, battery are IOKit-start-era lines in the same stream.
- **There was never a wall at the zone maps/battery: all of it was the
  73-row wrap mosaic.** The frontier at photo time was around SUBSYS
  17 (SYSCTL) / 18 (EARLY_BOOT = bsd_init + IOKit start).
- 0086 scroll REVERTED (per-line 10 MB wcomb memmove tore and crawled;
  first scroll lands right at the battery line - matches the user's
  report exactly). Replaced by **0087 (CI 42475622222, applied,
  kernel 5300d19b): clear-and-restart at wrap** - no per-line copying;
  the screen always shows the newest 73 lines in order, frontier at the
  BOTTOM. CI also gained a KDK sha256-verified install with 22G91/22G90
  fallbacks (the dortania CDN 503'd 22G74 for ~2h today).
- **Flash test: `out/shim-boot-merlin-v48-clearwrap.img`** SHA256
  c937a94b…2d87. Photo the BOTTOM of the screen when it stops: that is
  the true frontier now. Expect either bsd_init/IOKit progress lines,
  mountroot retries (M2 = eMMC driver next), or a panic - all readable
  directly, no mosaic decoding.

### DISPLAY SOLVED (2026-11-07 evening, v6-v33, user-confirmed full panel)











The final geometry, all hardware-sourced (v32's register reads + the user's
v33 full-panel confirmation):
- **Base: the OVL L0 address register (0x1400bf40), read live** — 0x7D9B0000
  at the observed boots (LK's display-pipe allocation; NOT the atag
  videolfb 0x7e605000, which is the logo buffer the pipe does NOT scan).
- **Pitch 4352 bytes (1088 px)** — hardware-confirmed by the OVL
  L0_PITCH register (0x1400b044) reading 0x1100. 1080 content + 8 px of
  64-byte alignment.
- **ONE contiguous 1088x2340 scan buffer** — no second layer, no split
  (the v19 "Redmi logo below the text" = LK's logo drawn lower in the SAME
  buffer; the v19 "red bar" = our second-segment writes landing at row
  1440+ of it correctly).
- Entry ritual: WDT kill first; save the DTB pointer (x19) BEFORE the
  D-cache clean+invalidate by set/way (LK leaves dirty D-cache lines that
  evict over our non-cached writes - the cause of every partial render);
  then MMU|C|I drop, TLBI, IC IALLU.
- Forbidden: writing MEM_SRC_PITCH (pixels, not bytes - v21's 4x
  compression), writing the OVL CON registers, trusting the RDMA
  MEM_START register (reads 0 - the RDMA is not the fetch engine).
- The console C code proven correct via the host render (host_test.exe).
- Kernel console: patch 0082 (fbcon reads the live OVL L0 base at
  serial_init; the ADT reg = the fallback; pitch 4352 via the ADT stride).

## Rootfs userdata image built (2026-11-07, Windows/WSL machine)

- Built `ios16-root-20H392-merlin.img` (16 GiB journaled case-sensitive HFS+)
  + `.simg` (12,145,168,668 B) + `.sha256` from the user's local
  `iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw`, using the upstream
  sweet toolchain (`tools/mkiosroot.sh` + `tools/sweet-root-tweaks.py`).
  Deliverables in `out/` (gitignored). SHA256: raw img
  f7b6e21a6c18ab09f0d6f209d3665bb161795c901f864bb341a714b0b42528da,
  simg 7f309197b21fda624e5c47d2e99444476b437be38e1fb99f7df6000bdbde107c.
  Contents = plain mkiosroot output (OS root + SystemOS/AppOS cryptexes
  under /private/preboot/Cryptexes, dyld cache hard-links, logd dirs,
  systembag.kb) + the full sweet tweaks (launchd _PanicOnCrasX + CommCenter
  removed, /private/var/containers/*, migration LastSystemVersion,
  VirtualAudio disabled, MediaToolbox StartRecorderServer=false,
  BKNoWatchdogs, Setup skipped). fsck clean before and after the tweaks.
- KNOWN DIFF vs the sweet v14/v15 images: the mobileactivationd data ark was
  NOT seeded (a fresh image has no system-container UUID dir to put it in) ->
  expect a mobileactivationd crash loop; and no USB-network preferences.plist
  (v15 extra). Everything else matches the sweet home-screen images.
- Build environment (new, on this Windows box): all of it lives in WSL2
  Ubuntu-24.04 under `/work` (root via `wsl -d Ubuntu-24.04 -u root`; user
  sudo needs a password). WSL2's stock kernel has NO HFS+ -> built a custom
  kernel (microsoft tag linux-msft-wsl-6.18.54.1 + CONFIG_HFSPLUS_FS=y +
  CONFIG_HFS_FS=y), installed as C:\Users\gycioc\bzImage-hfsplus-6.18.54.1,
  selected via kernel= in C:\Users\gycioc\.wslconfig (backup
  .wslconfig.bak-2026-11-07; delete the kernel= line to revert). apfs-fuse
  built from source (sgan81) at /work/apfs-fuse/build, symlinked to
  /usr/local/bin/apfs-fuse; hfsprogs + android-sdk-libsparse-utils from apt.
  /work holds the extracted IPSW dmgs (OS=087-86698-044,
  SystemOS=087-86593-047, AppOS=087-86715-047), the kernel tree, and the
  image build dir; delete them and compact the WSL disk to reclaim ~35 GB.
- Flash (Windows fastboot): `fastboot flash -S 512M userdata
  merlin2\out\ios16-root-20H392-merlin.simg`. REMINDER: the merlin kernel
  (through 0083) still has NO MSDC/eMMC root driver (M2) — it cannot mount
  this root yet; the image is staged for that milestone. Confirm the
  userdata partition is >= 16 GiB before flashing (if not, rebuild with a
  smaller SIZE argument; the fs only uses 12 GiB... can be trimmed).

### Session 2026-11-08 (2): repo maintenance — validator revert-gap fix, merlin README (agent, no device action)

- No kernel, shim, ADT, DTB or workflow changes: **no CI runs were spent and
  none will trigger on push** (xnu.yml watches `xnu/patches/**`, shim.yml
  watches `shim/**`; this session touched only tools/, docs and README).
  Device state and the pending work are UNCHANGED: **v50
  (`out/shim-boot-merlin-v50-gicprobe.img`, kernel 0088 8532cdfc, payload
  071a8b8f, shim 288cf8b1, SHA256 75d72f06…) is still the flash test to
  run**; its photo decides the timer/GICR next step per the decision tree
  in the v49 entry.
- **Bug found and fixed (commit f1c3015): `tools/validate-repo.py` failed on
  the healthy tree** — its sequence check flagged the intentional 0084/0086
  revert gaps as errors ("Repository integrity check FAILED"). Footgun: an
  agent or user seeing that could have "fixed" it by renumbering the series,
  breaking every NOTES.md patch reference and artifact name. Fix: a
  documented `RETIRED_PATCHES` table (number → revert commit); gaps must
  appear there, retired numbers present as files warn (stale entry), gaps
  NOT listed remain errors. Verified both directions locally: the healthy
  tree passes (86 patches, 0001-0088 modulo retired 0084/0086); removing
  0087 still fails with "missing 0087 not in RETIRED_PATCHES". Banner
  renamed to this repo. Also mkadt-merlin.py cosmetics (collapsed
  conditional line, fbcon props indent, literal 2340 → FB_H; output
  byte-identical 9948 B, warning about missing d22ap.adt as before).
- **README rewritten for merlin (commit 816809d):** it was the upstream
  sweet README verbatim (Redmi Note 10 Pro / SM7150 / UFS / fastboot boot /
  "boots to home screen") — wrong for this repo on every axis. New content
  is sourced from this file and the tree: current milestone state, the four
  boot-format rules (gzip kernel slot, stock header clone, Xiaomi vbmeta
  bits 24/25 @ offset 123, no fastboot boot), the chain diagram with the
  EL2→EL1 drop, this repo's CI paths, the merlin packaging commands, the
  merlin patch layer incl. retired 0084/0086, and the key MT6768 hardware
  facts (GICD/GICR incl. the 0x0c400000 decoy, 13 MHz timer/INTID 27,
  toprgu, OVL L0 live fb base + pitch 4352, eMMC/MSDC for M2, RAM map,
  boot.img slots). docs/QEMU_TESTING.md got a merlin banner note (the
  upstream guide still applies; qemu.yml derives the merlin twin at run
  time).
- Verified en route (observation, not change): `.github/workflows/qemu.yml`
  `workflow_run.branches: [main]` is correct in the repo — an apparent
  `branches: ain]` was an output-rendering artifact of the agent's tooling
  (byte-verified with od); future agents should hex-verify any suspicious
  `[m…` bracket text before "fixing" it.
- Open item for the user (housekeeping, no rush): the GitHub token used for
  this session's clone/push was shared in chat — revoke it and cut a fresh
  one when convenient.

### Session 2026-11-08 (3): full CI matrix — RELEASE/DEBUG configs proven, DEBUG fixed (0089), CI hardening (agent, no device action)

- User asked for "all" CI actions. Dispatched every workflow and every
  kernel config; three real repo bugs found and fixed on the way. No
  device action; **v50 (`out/shim-boot-merlin-v50-gicprobe.img`, kernel
  0088 8532cdfc, SHA256 75d72f06…) remains the flash test to run** —
  nothing in this session changes the kernel the phone would boot
  (0089 only touches DEBUG-only code paths; DEVELOPMENT kernel behavior
  and boot path are unchanged).
- **Run ledger** (all on main): xnu #37 DEVELOPMENT (dispatch, d575507)
  ✅ `kernel.development.sweet` aad466ef…; qemu #19 (auto) ✅;
  qemu #20 (manual) ✅; shim #57 (dispatch) ✅; xnu #38 RELEASE
  (dispatch) ✅ `kernel.release.sweet` 7e23d8dc… (12.3 MB, stripped);
  qemu #21 (auto after #38) ❌ pre-fix harness; qemu #22 (manual,
  `kernel_run_id=42489225532` re-test) ✅; xnu #39 DEBUG (dispatch)
  falsely ✅ with an EMPTY artifact; qemu #23 (auto after #39) ❌ (the
  new fetch guard correctly refused the empty artifact); xnu #40
  DEVELOPMENT (push @ 8532959, with 0089) ✅
  `kernel.development.sweet` c713a04c…; qemu #24 (auto) ✅; xnu #41
  DEBUG (dispatch @ 8532959) ✅ `kernel.debug.sweet` e301b13e…
  (25.4 MB); qemu #25 (auto) ✅ `{"status": "incomplete_decode",
  "unknown_glyphs": 464}` — full font decode (DEBUG kernel carries
  `_iso_font`).
- **Observation: RELEASE config builds and boots.** Kernel produces
  with no source changes; qemu boots it as `{"status": "not_decoded"}`
  (RELEASE strips `_iso_font` and every non-KPI symbol; fb.png, regs,
  serial and the exception log are still captured). Useful for a
  slimmer on-device test kernel later.
- **Observation: DEBUG config never compiled on xnu-8796** (and still
  does not on xnu-10002.81.5 — same four bugs verbatim). Four upstream
  errors, all in DEBUG-only code paths (machine_routines.c `#if DEBUG`
  kprintf using nonexistent `bad_page_cnt`; sched_proto.c — which is
  only compiled in DEBUG configs — referencing undeclared
  `max_unsafe_rt/fixed_quanta` and passing the RT tunable to the fixed
  setter; vm_pageout.c `#if UPL_DEBUG` member typo `uple_create_btref`;
  profile_prvd.c `ASSERT(MUTEX_HELD(...))` where MUTEX_HELD does not
  exist in XNU). Fixed by patch **0089** (commit 09ee8e5): compute the
  bad-page count, declare the externs, pass the right tunable, fix the
  typo, use `LCK_MTX_ASSERT_DEBUG`. Patch context built against the
  reconstructed post-0001-0088 tree (kprintf hunk anchors at line 1825
  matching run #39's error log); applies cleanly and was proven by runs
  #40/#41 (DEVELOPMENT unchanged, DEBUG green).
- **CI bug 1 (commit 202ad34):** qemu.yml hardcoded
  `kernel.development.sweet` — after the RELEASE build the auto boot
  test went red on `sha256sum`. Now detects the kernel file (any
  config) from the artifact and exports `KERNEL_BIN`.
- **CI bug 2 (commit c859f60):** the qemu harness refused to boot
  kernels without exactly one `_iso_font` symbol ("kernel must contain
  exactly one _iso_font symbol") — RELEASE kernels are stripped, so
  this would permanently break the auto-boot pipeline whenever RELEASE
  is the latest green build. Harness now falls back to no-font mode
  (boot runs, result `not_decoded`). Also added the `kernel_run_id`
  input to qemu.yml's workflow_dispatch so any green xnu run's kernel
  can be boot-tested on demand (used to re-test RELEASE as #22).
- **CI bug 3 (commit 8532959):** with keep_going, `make -k` survives
  compile errors and the Build step's exit code is tee's — run #39
  (DEBUG, 4 compile errors) reported GREEN with an empty xnu-kernel
  artifact. xnu.yml now fails if the fakeroot has no `kernel.*` file.
  This is the guard that makes every future silently-broken build red.
- **Capability now proven end to end:** all three workflows dispatchable
  with inputs; qemu auto-fires after every green xnu run; artifacts and
  logs retrievable via the API. Three kernel configs buildable on
  demand: DEVELOPMENT (the bring-up workhorse), RELEASE (slim, boots),
  DEBUG (assertions + full symbol table — boots in QEMU with complete
  fb decode; the natural kernel for the on-device GIC probe debugging
  if more verbosity is ever needed).
- Still open from the previous session: revoke the GitHub token that
  was shared in chat and cut a fresh one.

### Session 2026-11-08 (4): CI boot-image pipeline (v51) - image.yml + mkdtb-from-bootimg + verify-bootimg (agent, no device action)

- User request: "make the Image for The XNU now so i can test it and give new
  error logs". The pending flash test (v50, kernel 0088 GIC probe) was built
  locally on the user's Windows/WSL box from device artifacts
  (dtb/stock-merlin.dtb + backup/stock-boot.img) that live outside git, so
  this session makes the image build a first-class CI workflow:
  **`.github/workflows/image.yml`** (dispatch-only) packs the flashable
  boot.img from (a) the newest green xnu kernel artifacts, (b) the newest
  green merlin-shim artifact, (c) a freshly generated merlin ADT, and (d)
  the stock merlin boot.img downloaded from the official Xiaomi fastboot
  ROM. No kernel/shim source changes; the v50 flash test configuration is
  reproduced, the new image series starts at **v51**.
- **Provenance of the stock header/DTB in CI (observation + known risk):**
  default ROM = official merlin global `V12.0.3.0.QJOMIXM` (Android 10,
  2020-08, bigota 3,505,313,165 B, URL verified 200; bn.d.miui.com and the
  Alibaba-SG OSS mirror carry the identical file). The v-series' 181,203 B
  DTB came from the user's machine; the ROM dtb slot is MTK-wrapped, so
  **`tools/mkdtb-from-bootimg.py`** scans the whole boot.img for embedded
  FDTs, validates each (header bounds incl. off_mem_rsvmap, full structure
  walk, >=8 nodes, /chosen + /memory present), refuses trees that do not
  identify as merlin/mt6768, and writes the largest surviving candidate
  (logs every candidate with offset/region/model/compatible). A different
  firmware-version DTB/header than the user's backup is a deviation - if
  v51 misbehaves at the LK/DTB level (e.g. shim banner shows DTB magic 0),
  the fallback is `stock_boot_url` (dispatch input) pointing at the user's
  own stock-boot.img for byte-exact v-series reproduction.
- **`tools/verify-bootimg.py`** gates the packed image (the patch-skip-guard
  philosophy for images): ANDROID!/v2/2048 header sanity; header clone equal
  to stock modulo exactly the three 4-byte size fields; kernel slot gzips
  back to the shim binary; ramdisk slot == payload bytes (SWEETXNU v1,
  cmdline check); the payload-embedded ADT == the ADT file AND carries the
  Linux arm,gic-v3 reg bytes GICD 0x0c000000/0x40000 + GICR
  0x0c040000/0x200000 (the v49 decoy lesson, guarded forever); dtb slot ==
  DTB file with FDT magic; file ends exactly at the paged dtb end.
- **Local proof before spending CI runs** (all on this machine, no device):
  - Artifact identities re-verified via the API: shim run 42489231291
    (#57) = `shim-merlin.bin` SHA256 `288cf8b168d6...e2778a` (151,552 B) -
    **the CI shim is byte-identical to the field-tested v42 binary** the
    v45-v50 images booted (no toolchain drift). xnu #40 (42493163172)
    `kernel.development.sweet` = `c713a04c72aa...a0f8cc` (17,205,064 B);
    xnu #41 (42493186867) `kernel.debug.sweet` = `e301b13efe75...77144de`
    (25,441,xxx B) - both match the session (3) ledger.
  - End-to-end chain exercised locally with the real kernel/shim + a fresh
    `merlin.adt` (9,948 B, same size as every v-series ADT): mkpayload
    (payload-dev 16,609,824 B, payload-dbg 24,831,408 B - dbg ramdisk ends
    0x495adbb0, clear of the 0x50000000 kernel band), mkbootimg with header
    clone, verify-bootimg: **all 7 checks PASS** on both dev and dbg images
    (with a synthetic stock boot.img; the ROM stock pair is proven by the
    CI run below). Two extractor bugs were found and fixed during this:
    FDT header is 10 words not 9 (off_mem_rsvmap was being read as
    version), and the PROP len/nameoff pair is big-endian. Negative tests:
    foreign-identity DTB and no-/chosen DTB are both refused loudly.
- **image.yml design:** inputs `rom_url` (default pinned V12.0.3.0), 
  `stock_boot_url` (skip ROM, use own backup), `dev_run_id` / `dbg_run_id` /
  `shim_run_id` (default: newest green matching artifact - the kernel fetch
  walks `gh run list -w xnu -s success` and downloads until it finds
  `kernel.<config>.sweet`), `image_tag` (default v51), `build_images=false`
  (staged firmware-only run), `skip_debug`. Artifacts: `merlin-stock-firmware`
  (stock-boot.img + stock-merlin.dtb + header.txt) and
  `merlin-boot-image-<tag>` (dev + dbg images, payloads, merlin.adt,
  SHA256SUMS, FLASH-<tag>.md with flash instructions + the v49/v50 photo
  decision tree). ROM download: bigota -> bn.d.miui.com mirror fallback,
  resume + speed floor, stream-extract only `*boot.img` from the tgz.
  Permissions pinned to contents:read + actions:read (gh run download
  pattern proven by qemu.yml).
- Deviation vs v50 (record before flashing): kernel is xnu #40
  (`c713a04c`, includes 0089 - DEBUG-only code, DEVELOPMENT behavior
  unchanged) instead of the 0088-only build `8532cdfc`; ADT freshly
  generated (GICR reverted, same mkadt source); shim identical
  (`288cf8b1`); header/DTB from the official ROM instead of the user's
  backups. The photo decision tree is unchanged (the three SWEET GIC lines
  decide the timer/GICR fix).
- **Run ledger (workflow `image`):**
  - image #1 (42499899103, firmware-only): FAIL - bigota single-stream
    died mid-download at ~52 min; measured: **d.miui.com caps ~1.2 MB/s
    PER IP** on GitHub runners too.
  - image #2 (42504699574, firmware-only): FAIL - 16-way parallel ranges
    did no better (same per-IP cap), 35-min step timeout. Logs empty
    (runner killed mid-step).
  - image #3 (42508024983, firmware-only): FAIL - **self-deadlock**: the
    parts were complete at +2 min (watchdog log proves it) but a bare
    `wait` also waited on the throughput-watchdog subshell -> step hung
    to the 55-min cap. Fix: `wait "${pids[@]}"` on the curl PIDs only.
  - image #4 (42513186396, firmware-only): **GREEN** - the Alibaba OSS
    mirror (bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1) serves the
    full 3.5 GB at ~50-70 MB/s (~68 s); boot.img extracted (67,108,864 B,
    ANDROID! v2 header, page 2048, dtb slot @0x4bc80000, header_size 1660,
    os_version 0x14000147 vs the user backup's 0x16000157 - different
    firmware version, same layout); DTB extracted from the MTK-wrapped
    dtb slot: 108,879 B, fdt v17, **553 nodes, model MT6768, compatible
    mediatek,MT6768**, /chosen + /memory present, msdc0 + gic500 (the
    decoy) nodes all consistent with the hardware facts. Prefix stages
    (512 MiB / 1.5 GiB) extracted NOTHING: boot.img sits after the
    multi-GB images in the tgz - cascade removed (commit ce879fc).
  - image #5 (42513754159, FULL BUILD, @ce879fc): **GREEN, ~2.5 min**.
    Kernel picker worked as designed (skipped the DEBUG run for the dev
    image: "run 42493186867: not a development kernel, trying older").
    Inputs: shim run 42489231291 (288cf8b1, byte-identical to v45-v50),
    dev kernel run 42493163172 (#40, c713a04c, 0088+0089), dbg kernel run
    42493186867 (#41, e301b13e), stock = V12.0.3.0 ROM. Artifacts:
    `merlin-boot-image-v51` (25.4 MiB: both images, both payloads,
    merlin.adt, SHA256SUMS, FLASH-v51.md) + `merlin-stock-firmware`
    (stock-boot.img + stock-merlin.dtb + header.txt).
- **v51 READY (the pending flash test, downloadable):**
  - `shim-boot-merlin-v51-dev.img` SHA256
    `ba5f47709cb57ce9db4ccbc23105e6b70f4bf79f0e4a771c532884fa73e98d54`
    (16,732,160 B; payload-dev `5161d8439ae71cec4a9ed4ebd71f50ccf68a7c66cf4a50c62ed6cd1629b6c66e`,
    16,609,824 B)
  - `shim-boot-merlin-v51-dbg.img` SHA256
    `6fd95d3f5b9601363e8b35e327653d5cbb735e2a84559f74fe49361021518bb3`
    (24,952,832 B; payload-dbg `608f3f88bac9fd4e4fddda138bd313882816a8959a7d9dbdb853d92de69d8aae`,
    24,831,408 B)
  - merlin.adt `423bd2d1b56258d3e675f9d273296efcacf364d498454e1159360c83abbaf135`
    (9,948 B), stock-merlin.dtb `26afaecddf7907d7cf4ce0d69a0cedfa7fbec429aa2052ab22a1d8f67dbdd5e8`
    (108,879 B), stock-boot.img `6f1aa4abfc99ef24392135de28ba2a9faea780c34b279746812812e4fb8644f4`
    (67,108,864 B).
  - Both images re-verified INDEPENDENTLY on the agent machine against the
    downloaded artifacts (verify-bootimg: all 7 checks PASS, SHAs match
    the manifest byte-for-byte).
  - What to do: flash `-dev`, photo the BOTTOM of the screen (the three
    `SWEET GIC:` lines decide the timer/GICR fix per the v49/v50 decision
    tree - it is reproduced in FLASH-v51.md inside the artifact). `-dbg`
    only if the dev photo is inconclusive.
  - Fallback if v51 misbehaves at the LK/DTB level (shim banner shows DTB
    magic 0 / no boot at all - i.e. a DTB-provenance problem, NOT the
    expected timer wall): re-dispatch image.yml with `stock_boot_url`
    pointing at the user's own backup/stock-boot.img (e.g. attached to a
    GitHub release) for byte-exact v-series inputs, or use the local v50
    (out/shim-boot-merlin-v50-gicprobe.img, 75d72f06...) that is already
    READY on the user's Windows machine.
