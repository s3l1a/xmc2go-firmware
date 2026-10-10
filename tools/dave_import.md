# Optional: building inside DAVE

DAVE (Infineon's free IDE, https://www.infineon.com/dave) can be used instead
of the GNU toolchain. The sources in this project are plain C11 + one GNU
assembler file (`board/startup.S`) + GNU ld scripts; DAVE projects use GCC
internally, so everything compiles as-is except the linker script choice.

## Project creation

1. File > New > DAVE Project; select device **XMC1100-Q024x0032** (or x0064),
   package VQFN-24.
2. Create one project per image you want to build (e.g. `xmc2go_bootloader`,
   `xmc2go_app_traffic_A`).
3. Add the source folders to the project:
   - bootloader project: `bootloader/`, `board/`, `common/`
   - app project: `app_traffic/` (or `app_bad`/`app_crash`), `board/`, `common/`
   - Exclude nothing; `board/startup.S` replaces DAVE's generated startup, so
     **remove/disable DAVE's own `startup_XMC1100.S` / `system_XMC1100.c`** to
     avoid duplicate symbols (`Reset_Handler`, `SystemInit`, handler names).
4. Include paths: `common`, `board`, plus the app folder.
5. Linker script: use our `board/link_bootloader.ld` (bootloader) or
   `board/link_slotA.ld` / `link_slotB.ld` (apps). In DAVE's project settings
   (C/C++ Build > Settings > ARM-GNU C Linker > Script file) point at the
   matching file. Note the apps link at `slot + 0x20` because the host image
   builder prepends the 32-byte header.
6. Compiler flags: `-std=c11 -Os -mcpu=cortex-m0 -mthumb` (DAVE defaults are
   fine; keep `-mcpu=cortex-m0`).

## What DAVE cannot replace

- The image header (`tools/mkimage.py`) must still be added to the raw binary
  before sending it to the device (`python tools/mkimage.py ...` or the GUI/CLI
  which can wrap a raw `.bin` on the fly).
- The boot/rollback logic is ours (`bootloader/main.c`); DAVE apps or
  device-config-generated clocks must not overwrite `board/system.c`'s
  `SystemInit` unless you keep the CLK_VAL1/CLK_VAL2 contract documented in
  `docs/DESIGN.md` (32 MHz MCLK, CCU40/USIC0/WDT clocks enabled).

## BMI warning

Do not use DAVE's "BMI Get Set" tool on this board (see `docs/CAVEATS.md`).
