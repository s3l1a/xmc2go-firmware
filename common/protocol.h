/*
 * protocol.h - host <-> bootloader wire format. Byte-identical to the Python
 * implementation in host/updater/xmcup/framing.py (see docs/PROTOCOL.md).
 *
 * Frame:  SOF(0xA5) | CMD | SEQ | LEN(2, LE) | PAYLOAD(LEN) | CRC16(2, LE)
 * CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect, xorout 0) computed
 * over CMD..PAYLOAD inclusive.
 * Response frame: same layout, CMD echoes the request, PAYLOAD[0] = status.
 */
#ifndef XMC_PROTOCOL_H
#define XMC_PROTOCOL_H

#include <stdint.h>

#define PROTO_SOF 0xA5u
#define PROTO_MAX_PAYLOAD 128u
#define PROTO_HEADER_SIZE 5u   /* SOF CMD SEQ LEN(2) */
#define PROTO_CRC_SIZE 2u
#define PROTO_MAX_FRAME (PROTO_HEADER_SIZE + PROTO_MAX_PAYLOAD + PROTO_CRC_SIZE)
/* CRC16 covers CMD..PAYLOAD = 1 + 1 + 2 + LEN bytes */

/* Commands */
#define CMD_PING 0x01u
#define CMD_INFO 0x02u
#define CMD_ERASE_SLOT 0x10u
#define CMD_WRITE_CHUNK 0x11u
#define CMD_VERIFY_SLOT 0x12u
#define CMD_SET_ACTIVE_SLOT 0x13u
#define CMD_BOOT 0x14u
#define CMD_ROLLBACK 0x15u

/* Status codes (first byte of every response payload) */
#define ST_OK 0x00u
#define ST_ERR_BAD_CMD 0x01u
#define ST_ERR_BAD_PARAM 0x02u
#define ST_ERR_BUSY 0x03u
#define ST_ERR_FLASH 0x04u
#define ST_ERR_VERIFY 0x05u
#define ST_ERR_PROTECTED 0x06u   /* target is the active slot or out of bounds */
#define ST_ERR_STATE 0x07u       /* e.g. SET_ACTIVE without successful verify */
#define ST_ERR_TIMEOUT 0x08u
#define ST_ERR_INTERNAL 0x09u

/* Slot states reported by CMD_INFO */
#define SLOT_STATE_INVALID 0u
#define SLOT_STATE_VALID 1u
#define SLOT_STATE_TRIAL 2u
#define SLOT_STATE_BAD 3u

/* PING response payload after status:
 * [1] proto_version [2..4] bl version maj/min/patch */
#define PING_RESP_LEN 5u

/* INFO response payload layout (index after CMD/SEQ/LEN; [0] = status):
 *  [1] proto_version
 *  [2..4] bootloader version maj/min/patch
 *  [5] active_slot            [6] slotA_state   [7] slotB_state
 *  [8] boot_attempts          [9] reset_cause   [10] flags
 *  [11] A ver maj  [12] min   [13] patch        [14] reserved
 *  [15..18] A build (u32 LE)
 *  [19] B ver maj  [20] min   [21] patch        [22] reserved
 *  [23..26] B build (u32 LE)
 * total = 27 bytes */
#define INFO_RESP_LEN 27u

/* WRITE_CHUNK request payload after CMD header: slot(1) | offset(4, LE) | data.
 * data length must be a nonzero multiple of CFG_FLASH_BLOCK_SIZE (16), offset
 * must be 16-byte aligned; <= 112 bytes per chunk (128 - 5 = 123 available). */
#define WRITE_CHUNK_MAX_DATA 112u

#endif /* XMC_PROTOCOL_H */
