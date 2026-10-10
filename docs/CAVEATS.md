# CAVEATS - hardware and safety notes

## 1. Never change the BMI / debug configuration

The XMC1100 is configured to **SWD1 user mode with debug** (BMI `0xFAC3`).
The board manual warns that the "BMI Get Set" tool can make the board
unusable (SWD0/SPD0/productive user mode). This project therefore:

* never writes the configuration sector CS0 (`0x10000000..0x10000FFF`, BMI at
  `0x10000E00` + inverse at `0x10000E10`);
* never calls the ROM "Request BMI installation" routine (`0x00000108`);
* locks CS0 out of every flash write path in `board/flash.c`
  (`flash_range_is_writable()` rejects it).

Do not add code that changes the BMI. Productive user mode would permanently
disable the debug interface on this board.

## 2. Bootloader region protection

* Software: `board/flash.c` refuses any erase/write outside slot A, slot B and
  the two metadata sectors. ERASE_SLOT/WRITE_CHUNK additionally refuse the *active*
  slot so the previous image always survives an update. This is unit-tested
  (`tests/host_unit/test_update_flow.py`).
* Hardware (optional, **disabled by default**): `NVMCONF.SECPROT` can protect
  sectors 0..N-1 from any modification. It is compiled behind
  `FLASH_SECPROT_ENABLE 0` because the interaction with J-Link recovery
  reflashing is unverified (TODO(verify)).

If the bootloader is erased or corrupted, recovery requires the onboard J-Link
debugger (section 6).

## 3. Flash endurance

* Page erase (256 B) is only done for slot updates and when a metadata log bank
  is full. Two append-only banks alternate at rollover, preserving the newest
  valid record while the other bank is erased. Normal healthy boots do not
  write metadata.
* Slot updates erase 32 pages and write the image once; do not script
  thousands of update cycles (a 2 MB/s limit is not the issue - raw flash
  endurance is).

## 4. Power

* The board draws about 75 mA; the 3.3 V header pin is limited to 150 mA. No
  external circuitry is required or assumed by any part of this project.
* Interrupted transfers leave the old slot active. Record CRCs reject torn
  writes, and dual metadata banks are designed to preserve the previous state
  during rollover. Automated interruption tests pass; a physical power pull
  during metadata rollover has not been performed.

## 5. Watchdog

* The watchdog is armed only just before booting an app. During the
  bootloader's update session it is OFF (long flash transfers must not be
  interrupted); stalled host transfers are handled by the 5 s protocol
  timeout instead.
* `WLB = 0` disables the WDT window so servicing is legal at any time; a wrong
  service value (`!= 0xABADCAFE`) still causes an immediate reset (RM 10.4).
* Apps MUST call `app_service_watchdog()` in their main loop and
  `app_mark_healthy()` within the 5 s trial window. Forgetting either yields a
  reset loop and finally rollback (this is exactly what app_bad/app_crash
  demonstrate).
* `WDT.CTR.DSP = 0` keeps the watchdog stopped while a debugger halts the CPU,
  so debugging sessions do not trigger resets.

## 6. Recovery procedure (bootloader lost)

1. Install DAVE (or J-Link tools) and the J-Link driver **with the CDC USB
   driver** so the virtual COM port appears.
2. Keep the known-good bootloader binary `dist/bootloader.bin` (built by
   `python tools/build_fw.py bootloader` or `make`).
3. Erase + program the bootloader region with J-Link / DAVE / Memtool:
   * device: XMC1100-Q024x0032 (or x0064),
   * address `0x10001000`, file `dist/bootloader.bin` (raw binary, 5456 bytes),
   * do **not** touch `0x10000000..0x10000FFF` (CS0/BMI).
4. Reset the board; the bootloader prints its banner on the virtual COM port
   (115200 8N1) and either boots the app or waits in recovery mode when no
   valid image is present.

Example J-Link commander script (adapt the path):
```
device XMC1100-Q024x0032
si swd
speed 4000
connect
loadbin C:\xmc2go\project\dist\bootloader.bin, 0x10001000
r
g
exit
```
Never use "BMI Get Set"/BMI programming during recovery.

## 7. Interrupts and flash

* ISRs in this project are tiny (CCU40 tick counter only). No flash operation
  is performed from an interrupt; all flash writes run from the main loop with
  interrupts effectively irrelevant (the NVM FSM stalls the bus while busy).

## 8. LED mapping inconsistency in the board manual

Section 0 of the task and `common/config.h`: the manual contradicts itself
about the LEDs (Table 1 + Figure 1 + schematic say LED1 = P1.0 / LED2 = P1.1;
section 2.3 text says P1.0 and P1.2; Table 2 swaps LED1/LED2). We follow the
**schematic (Figure 5)**. Verify on your board which physical LED is LED1; only
`CFG_LED1_*`/`CFG_LED2_*` in `common/config.h` need to change. P1.2 is the
SWDCLK pin (Table 3) so it is almost certainly not an LED.

## 9. Pin header X1/X2 pinout text

The manual's X1/X2 pinout refers to a TSSOP-16 package while the chip is
VQFN-24; do not rely on it. The schematic net names are authoritative.

## 10. Host serial backend

The stdlib Win32 backend uses the COM API directly. USB serial adapters
usually need no flow control; the backend enables DTR/RTS and no XON/XOFF. If
a particular adapter needs RTS/CTS, adjust `serial_win32.py` (`_set_flags`).
