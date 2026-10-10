/*
 * proto.c - bootloader link protocol implementation (mirrors
 * host/updater/xmcup/framing.py and protocol.py byte for byte).
 */
#include "proto.h"
#include "protocol.h"
#include "crc16.h"
#include "image.h"
#include "metadata.h"
#include "meta.h"
#include "flash.h"
#include "uart.h"
#include "delay.h"
#include "system.h"
#include "config.h"

enum {
    P_SOF = 0,
    P_HDR,
    P_HDR_LEN_HI,
    P_PAYLOAD,
    P_CRC
};

typedef struct {
    uint8_t state;
    uint8_t cmd;
    uint8_t seq;
    uint16_t len;
    uint16_t pos;
    uint8_t payload[PROTO_MAX_PAYLOAD];
    uint8_t hdr[3];
} parser_t;

static parser_t s_parser;
static proto_ctx_t *s_ctx;

void proto_init(proto_ctx_t *ctx)
{
    s_parser.state = P_SOF;
    s_ctx = ctx;
    ctx->host_seen = 0;
    ctx->do_boot = 0;
    ctx->do_rollback = 0;
    ctx->last_rx_ms = sys_tick_now_ms();
}

static void proto_send(uint8_t cmd, uint8_t seq, const uint8_t *payload,
                       uint16_t len)
{
    uint8_t frame[PROTO_MAX_FRAME];
    uint16_t i;
    uint16_t crc;
    uint16_t body_len = (uint16_t)(4u + len); /* CMD SEQ LEN(2) PAYLOAD */

    frame[0] = PROTO_SOF;
    frame[1] = cmd;
    frame[2] = seq;
    frame[3] = (uint8_t)(len & 0xFFu);
    frame[4] = (uint8_t)(len >> 8);
    for (i = 0; i < len; i++) {
        frame[5u + i] = payload[i];
    }
    crc = crc16_ccitt(&frame[1], body_len);
    frame[5u + len] = (uint8_t)(crc & 0xFFu);
    frame[6u + len] = (uint8_t)(crc >> 8);
    uart_write(frame, (size_t)(7u + len));
}

static void proto_reply(uint8_t cmd, uint8_t seq, uint8_t status,
                        const uint8_t *extra, uint16_t extra_len)
{
    uint8_t payload[PROTO_MAX_PAYLOAD];
    uint16_t i;
    payload[0] = status;
    for (i = 0; i < extra_len; i++) {
        payload[1u + i] = extra[i];
    }
    proto_send(cmd, seq, payload, (uint16_t)(1u + extra_len));
}

/* ---- helpers ---- */

static int slot_valid_id(uint8_t slot)
{
    return (slot == 0u || slot == 1u) ? 1 : 0;
}

static uint32_t slot_start_of(uint8_t slot)
{
    return (slot == 0u) ? CFG_SLOT_A_START : CFG_SLOT_B_START;
}

static const image_header_t *slot_header(uint8_t slot)
{
    return (const image_header_t *)(uintptr_t)slot_start_of(slot);
}

static int slot_image_valid(uint8_t slot)
{
    const image_header_t *h = slot_header(slot);
    if (image_header_check(h, slot_start_of(slot), CFG_SLOT_SIZE, slot) != IMG_OK) {
        return 0;
    }
    if (image_vector_check(h, slot_start_of(slot)) != IMG_OK) {
        return 0;
    }
    return image_payload_check(h, slot_start_of(slot)) == IMG_OK ? 1 : 0;
}

static uint8_t slot_state_of(uint8_t slot, uint8_t flags)
{
    if ((flags & META_FLAG_BAD) != 0u) {
        return SLOT_STATE_BAD;
    }
    if ((flags & META_FLAG_TRIAL) != 0u) {
        return SLOT_STATE_TRIAL;
    }
    if ((flags & META_FLAG_VALID) != 0u && slot_image_valid(slot)) {
        return SLOT_STATE_VALID;
    }
    return SLOT_STATE_INVALID;
}

/* ---- commands ---- */

static void cmd_ping(uint8_t seq)
{
    uint8_t extra[4];
    extra[0] = CFG_PROTO_VERSION;
    extra[1] = CFG_BL_VERSION_MAJOR;
    extra[2] = CFG_BL_VERSION_MINOR;
    extra[3] = CFG_BL_VERSION_PATCH;
    proto_reply(CMD_PING, seq, ST_OK, extra, 4);
}

static void cmd_info(uint8_t seq)
{
    uint8_t e[INFO_RESP_LEN - 1u];
    meta_record_t rec;
    const image_header_t *ha = slot_header(0);
    const image_header_t *hb = slot_header(1);
    unsigned i;

    for (i = 0; i < sizeof(e); i++) {
        e[i] = 0u;
    }
    if (!meta_log_read(&rec)) {
        rec.active_slot = 0u;
        rec.flags_a = 0u;
        rec.flags_b = 0u;
        rec.attempts = 0u;
    }

    e[0] = CFG_PROTO_VERSION;
    e[1] = CFG_BL_VERSION_MAJOR;
    e[2] = CFG_BL_VERSION_MINOR;
    e[3] = CFG_BL_VERSION_PATCH;
    e[4] = rec.active_slot;
    e[5] = slot_state_of(0u, rec.flags_a);
    e[6] = slot_state_of(1u, rec.flags_b);
    e[7] = rec.attempts;
    e[8] = (uint8_t)(g_reset_cause & 0xFFu);
    e[9] = 0u; /* flags */

    if (slot_image_valid(0)) {
        e[10] = ha->ver_major; e[11] = ha->ver_minor; e[12] = ha->ver_patch;
        e[14] = (uint8_t)(ha->build_number & 0xFFu);
        e[15] = (uint8_t)((ha->build_number >> 8) & 0xFFu);
        e[16] = (uint8_t)((ha->build_number >> 16) & 0xFFu);
        e[17] = (uint8_t)((ha->build_number >> 24) & 0xFFu);
    }
    if (slot_image_valid(1)) {
        e[18] = hb->ver_major; e[19] = hb->ver_minor; e[20] = hb->ver_patch;
        e[22] = (uint8_t)(hb->build_number & 0xFFu);
        e[23] = (uint8_t)((hb->build_number >> 8) & 0xFFu);
        e[24] = (uint8_t)((hb->build_number >> 16) & 0xFFu);
        e[25] = (uint8_t)((hb->build_number >> 24) & 0xFFu);
    }
    proto_reply(CMD_INFO, seq, ST_OK, e, (uint16_t)(INFO_RESP_LEN - 1u));
}

static void cmd_erase_slot(uint8_t seq, const uint8_t *p, uint16_t len)
{
    uint8_t slot;
    if (len != 1u || !slot_valid_id(p[0])) {
        proto_reply(CMD_ERASE_SLOT, seq, ST_ERR_BAD_PARAM, 0, 0);
        return;
    }
    slot = p[0];
    if (slot == s_ctx->active_slot) {
        proto_reply(CMD_ERASE_SLOT, seq, ST_ERR_PROTECTED, 0, 0);
        return;
    }
    if (flash_erase_slot(slot_start_of(slot), CFG_SLOT_SIZE) != FLASH_OK) {
        proto_reply(CMD_ERASE_SLOT, seq, ST_ERR_FLASH, 0, 0);
        return;
    }
    s_ctx->slot_verified[slot] = 0u;
    proto_reply(CMD_ERASE_SLOT, seq, ST_OK, 0, 0);
}

static void cmd_write_chunk(uint8_t seq, const uint8_t *p, uint16_t len)
{
    uint8_t slot;
    uint32_t offset;
    uint16_t dlen;
    uint16_t off;

    if (len < 5u + 16u) {
        proto_reply(CMD_WRITE_CHUNK, seq, ST_ERR_BAD_PARAM, 0, 0);
        return;
    }
    slot = p[0];
    offset = (uint32_t)p[1] | ((uint32_t)p[2] << 8) | ((uint32_t)p[3] << 16) |
             ((uint32_t)p[4] << 24);
    dlen = (uint16_t)(len - 5u);

    if (!slot_valid_id(slot) || slot == s_ctx->active_slot) {
        proto_reply(CMD_WRITE_CHUNK, seq,
                    slot_valid_id(slot) ? ST_ERR_PROTECTED : ST_ERR_BAD_PARAM,
                    0, 0);
        return;
    }
    if ((offset % CFG_FLASH_BLOCK_SIZE) != 0u ||
        (dlen % CFG_FLASH_BLOCK_SIZE) != 0u || dlen == 0u ||
        dlen > WRITE_CHUNK_MAX_DATA) {
        proto_reply(CMD_WRITE_CHUNK, seq, ST_ERR_BAD_PARAM, 0, 0);
        return;
    }
    if (offset >= CFG_SLOT_SIZE || dlen > CFG_SLOT_SIZE - offset) {
        proto_reply(CMD_WRITE_CHUNK, seq, ST_ERR_PROTECTED, 0, 0);
        return;
    }
    if (flash_range_is_writable(slot_start_of(slot) + offset, dlen) != FLASH_OK) {
        proto_reply(CMD_WRITE_CHUNK, seq, ST_ERR_PROTECTED, 0, 0);
        return;
    }
    for (off = 0; off < dlen; off = (uint16_t)(off + CFG_FLASH_BLOCK_SIZE)) {
        if (flash_write_block_verify(slot_start_of(slot) + offset + off,
                                     &p[5u + off]) != FLASH_OK) {
            proto_reply(CMD_WRITE_CHUNK, seq, ST_ERR_FLASH, 0, 0);
            return;
        }
    }
    s_ctx->slot_verified[slot] = 0u; /* image changed: must re-verify */
    proto_reply(CMD_WRITE_CHUNK, seq, ST_OK, 0, 0);
}

static void cmd_verify_slot(uint8_t seq, const uint8_t *p, uint16_t len)
{
    uint8_t slot;
    if (len != 1u || !slot_valid_id(p[0])) {
        proto_reply(CMD_VERIFY_SLOT, seq, ST_ERR_BAD_PARAM, 0, 0);
        return;
    }
    slot = p[0];
    if (!slot_image_valid(slot)) {
        proto_reply(CMD_VERIFY_SLOT, seq, ST_ERR_VERIFY, 0, 0);
        return;
    }
    s_ctx->slot_verified[slot] = 1u;
    proto_reply(CMD_VERIFY_SLOT, seq, ST_OK, 0, 0);
}

static void cmd_set_active(uint8_t seq, const uint8_t *p, uint16_t len)
{
    meta_record_t rec;
    uint8_t slot;
    uint8_t flags;

    if (len != 1u || !slot_valid_id(p[0])) {
        proto_reply(CMD_SET_ACTIVE_SLOT, seq, ST_ERR_BAD_PARAM, 0, 0);
        return;
    }
    slot = p[0];
    if (slot == s_ctx->active_slot) {
        proto_reply(CMD_SET_ACTIVE_SLOT, seq, ST_ERR_PROTECTED, 0, 0);
        return;
    }
    if (!s_ctx->slot_verified[slot]) {
        /* rule: slot-switch only after successful verification */
        proto_reply(CMD_SET_ACTIVE_SLOT, seq, ST_ERR_STATE, 0, 0);
        return;
    }

    if (!meta_log_read(&rec)) {
        rec.magic = META_MAGIC;
        rec.seq = 0u;
        rec.active_slot = 0u;
        rec.flags_a = 0u;
        rec.flags_b = 0u;
        rec.attempts = 0u;
        rec.boot_count = 0u;
    }
    rec.seq += 1u;
    rec.active_slot = slot;
    flags = meta_flags_of(&rec, slot);
    flags = (uint8_t)(flags | META_FLAG_VALID | META_FLAG_TRIAL);
    flags = (uint8_t)(flags & ~(uint8_t)META_FLAG_BAD);
    meta_set_flags(&rec, slot, flags);
    rec.attempts = 0u;

    if (meta_log_append(&rec) != 0) {
        proto_reply(CMD_SET_ACTIVE_SLOT, seq, ST_ERR_FLASH, 0, 0);
        return;
    }
    s_ctx->active_slot = slot;
    proto_reply(CMD_SET_ACTIVE_SLOT, seq, ST_OK, 0, 0);
}

static void proto_dispatch(uint8_t cmd, uint8_t seq, const uint8_t *p,
                           uint16_t len)
{
    switch (cmd) {
    case CMD_PING:
        cmd_ping(seq);
        break;
    case CMD_INFO:
        cmd_info(seq);
        break;
    case CMD_ERASE_SLOT:
        cmd_erase_slot(seq, p, len);
        break;
    case CMD_WRITE_CHUNK:
        cmd_write_chunk(seq, p, len);
        break;
    case CMD_VERIFY_SLOT:
        cmd_verify_slot(seq, p, len);
        break;
    case CMD_SET_ACTIVE_SLOT:
        cmd_set_active(seq, p, len);
        break;
    case CMD_BOOT:
        proto_reply(CMD_BOOT, seq, ST_OK, 0, 0);
        s_ctx->do_boot = 1;
        break;
    case CMD_ROLLBACK:
        proto_reply(CMD_ROLLBACK, seq, ST_OK, 0, 0);
        s_ctx->do_rollback = 1;
        break;
    default:
        proto_reply(cmd, seq, ST_ERR_BAD_CMD, 0, 0);
        break;
    }
}

static void proto_rx_byte(uint8_t b)
{
    parser_t *ps = &s_parser;

    switch (ps->state) {
    case P_SOF:
        if (b == PROTO_SOF) {
            ps->state = P_HDR;
            ps->pos = 0u;
        }
        break;

    case P_HDR:
        ps->hdr[ps->pos++] = b;
        if (ps->pos == 3u) {
            ps->cmd = ps->hdr[0];
            ps->seq = ps->hdr[1];
            ps->len = (uint16_t)(ps->hdr[2]);  /* LEN low byte */
            ps->state = P_HDR_LEN_HI;
        }
        break;

    case P_HDR_LEN_HI:
        ps->len = (uint16_t)(ps->len | ((uint16_t)b << 8));
        if (ps->len > PROTO_MAX_PAYLOAD) {
            ps->state = P_SOF;   /* oversized: resync */
        } else if (ps->len == 0u) {
            ps->state = P_CRC;
            ps->pos = 0u;
        } else {
            ps->state = P_PAYLOAD;
            ps->pos = 0u;
        }
        break;

    case P_PAYLOAD:
        ps->payload[ps->pos++] = b;
        if (ps->pos >= ps->len) {
            ps->state = P_CRC;
            ps->pos = 0u;
        }
        break;

    case P_CRC:
        ps->hdr[ps->pos++] = b;   /* reuse hdr[0..1] for CRC bytes */
        if (ps->pos == 2u) {
            uint8_t body[PROTO_MAX_PAYLOAD + 4];
            uint16_t crc_rx = (uint16_t)(ps->hdr[0] | ((uint16_t)ps->hdr[1] << 8));
            uint16_t crc_calc;
            uint16_t i;

            body[0] = ps->cmd;
            body[1] = ps->seq;
            body[2] = (uint8_t)(ps->len & 0xFFu);
            body[3] = (uint8_t)(ps->len >> 8);
            for (i = 0; i < ps->len; i++) {
                body[4u + i] = ps->payload[i];
            }
            crc_calc = crc16_ccitt(body, (size_t)(4u + ps->len));
            ps->state = P_SOF;
            if (crc_calc == crc_rx) {
                s_ctx->host_seen = 1;
                proto_dispatch(ps->cmd, ps->seq, ps->payload, ps->len);
            }
            /* bad CRC: frame dropped, resync at next SOF */
        }
        break;

    default:
        ps->state = P_SOF;
        break;
    }
}

void proto_poll(proto_ctx_t *ctx, uint32_t idle_ms)
{
    uint32_t start = sys_tick_now_ms();

    (void)ctx;
    for (;;) {
        int c = uart_getc_nonblock();
        if (c >= 0) {
            s_ctx->last_rx_ms = sys_tick_now_ms();
            proto_rx_byte((uint8_t)c);
            start = s_ctx->last_rx_ms;
            if (s_ctx->do_boot || s_ctx->do_rollback) {
                return;
            }
        } else {
            if ((sys_tick_now_ms() - start) >= idle_ms) {
                return;
            }
        }
    }
}
