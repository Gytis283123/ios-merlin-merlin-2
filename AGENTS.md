# Working on ios-merlin-merlin-2

- Read `NOTES.md` before starting; it contains the project goal, hardware
  facts (with sources), the milestone plan, current state and the next
  concrete action.
- The user switches agents frequently. Update the active handoff in
  `NOTES.md` after each milestone and before stopping. Record commits, CI
  run IDs, artifact SHA256s, exact build/boot results and unfinished work.
  Distinguish observations from guesses.
- **Do not use the older merlin work** (forks `Gytis283123/ios-merlin`,
  `Gytis283123/ios-sweet`, their patch series 0082–0122, or packaged images
  from Downloads) — the user decided (2026-11-06) the merlin layer is remade
  from first principles in this repo. Do not read or diff those patch series;
  base new work on the upstream `dipa-studio/ios-sweet` foundation and
  primary hardware documentation (the device's own kernel source, live DTB).
- Kernel builds come from GitHub Actions in this repo only. The WSL
  cross-compiler is banned (its kernels did not boot). Local single-file
  syntax checks are fine before spending a CI run.
- Device bring-up uses temporary `fastboot boot` images only. Never flash
  (no partition writes) without explicit user confirmation in the moment;
  preserve bootloader, recovery, modem, persist and partition backups.
- Keep device dumps, serial numbers, DTBs pulled from the device and
  downloaded Apple artifacts out of git (`.gitignore` covers backup/, dtb/,
  recovery/, research/, out dirs).
- Commit completed changes; one milestone per commit; descriptive messages.
