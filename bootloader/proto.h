#ifndef BL_PROTO_H
#define BL_PROTO_H

#include <stdint.h>

/* Bootloader link protocol (docs/PROTOCOL.md). Serves one request per call
 * sequence; returns after `idle_ms` without receiving a byte. */

typedef struct {
    uint8_t active_slot;
    uint8_t slot_verified[2];  /* VERIFY_SLOT succeeded this session */
    uint32_t last_rx_ms;       /* sys_tick time of last received byte */
    int host_seen;             /* any valid frame received */
    int do_boot;               /* CMD_BOOT received: exit loop and boot */
    int do_rollback;           /* CMD_ROLLBACK received */
} proto_ctx_t;

void proto_init(proto_ctx_t *ctx);
/* Poll for host traffic; returns when idle for idle_ms (or do_boot set). */
void proto_poll(proto_ctx_t *ctx, uint32_t idle_ms);

#endif
