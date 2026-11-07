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
