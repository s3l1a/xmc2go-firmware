# DESIGN - XMC 2Go custom bootloader

Target: Infineon XMC 2Go kit, XMC1100 (Cortex-M0, 32 MHz, 16 KB RAM),
minimum flash 32 KB (XMC1100-Q024F0032). All register facts used here are
verified from the XMC1100 Reference Manual v1.0 (RM) / CMSIS XMC1100.h /
XMC1100 datasheet (sources in `docs/ENVIRONMENT.md`).

## 1. Boot model of the XMC1100 (why the layout looks like this)

* The Cortex-M0 core has **no VTOR**. The ROM vector table at `0x00000000`
  hard-codes RAM addresses for every exception (RM Table 2-10):

  | Vector | RAM address |
  |---|---|
  | HardFault | `0x2000000C` |
  | SVCall | `0x2000002C` |
  | PendSV | `0x20000038` |
  | SysTick | `0x2000003C` |
  | IRQn | `0x20000040 + 4*n` |

  Region `0x2000000C..0x200000BF` must be reserved for this "remapped vector
  table". Each 4-byte slot holds a veneer `LDR R0,=handler / BX R0`
  (`board/startup.S`). The build verifies the veneer section lands at exactly
  these addresses (see TEST_REPORT.md).
* The startup software (SSW, in ROM) reads the **initial SP from `0x10001000`**
  and jumps to the address at **`0x10001004`** (= image start + 4) in user mode.
* Two extra words in the image header area are consumed by the SSW
  (RM 18.1.3.1): `CLK_VAL1` at image+0x10 installs `SCU_CLKCR[19:0]` and
  `CLK_VAL2` at image+0x14 installs `SCU_CGATCLR0[10:0]`, both only when bit31
  is 0. Our images use CLK_VAL1 = `0x100` (IDIV=1 -> MCLK 32 MHz) and
  CLK_VAL2 = `0x20C` (CCU40 + USIC0 + WDT clocks enabled).
* SRAM `0x200000C0..0x20000200` is used by the SSW across (non-power) resets -
  we only keep re-initializable data there (the veneer literal pool).

## 2. Flash map (32 KB device)

Program flash starts at `0x10001000`. `0x10000000..0x10000FFF` is the
configuration sector CS0 which contains the **BMI** at `0x10000E00`; it is
never written by this project (changing the BMI can brick the board).

Erase unit = **256 B page**, write unit = **16 B block** (4 words, ECC is
generated automatically), protection unit = 4 KB sector (RM 8.2, 8.3).

```
0x10000000  CS0: BMI, chip ID, calibration     (NEVER WRITE)
0x10001000  +------------------------------------------------+
            | Bootloader                     8 KB (2 sectors) |  0x10001000..0x10002FFF
0x10003000  | Slot A                         8 KB (2 sectors) |  0x10003000..0x10004FFF
0x10005000  | Slot B                         8 KB (2 sectors) |  0x10005000..0x10006FFF
0x10007000  | Metadata log bank 0            4 KB (1 sector)  |  0x10007000..0x10007FFF
0x10008000  | Metadata log bank 1            4 KB (1 sector)  |  0x10008000..0x10008FFF
0x10009000  +------------------------------------------------+
```

Justification:
* Equal 8 KB slots keep A/B symmetric (simplest rollback model) and every test
  app links well below 4 KB.
* Sector alignment (4 KB) keeps erase simple and leaves the option of hardware
  sector protection (`NVMCONF.SECPROT`) for the bootloader region.
* Two metadata banks preserve one complete record while the other bank is
  erased during log rollover.

On a 64 KB device the same map is used; the remaining flash stays free.

## 3. RAM map (16 KB)

```
0x20000000..0x2000000B  unused
0x2000000C..0x200000BF  remapped vector table (veneers, 4 B per slot)
0x200000C0..            veneer literal pool (SSW-transient area, re-inited)
0x20000200..            .data / .bss
..0x20004000            stack (grows down from RAM top)
```

## 4. Image format (per slot)

32-byte header + raw application binary (little-endian, `common/image.h`):

| Offset | Size | Field |
|---|---|---|
| 0x00 | 4 | magic `0x314D4358` (bytes `XCM1`) |
| 0x04 | 2 | format version (1) |
| 0x06 | 2 | slot id (0 = A, 1 = B) |
| 0x08 | 3 | version major/minor/patch |
| 0x0B | 1 | reserved (0) |
| 0x0C | 4 | build number |
| 0x10 | 4 | payload length |
| 0x14 | 4 | payload CRC-32 (IEEE) |
| 0x18 | 4 | entry point (app reset handler, must equal vector word 1) |
| 0x1C | 4 | header CRC-32 (IEEE over bytes 0..0x1B) |

The raw binary is linked at `slot_start + 0x20`; its first 24 bytes are the
XMC1100 user vector table (`[SP][reset][0][0][CLK_VAL1][CLK_VAL2]`). The
bootloader validates magic, version, header CRC, slot id, length (must fit the
slot), initial SP (aligned and in SRAM), reset vector (equal to the header entry
point, inside the payload, Thumb bit set) and payload CRC before booting.
Payload length + CRC cover exactly the raw binary; the updater pads
the last flash block with `0xFF` which is outside the CRC scope.

## 5. Metadata (persistent boot state)

16-byte record = one flash block (`common/metadata.h`):

| Offset | Size | Field |
|---|---|---|
| 0x00 | 4 | magic "META" |
| 0x04 | 4 | sequence number (monotonic) |
| 0x08 | 1 | active slot |
| 0x09 | 1 | slot A flags (VALID=1, TRIAL=2, BAD=4) |
| 0x0A | 1 | slot B flags |
| 0x0B | 1 | trial boot-attempt counter |
| 0x0C | 2 | boot count (informational) |
| 0x0E | 2 | CRC-16/CCITT over bytes 0..0x0D |

**Wear leveling / atomicity:** each 4 KB bank holds 256 blocks. Records append
to the active bank; the valid record with the highest sequence across both
banks wins. A torn append fails its CRC and leaves the previous record valid.
When a bank fills, the other bank is erased and receives the next record before
the full bank is touched. This keeps one valid record throughout rollover. A
full update uses about two records, and normal healthy boots do not write.

## 6. Boot/rollback state machine

`meta_boot_decision()` (pure logic, unit-tested in Python *and* C):

```
on reset:
  rec = newest valid metadata record (or defaults)
  active_ok = image(active slot) passes header+payload CRC
  other_ok  = image(other slot) passes header+payload CRC

  if !active_ok:
      if other_ok: ROLLBACK (mark active BAD, switch to other) else RECOVERY
  elif flags[active] has TRIAL:
      attempts++
      if attempts > CFG_WDT_TRIAL_ATTEMPTS (2):   # app never reported healthy
          mark active slot BAD
          if other_ok: ROLLBACK to other else RECOVERY
      else:
          persist attempts, BOOT active in trial mode
  else:
      BOOT active
```

Then a 1-2 s recovery window: if the host speaks the protocol (PING), the
bootloader enters update mode. If no valid image exists it stays in recovery
until the host fixes things. Otherwise it arms the watchdog (5 s) and jumps to
the app.

Trial lifecycle:
1. Host update: erase inactive slot -> write chunks -> VERIFY -> SET_ACTIVE
   (writes `active = slot`, `flags |= VALID|TRIAL`, `attempts = 0`) -> BOOT.
2. Bootloader arms the WDT and jumps; the attempt counter is bumped **in
   flash before the jump** so a watchdog reset is observable.
3. The app calls `app_mark_healthy()` within the trial window: it clears TRIAL
   (leaves VALID) and services the watchdog. After that the app keeps calling
   `app_service_watchdog()` in its main loop.
4. If step 3 never happens, the WDT resets the board; after 2 failed attempts
   the bootloader marks the slot BAD and rolls back (step 1 rules for the
   other slot).

RAM is *not* relied on across resets: the WDT/system reset leaves RAM in an
unknown state on this device (RM Table 12-3: SRAM "unreliable" after
power-on reset), so all state lives in the metadata log.

## 7. Watchdog

* XMC1100 WDT is a **window watchdog** clocked by the 32.768 kHz standby
  clock (RM chapter 10). Service = write magic `0xABADCAFE` to `WDT.SRV`.
  Servicing with a wrong magic or below `WLB` causes an immediate reset.
* We set `WLB = 0` which **disables the window** (RM 10.9.1), so the dog can
  be serviced at any count - a plain timeout watchdog. `WUB = 5*32768-1` =
  163839 gives a ~5.0 s timeout (CFG_WDT_TIMEOUT_MS).
* `CTR.DSP = 0` stops the watchdog while a debugger halts the CPU (debug
  friendly).
* The bootloader arms the WDT only when it is about to jump to an app. During
  an update session the WDT is off so long flash transfers cannot be
  interrupted by it (the host-side timeout aborts stalled transfers instead).

## 8. Traffic light application

* Pure FSM core (`app_traffic/traffic_fsm.c`) with a timing table
  (`TRAFFIC_TIMING`: green 5 s, yellow 2 s, red 5 s, walk 4 s).
* States: `NORMAL_GREEN`, `NORMAL_YELLOW`, `NORMAL_RED`,
  `PEDESTRIAN_REQUEST` (the pedestrian walk phase, entered at the safe point
  after the vehicle red when a request is pending), `FAULT` (invalid event;
  leaves only via RESET_CYCLE).
* LED mapping (only 2 LEDs): LED1 = green aspect, LED2 = red aspect,
  yellow = both on, walk = LED2 on + LED1 blinking, fault = both blink.
* Timing source: CCU40 slice 0, 1 ms period match interrupt (IRQ 21) - no
  busy waits. Inputs `P`/`R`/`S` (and `X` = reset into bootloader) come from
  the J-Link virtual COM port; the board has no buttons.
* Every state transition is logged as `"<ms>: OLD-> NEW"`.

## 9. Host link protocol

See `docs/PROTOCOL.md`. Summary: `SOF 0xA5 | CMD | SEQ | LEN(2 LE) | PAYLOAD |
CRC16-CCITT over CMD..PAYLOAD`, responses echo CMD with a status byte first.
The C (`bootloader/proto.c`) and Python (`host/updater/xmcup/framing.py`)
implementations are byte-identical and cross-checked by test vectors.

## 10. Safety rules (enforced in code)

* `board/flash.c` rejects any erase/write outside the two slots and two
  metadata sectors (software lockout of the bootloader region and CS0).
* ERASE_SLOT/WRITE_CHUNK refuse the **active** slot (the old image always
  survives an update).
* WRITE_CHUNK bounds: 16-byte aligned offset/length, must fit the slot.
* SET_ACTIVE_SLOT requires a successful VERIFY_SLOT in the same session
  (slot-switch only after verification; invalid images never become active).
* Stalled transfers (>5 s idle) exit update mode and boot the old slot.
* Cancellation on the host stops before SET_ACTIVE; the old slot stays active.
