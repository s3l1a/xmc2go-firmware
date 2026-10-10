# PROTOCOL - host <-> bootloader link

Implemented twice, byte-identical:
* C: `common/protocol.h`, `bootloader/proto.c`
* Python: `host/updater/xmcup/framing.py`, `protocol.py`

## 1. Framing

```
+------+-----+-----+-----------+--------------+------------+
| SOF  | CMD | SEQ | LEN (2 LE)| PAYLOAD(LEN) | CRC16 (2LE)|
+------+-----+-----+-----------+--------------+------------+
 0xA5   1B    1B    2B           0..128 B       2B
```

* `LEN` is the payload length (0..128). Frames with LEN > 128 are discarded.
* `CRC16` = CRC-16/CCITT-FALSE (poly `0x1021`, init `0xFFFF`, no reflection,
  xorout `0`) over `CMD .. end of PAYLOAD` (SOF and CRC excluded).
* Responses use the same frame format; `CMD` echoes the request, `SEQ` echoes
  the request SEQ, and `PAYLOAD[0]` is a status byte (`0x00` = OK).
* **Resync**: on bad SOF, oversized LEN or bad CRC the receiver discards up to
  and including the offending byte and scans for the next `0xA5`. No byte
  stuffing is used (the length field makes it unnecessary).
* SEQ is a free-running 8-bit counter (host increments per request, wraps at
  255). The receiver answers every valid request exactly once.

## 2. Status codes (PAYLOAD[0] of every response)

| Code | Name | Meaning |
|---|---|---|
| 0x00 | OK | success |
| 0x01 | BAD_CMD | unknown command |
| 0x02 | BAD_PARAM | wrong payload size/alignment/offset |
| 0x03 | BUSY | (reserved) |
| 0x04 | FLASH | erase/program failure |
| 0x05 | VERIFY | image header/payload CRC mismatch |
| 0x06 | PROTECTED | target is the active slot or outside a slot |
| 0x07 | STATE | e.g. SET_ACTIVE without successful VERIFY |
| 0x08 | TIMEOUT | (reserved for host-side use) |
| 0x09 | INTERNAL | unexpected firmware error |

## 3. Commands

### 0x01 PING
Request payload: empty.
Response payload: `[status][proto_ver][bl_maj][bl_min][bl_patch]`

### 0x02 INFO
Request payload: empty.
Response payload (`INFO_RESP_LEN` = 27 bytes):

| Index | Field |
|---|---|
| 0 | status |
| 1 | proto_version |
| 2..4 | bootloader version maj/min/patch |
| 5 | active slot (0 = A, 1 = B) |
| 6 | slot A state (0 invalid, 1 valid, 2 trial, 3 bad) |
| 7 | slot B state |
| 8 | trial boot-attempt counter |
| 9 | reset cause (SCU_RESET.RSTSTAT low byte; bit5 = watchdog) |
| 10 | flags (reserved, 0) |
| 11..13 | slot A version maj/min/patch, 14 reserved |
| 15..18 | slot A build number (u32 LE) |
| 19..21 | slot B version maj/min/patch, 22 reserved |
| 23..26 | slot B build number (u32 LE) |

### 0x10 ERASE_SLOT
Request payload: `[slot]` (0 = A, 1 = B).
Erases every 256 B page of the slot. Refused with `PROTECTED` when `slot` is
the active slot (the running image is never destroyed).

### 0x11 WRITE_CHUNK
Request payload: `[slot][offset u32 LE][data]`.
* `offset` must be 16-byte aligned; `len(data)` a nonzero multiple of 16 and
  <= 112 (`WRITE_CHUNK_MAX_DATA`).
* `offset + len(data)` must fit inside the slot; otherwise `PROTECTED`.
* Refused with `PROTECTED` for the active slot.
* Each 16-byte group is programmed as one flash block (with hardware verify).
* Any write invalidates the session's "verified" flag for the slot (must
  VERIFY again before SET_ACTIVE).

### 0x12 VERIFY_SLOT
Request payload: `[slot]`.
Validates the slot's image header (magic, format version, header CRC, slot id,
length), initial stack pointer, reset vector/entry point, and payload CRC-32.
Sets the session verify flag on success; `VERIFY` status on failure.

### 0x13 SET_ACTIVE_SLOT
Request payload: `[slot]`.
Rules: `slot` must have been verified successfully in this session (else
STATE), must not be the active slot (else PROTECTED). On success writes the
metadata record: `active = slot`, `flags[slot] |= VALID|TRIAL`,
`attempts = 0`, sequence + 1.

### 0x14 BOOT
Request payload: empty. Response `OK`, then the bootloader arms the watchdog
and jumps to the active slot (trial logic applies on the next reset).

### 0x15 ROLLBACK
Request payload: empty. The bootloader marks the current active slot BAD,
switches to the other slot (must have a valid image, else the command is
acknowledged but no switch happens), writes metadata, reboots into it.

## 4. Update flow

```
PING -> INFO -> (choose inactive slot)
ERASE_SLOT(slot)
WRITE_CHUNK(slot, 0, ..) x N          # whole image, 0xFF padded to 16 B
VERIFY_SLOT(slot)                     # required before switching
SET_ACTIVE_SLOT(slot)                 # marks the slot trial
BOOT
```

Any failure or cancellation before SET_ACTIVE leaves the old slot active and
untouched. A transfer stall (> 5 s without host traffic) exits the update
session and boots the old slot.

## 5. Test vectors (hex)

Vector 1 - PING request (SEQ=1, empty payload):
```
A5 01 01 00 00 44 C5
```
`CRC16(01 01 00 00) = 0xC544` (LE bytes `44 C5`). Verified in both
implementations (`tests/host_unit/test_framing.py`,
`tests/host_unit/c_vectors.c`).

Vector 2 - CRC check values used by both implementations:
```
CRC16-CCITT-FALSE("123456789") = 0x29B1
CRC16-CCITT-FALSE("")          = 0xFFFF
CRC16-CCITT-FALSE(00)          = 0xE1F0
CRC16-CCITT-FALSE(01)          = 0xF1D1
CRC16-CCITT-FALSE(41 'A')      = 0xB915
CRC32-IEEE("123456789")        = 0xCBF43926
CRC32-IEEE("")                 = 0x00000000
CRC32-IEEE(00)                 = 0xD202EF8D
CRC32-IEEE("a")                = 0xE8B7BE43
```

Vector 3 - INFO response (status OK, proto 1, BL 1.0.0, active B, A valid
v1.2.3 build 7, B trial v2.0.0 build 9, attempts 1, reset cause 0x01):
```
A5 02 05 1B 00 00 01 01 00 00 01 01 02 02 01 00
07 00 00 00 01 02 03 00 07 00 00 00 02 00 00 00
09 00 00 00 HH HH
```
(27 payload bytes; `HH HH` = CRC16 over `02 05 1B 00` + 27 payload bytes;
computed at test time rather than transcribed here.)

Vector 4 - WRITE_CHUNK request (slot 1, offset 0x20, 16 bytes 00..0F):
```
A5 11 03 15 00 01 20 00 00 00 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F HH HH
```
LEN = 0x0015 = 21 = 1 (slot) + 4 (offset) + 16 (data).

## 6. Timeout behaviour

| Where | Timeout | Effect |
|---|---|---|
| host request retry | 2 s (8 s for flash ops) | retry, then error |
| bootloader update session | 5 s without host bytes | exit session, boot old slot |
| bootloader recovery window | 1-2 s after reset | decide boot vs. update mode |
| watchdog (app running) | 5 s | MCU reset, trial/rollback logic |
