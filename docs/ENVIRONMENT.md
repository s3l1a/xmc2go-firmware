# Development environment history (2026-10-10)

The project began in a minimal Windows workspace. Toolchain and hardware support
were installed later for the validation recorded in `docs/TEST_REPORT.md`.

## What exists on this PC

| Tool | Status | Notes |
|---|---|---|
| `arm-none-eabi-gcc` | Not present initially; later installed | firmware release built with ARM GNU Toolchain 14.3.Rel1 |
| `make` / `mingw32-make` | **NOT INSTALLED** | Makefile provided; GNU make needed for `make` targets |
| `cmake` | NOT INSTALLED | not used |
| `python` | **3.14.4** at `C:\Python314\python.exe` | stdlib only needed |
| `pip list` | many packages, **no `pyserial`**, **no `pytest`** | unittest is used |
| `pywin32` | present (311) | not required; our Win32 serial backend uses ctypes directly |
| `tkinter` | present (8.6) | GUI works |
| host C compiler (`gcc`, `clang`, `cl`) | `gcc`/`clang` **NOT on PATH**; **MSVC `cl.exe` 14.50.35717** present via `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars32.bat` | used to compile/run the host-side C tests |
| J-Link tools | Not present initially; later installed | release validation used SEGGER J-Link V9.84 |
| DAVE IDE / XMC Lib / CMSIS device headers | **NOT INSTALLED** | we provide our own minimal register header |
| Board attached | Not attached initially; later connected | release HIL results are in `TEST_REPORT.md` |

## What was implemented because tools were missing

1. **Build system**: `Makefile` (GNU make + `arm-none-eabi-gcc`) and the equivalent
   `tools/build_fw.py`. Exact install steps are in `tools/setup_toolchain.md`.
   The Python build driver was later run successfully for release validation.
2. **Device headers**: `board/xmc1100_regs.h` — minimal, only registers we use.
   All addresses and bit positions were **verified against**:
   * Keil/CMSIS `XMC1100.h` (SVD-generated from the XMC1100 Reference Manual v1.0),
     fetched from `https://www.keil.com/dd/docs/arm/infineon/xmc1100/xmc1100.h`
   * XMC1100 Reference Manual v1.0 (2013-03), PDF fetched from keil.com
     (`xmc1100_rm_v1_0_2013_03.pdf`), chapters 2 (CPU/vecs), 8 (NVM), 10 (WDT),
     12 (SCU/clock), 14 (USIC), 17 (Ports), 18 (Boot/SSW)
   * XMC1100 AB-Step Datasheet v2.1 (pin mux, Table 9)
   * Board schematic (Figure 5 of the board user manual) for the LED/UART nets
   Nothing is invented. Items that could not be fully confirmed are marked
   `TODO(verify)` in the sources (see list below).
3. **Serial on host**: `host/updater/xmcup/serial_win32.py` — stdlib-only Windows
   backend using ctypes against the Win32 COM API (CreateFileW, SetCommState,
   GetCommState, SetCommTimeouts, ReadFile, WriteFile, registry enumeration
   `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM`). `serial_pyserial.py` is used
   automatically if pyserial is importable. `serial_fake.py` backs the unit tests.
4. **Host tests**: Python `unittest` (no pytest needed). The C-side CRC test
   vectors and the traffic FSM tests are compiled with MSVC `cl.exe` (since gcc is
   absent) via `tests/host_unit/run_c_vectors.bat` and `tests/host_fsm/run.bat`;
   the Makefile also offers `gcc`-based equivalents (`make host-test`) for when
   GNU tools are installed.

## Verified vs. unverified

Verified (by running here):
* All `tests/host_unit` Python tests (CRC, framing, image header, metadata state
  machine, update flow) — see `docs/TEST_REPORT.md`.
* `tests/host_fsm` traffic FSM tests compiled and run with MSVC cl.exe.
* CRC16/CRC32 C vectors compiled and run with MSVC cl.exe (cross-checked with the
  Python implementation).

The firmware build and HIL suite were run later; see `docs/TEST_REPORT.md` for
the exact validated scope and remaining limitations.

`TODO(verify)` items in code:
* `board/xmc1100_regs.h`: none outstanding for addresses used (all from CMSIS SVD
  header or RM text). `NVMCONF.WS`/`NVMCONF` unlock semantics noted in
  `bootloader/flash` comments.
* `board/flash.c`: `NVMCONF.SECPROT` hardware write-protection of the bootloader
  sector is compiled in but **disabled by default** (`FLASH_SECPROT_ENABLE 0`),
  because the interaction with J-Link recovery reflashing could not be tested.
* Exact SSW clamp behavior for `CLK_VAL1.IDIV` (RM 18.1.3.1 says 1..16) is taken
  from the RM; our bootloader sets IDIV=1 (32 MHz) which is inside the range.
