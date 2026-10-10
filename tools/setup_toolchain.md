# Toolchain setup

The firmware needs an ARM GNU toolchain. Everything host-side (protocol,
tests, CLI, GUI) needs only Python 3.

## 1. ARM GNU Toolchain (arm-none-eabi-gcc)

Windows (verified on Windows 10/11 x64):

1. Download "ARM GNU Toolchain" (any recent version, e.g. 13.3 or 14.3) from
   https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
   - file: `arm-gnu-toolchain-<ver>-mingw-w64-x86_64-arm-none-eabi.zip`
2. Extract it, e.g. to `C:\xmc2go\toolchain\` so that
   `C:\xmc2go\toolchain\bin\arm-none-eabi-gcc.exe` exists
   (the build scripts search `..\toolchain\bin` and `C:\xmc2go\toolchain\bin`
   automatically; `tools/build_fw.py` also honours the `ARM_GNU` environment
   variable).
3. Or add the `bin` directory to `PATH` and use the Makefile normally.

Verify:

```
arm-none-eabi-gcc --version
```

## 2. GNU make (optional)

* If you have `make` (MSYS2, chocolatey `make`, WSL, ...): use the `Makefile`
  as documented in the README.
* If not: `python tools/build_fw.py all` performs the identical build steps
  (this is how the firmware was built during development).

## 3. Host-side Python

Python 3.8+ with **no extra packages**. Optional: `pyserial` (used
automatically when present); otherwise the stdlib ctypes/Win32 COM backend in
`host/updater/xmcup/serial_win32.py` is used. `tkinter` is required only for
the GUI (bundled with the standard Windows Python installer).

## 4. Host C tests (optional)

`tests/host_unit/run_c_vectors.bat` and `tests/host_fsm/run.bat` compile with
MSVC `cl.exe` (auto-located via vswhere / vcvars) or `gcc`. They are part of
`make host-test`.

## 5. DAVE (optional path)

See `tools/dave_import.md` if you prefer building inside DAVE.

## 6. J-Link driver (for flashing/recovery)

Install the SEGGER J-Link driver **including "Install USB Driver for
J-Link-OB with CDC"** so the XMC 2Go shows a virtual COM port. For recovery
reflashing see `docs/CAVEATS.md` section 6.
