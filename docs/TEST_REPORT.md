# TEST REPORT (2026-10-10)

Environment: Windows 10/11 x64, Python 3.14.4, MSVC cl 14.50 (host C tests),
ARM GNU Toolchain 14.3.Rel1 (firmware build), SEGGER J-Link V9.84, and an
XMC 2Go board attached through its J-Link virtual COM port.

Legend: [run and passed] / [run and failed] / [not run (requires hardware)]

## 1. Host unit tests - `tests/host_unit` (Python unittest)

**[run and passed]** - 73 tests, all OK (2.5 s)

```
python -m unittest discover -s tests/host_unit -v
Ran 73 tests in 2.457s
OK
```

| Test file | Covers | Result |
|---|---|---|
| `test_crc.py` | CRC16-CCITT-FALSE + CRC32-IEEE against published check values ("123456789" -> 0x29B1 / 0xCBF43926), empty/single-byte vectors, incremental == block | passed |
| `test_framing.py` | frame encode/decode round trip, bad CRC dropped + resync, bad SOF hunt, truncated frames, oversized LEN, garbage between frames, exact PING frame bytes `A5 01 01 00 00 44 C5` | passed |
| `test_image.py` | header build/parse, CRC failures, length/slot checks, entry inside payload, Thumb reset vector, reset/header match, SRAM stack pointer | passed |
| `test_metadata.py` | record CRC round-trip/corruption, boot decision: normal boot, trial increments attempts, rollback after 2 failed trials, healthy clears trial, invalid image never booted (rollback/recovery), second-slot trial, single-bank log scan | passed |
| `test_update_flow.py` | end-to-end update against a scripted device: happy path (erase/write/verify/set-active/trial/boot), erase+write of active slot refused, out-of-bounds write refused, SET_ACTIVE without verify refused, verify failure keeps old slot, corrupt image rejected on host before touching the device, cancel before/during update keeps old slot, stalled transfer aborts safely, flash errors keep old slot | passed |
| `test_c_cross_check.py` | compiles `tests/host_unit/c_vectors.c` against `common/` with MSVC cl.exe and checks the C known-answer vectors match | passed |

## 2. C known-answer vectors - `tests/host_unit/c_vectors.c`

**[run and passed]** - `run_c_vectors.bat` -> `ALL C VECTORS PASS` (41 checks)

CRC16/CRC32 vectors identical to the Python tests, `sizeof(meta_record_t)=16`,
`sizeof(image_header_t)=32`, the metadata boot-decision scenarios
(normal / trial-attempt / rollback / exhausted / invalid-active / both-invalid /
healthy / record corruption) matching the Python reference, and the flash
range-check matrix: bootloader region, CS0 (BMI sector), and slot-crossing
ranges rejected; slot A/B blocks/pages and both metadata banks accepted.

## 3. Traffic FSM tests - `tests/host_fsm` (compiled with MSVC cl.exe)

**[run and passed]** - `run.bat` -> `ALL FSM TESTS PASS (81 checks)`

Covers: timing table values, state names, init outputs, every timed transition
(GREEN->YELLOW->RED->GREEN with a fake 1 ms clock), pedestrian request queued
in GREEN/YELLOW/RED and served at the safe point, request during the walk
phase queued for the next cycle, LED output patterns (green/yellow/red/walk
blink), RESET_CYCLE from every state incl. FAULT, INVALID event -> FAULT,
FAULT stability under ticks, ignored events in FAULT, status event, remaining
time computations.

(The suite uses MSVC `cl.exe` because no gcc is installed here; `run.bat` and
the Makefile also support gcc.)

## 4. Firmware build

**[run and passed]** - `python tools/build_fw.py all` with arm-none-eabi-gcc
14.3.Rel1, zero warnings (`-Wall -Wextra`):

| Image | Flash | Notes |
|---|---|---|
| bootloader | 5456 B / 8 KB | veneer section 276 B at 0x2000000C |
| app_traffic A/B | 3652 B / 8160 B | incl. FSM + logging |
| app_bad A/B | 1320 B | |
| app_crash A/B | 1072 B | |

Structural checks on the produced binaries (verified with objdump/readelf):
* `.isr_vector`: SP = 0x20004000 (RAM top), reset = Thumb address inside the
  image, CLK_VAL1 = 0x00000100 (32 MHz), CLK_VAL2 = 0x0000020C.
* `.VENEER_Code` VMA 0x2000000C with exactly the RM Table 2-10 layout:
  HardFault veneer at 0x2000000C, 7 reserved slots, SVCall at 0x2000002C,
  2 reserved, PendSV at 0x20000038, SysTick at 0x2000003C, IRQ0..IRQ31 at
  0x20000040 + 4*n, then the literal pool at 0x200000C0.
* Image files: magic "XCM1", entry point == vector word 1, payload CRC ok
  (re-checked by `mkimage.py` and the host unit tests).

## 5. Host tooling smoke tests

**[run and passed]**
* `python -m py_compile host/gui/gui.py host/cli/main.py` OK.
* `python host/cli/main.py list` behaves correctly with no board attached
  ("no COM ports found").
* `python host/cli/main.py --help` prints the full command set.

## 6. Hardware-in-the-loop tests - `tests/hil` (XMC 2Go board)

**All seven ran on the release build and PASS:**

| Script | Scenario | Result |
|---|---|---|
| `test_update_and_boot.py` | update inactive slot with app_traffic, boot, expect healthy + valid + attempts 0 | **[run and passed]** slot A active, healthy, v1.0.0 |
| `test_rollback_bad.py` | flash app_bad (never healthy, no watchdog service) | **[run and passed]** automatic rollback to previous slot, failed slot marked `bad` |
| `test_rollback_crash.py` | flash app_crash (HardFault before healthy) | **[run and passed]** crash + watchdog -> rollback to previous slot, failed slot marked `bad` |
| `test_watchdog_healthy.py` | run app_traffic 3 minutes | **[run and passed]** no spurious reset: 180 s of monotonic timestamps, exactly 1 healthy mark, slot `valid` attempts 0 at the end |
| `test_power_loss_during_update.py` | interrupt an update mid-write, old slot must survive | **[run and passed]** interrupted update left old slot intact + bootable; retry succeeded |
| `test_write_bounds.py` | malicious cross-slot, metadata, and wrapping offsets | **[run and passed]** all rejected; active slot remained valid |
| `test_vector_validation.py` | CRC-consistent image with an invalid initial SP | **[run and passed]** device verification rejected it; inactive image restored |

Additional hardware checks performed during bring-up:
* Bootloader banner + PING/INFO round-trip over the J-Link VCOM at 115200.
* `X` serial command resets from app into the bootloader update window.
* Traffic light FSM timing verified on target: transitions at 5001/7001/12001 ms
  (5 s green / 2 s yellow / 5 s red) with timestamps from the CCU40 tick.
* Factory demo backed up before flashing (`dist/factory_backup.bin`,
  `dist/factory_cs0_backup.bin`, BMI 0xFAC3 confirmed = SWD1 user mode).

## 6b. Hardware bring-up bugs found and fixed (all verified on-target)

These were found by SWD register inspection and fixed in `board/`:

1. **`P2_PDISC` reset disables every P2 pad** (RM 17.8.3: PDISx=1 = pad
   disabled). Nothing reached the pins until `uart_init` enabled P2.1/P2.2.
2. `SCTR.TRM = 00b` makes "data frame transfers not possible" (RM 14.11) —
   must be `01b`; `SCTR.PDL` must be 1 (UART idle-high).
3. `TCSR.TDEN = 00b` gates off transmission start (RM 14.11.7.2) — must be
   `01b`; `TCSR.TDSSM = 1` clears TDV at TBI.
4. `PSR.TBIF` is an event (set at start of a frame) — waiting for it before the
   first byte deadlocked `uart_putc`; tracked with `s_tx_busy`.
5. `NVIC_ISER` is at `0xE000E100` (ARMv6-M standard; the SVD header's struct
   offset 0x108 is wrong) — timer interrupts were silently not enabled.
6. `GCSS.S0SE` (bit 0) is the period/compare **shadow transfer**; `S0PSE`
   (bit 2) is the *prescaler* transfer — PRS never reached PR.
7. `jump_to_app` runs `cpsid i` for the MSP handoff; every image must re-enable
   with `cpsie i` (added to `SystemInit`) or all ISRs stay masked.
8. Flash auto-verify (`ACTION=0x51`, hardread levels) reported false failures
   on marginally-erased blocks; block writes now verify by software readback
   and page erases verify by readback with one retry.

## 7. Not verified (and why)

* **`NVMCONF.SECPROT` hardware protection** - compiled in but disabled
  (`FLASH_SECPROT_ENABLE 0`), because its effect on J-Link recovery flashing
  could not be tested (TODO(verify)).
* **GNU `make` build** - make is not installed here; the Makefile mirrors the
  verified `tools/build_fw.py` steps one-to-one but has not itself been run.
* **GUI against a real device** - compiles (py_compile) and the library it uses
  is exactly what the CLI/HIL scripts exercised on hardware; the interactive
  Tk session itself was not launched here.
* Real power-pull during an update (the automated variant simulates the
  interrupted-transfer path; the manual USB-unplug procedure is documented in
  `tests/hil/test_power_loss_during_update.py`).
