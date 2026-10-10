# XMC 2Go custom bootloader + host update tool

Custom A/B-slot bootloader with watchdog rollback for the Infineon XMC 2Go
kit (XMC1100, Cortex-M0), a traffic-light demo application, and a Python host
updater (GUI + CLI) that works **without pyserial** (stdlib Win32 COM API).

Downloadable binaries and end-user installation steps are available on the
[Releases](https://github.com/s3l1a/xmc2go-firmware/releases) page. Read
`docs/RELEASE_INSTALL.md` before programming a board.

Layout (see `docs/DESIGN.md` for the full design):

```
bootloader/     8 KB bootloader: protocol, boot/rollback state machine
app_traffic/    traffic light FSM app (marks healthy, services watchdog)
app_bad/        never reports healthy  -> rollback test image
app_crash/      HardFault before healthy -> rollback test image
common/         image header, CRC16/CRC32, protocol constants, config
board/          startup (veneers), linker scripts, LED/UART/WDT/flash/timer
host/updater/   Python package (framing, image builder, serial backends)
host/gui/       Tkinter GUI (threaded, cancellable updates)
host/cli/       command-line updater
tests/          host unit tests, FSM tests (gcc/MSVC), HIL scripts
docs/           ENVIRONMENT, DESIGN, PROTOCOL, CAVEATS, TEST_REPORT
tools/          mkimage.py, build_fw.py, setup_toolchain.md, dave_import.md
```

## Build

```
# firmware (needs arm-none-eabi-gcc, see tools/setup_toolchain.md)
python tools/build_fw.py all        # or: make && make images

# host tests (no hardware, nothing to install)
python -m unittest discover -s tests/host_unit -v
tests\host_fsm\run.bat
```

`python tools/build_fw.py all` produces:

| File | Purpose |
|---|---|
| `build/bootloader.bin` | flash at 0x10001000 (also kept in `dist/` for recovery) |
| `build/app_*_[AB].bin` | raw apps linked for slot A/B |
| `dist/app_*_[AB].img` | images with header, for the updater |

## Flash the bootloader (first time / recovery)

Use J-Link / DAVE / Memtool to program `build/bootloader.bin` at **0x10001000**
(never touch 0x10000000..0x10000FFF - the BMI lives there). Details and a
J-Link script: `docs/CAVEATS.md` section 6.

## Update an application over USB

GUI:

```
python host\gui\gui.py
```

* Refresh -> pick the COM port (the XMC 2Go's J-Link VCP is highlighted).
* Connect -> device status appears (bootloader version, slots, attempts).
* Browse... -> pick `dist/app_traffic_A.img` (or a raw `.bin`; it is wrapped
  with a header on the fly).
* Update -> progress bar; the *inactive* slot is programmed, verified, marked
  trial and the board reboots.
* Rollback / Reboot buttons, log panel with optional full hex dumps.
* Cancel is always safe: the old slot stays active and bootable.

CLI (same operations, scriptable):

```
python host\cli\main.py list
python host\cli\main.py --port COM5 info
python host\cli\main.py --port COM5 update dist\app_traffic_A.img
python host\cli\main.py --port COM5 update build\app_traffic_A.bin --ver 1.2.0 --build 7
python host\cli\main.py --port COM5 verify
python host\cli\main.py --port COM5 rollback
python host\cli\main.py --port COM5 reboot
```

**Reaching the bootloader again:** the app owns the UART once it runs. Either
press the board's RESET button while the GUI/CLI is trying to connect (the
bootloader listens for 1-2 s after reset), or use the traffic app's `X`
command (serial terminal) which resets into the bootloader. While an unhealthy
app (app_bad/app_crash) is installed, watchdog resets open the window
repeatedly.

## Traffic light app

Serial console (115200 8N1 on the J-Link VCP):

* `P` pedestrian button - walk phase at the next safe point (after the red)
* `R` reset the cycle
* `S` print state + time remaining
* `X` reset into the bootloader (development helper)

LED mapping (only two LEDs; see `common/config.h` for the manual's LED
inconsistency): LED1 = green, LED2 = red, yellow = both, walk = LED1 blinking
while LED2 holds red, fault = both blink. All transitions are logged as
`"<ms>: OLD-> NEW"`.

## Tests

```
python -m unittest discover -s tests/host_unit -v   # 73 host tests
tests\host_unit\run_c_vectors.bat                   # C/Python cross-check
tests\host_fsm\run.bat                              # traffic FSM (81 checks)

# hardware-in-the-loop (board required), one at a time:
python tests\hil\test_update_and_boot.py [COMx]
python tests\hil\test_rollback_bad.py [COMx]
python tests\hil\test_rollback_crash.py [COMx]
python tests\hil\test_watchdog_healthy.py [COMx] [--minutes 3]
python tests\hil\test_power_loss_during_update.py [COMx]
```

Results and what could not be run here: `docs/TEST_REPORT.md`.
Safety rules and recovery: `docs/CAVEATS.md`.

## Security scope

This project is intended for development boards. Firmware images and protocol
frames have CRC integrity checks but no signatures or authentication. Do not
use this updater as-is where untrusted users can access the serial port.
