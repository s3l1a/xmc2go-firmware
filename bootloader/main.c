/*
 * main.c - XMC 2Go custom bootloader.
 *
 * Boot sequence (docs/DESIGN.md):
 *  1. init clock/UART/LEDs, read metadata log
 *  2. validate active + other slot images (header + payload CRC)
 *  3. meta_boot_decision(): boot / boot-trial / rollback / recovery
 *  4. recovery window (1 s): if a host talks, enter update mode
 *  5. arm the watchdog and jump to the app (SP + reset from the app vector
 *     table at slot+0x20; CLK_VAL1/CLK_VAL2 applied like the SSW does)
 *
 * The bootloader never writes its own flash region: board/flash.c rejects any
 * range outside the two slots and metadata sectors.
 */
#include "xmc1100_regs.h"
#include "system.h"
#include "uart.h"
#include "delay.h"
#include "led.h"
#include "wdt.h"
#include "flash.h"
#include "meta.h"
#include "image.h"
#include "metadata.h"
#include "protocol.h"
#include "config.h"
#include "proto.h"

static uint32_t slot_start_of(uint8_t slot)
{
    return (slot == 0u) ? CFG_SLOT_A_START : CFG_SLOT_B_START;
}

static int slot_image_valid(uint8_t slot)
{
    uint32_t start = slot_start_of(slot);
    const image_header_t *h = (const image_header_t *)(uintptr_t)start;
    if (image_header_check(h, start, CFG_SLOT_SIZE, slot) != IMG_OK) {
        return 0;
    }
    if (image_vector_check(h, start) != IMG_OK) {
        return 0;
    }
    return image_payload_check(h, start) == IMG_OK ? 1 : 0;
}

static void jump_to_app(uint32_t slot_start)
{
    const volatile uint32_t *vt =
        (const volatile uint32_t *)(uintptr_t)(slot_start + IMAGE_VTABLE_OFFSET);
    uint32_t sp = vt[0];
    uint32_t reset = vt[1];

    /* apply the app's CLK_VAL1/CLK_VAL2 like the SSW would (RM 18.1.3.1) */
    if ((vt[4] & 0x80000000u) == 0u) {
        SCU_CLOCK->CLKCR = (SCU_CLOCK->CLKCR & ~0xFFFFFu) | (vt[4] & 0xFFFFFu);
    }
    if ((vt[5] & 0x80000000u) == 0u) {
        SCU_CLOCK->CGATCLR0 = vt[5] & 0x7FFu;
    }

    uart_puts("\nboot: jump to app\n");
    uart_flush_tx();

    __asm volatile("cpsid i");
    __asm volatile("msr msp, %0" :: "r"(sp));
    ((void (*)(void))reset)();
    for (;;) {
    }
}

static void meta_defaults(meta_record_t *rec)
{
    rec->magic = META_MAGIC;
    rec->seq = 0u;
    rec->active_slot = 0u;
    rec->flags_a = 0u;
    rec->flags_b = 0u;
    rec->attempts = 0u;
    rec->boot_count = 0u;
}

static int meta_commit(meta_record_t *rec)
{
    rec->seq += 1u;
    rec->boot_count = (uint16_t)(rec->boot_count + 1u);
    if (meta_log_append(rec) != 0) {
        uart_puts("meta write FAILED\n");
        return -1;
    }
    return 0;
}

static void run_rollback(proto_ctx_t *ctx, meta_record_t *rec)
{
    meta_record_t n = *rec;
    uint8_t target = (uint8_t)(1u - rec->active_slot);
    uint8_t flags;

    if (!slot_image_valid(target)) {
        uart_puts("rollback: other slot invalid, staying\n");
        ctx->do_rollback = 0;
        return;
    }
    /* mark the abandoned slot bad so it is never auto-booted again */
    flags = (uint8_t)(meta_flags_of(&n, rec->active_slot) | META_FLAG_BAD);
    meta_set_flags(&n, rec->active_slot, flags);
    /* the target boots as a healthy image */
    flags = (uint8_t)((meta_flags_of(&n, target) | META_FLAG_VALID) &
                      ~(uint8_t)META_FLAG_TRIAL);
    meta_set_flags(&n, target, flags);
    n.active_slot = target;
    n.attempts = 0u;
    if (meta_commit(&n) != 0) {
        ctx->do_rollback = 0;
        return;
    }
    uart_puts("rollback: switching slot\n");
    wdt_init(CFG_WDT_TIMEOUT_MS);
    jump_to_app(slot_start_of(target));
}

int main(void)
{
    meta_record_t rec;
    meta_decision_t d;
    proto_ctx_t ctx;
    int active_valid;
    int other_valid;
    int i;

    sys_tick_init();
    uart_init();
    led_init();
    led_set(1, 1);

    uart_puts("\n== XMC2Go bootloader ==\n");

    if (!meta_log_read(&rec)) {
        meta_defaults(&rec);
    }

    active_valid = slot_image_valid(rec.active_slot);
    other_valid = slot_image_valid((uint8_t)(1u - rec.active_slot));
    d = meta_boot_decision(&rec, active_valid, other_valid,
                           (uint8_t)CFG_WDT_TRIAL_ATTEMPTS);

    /* persist the consequences of the decision */
    if (d.action == META_ACTION_BOOT_TRIAL) {
        rec.attempts = d.attempts;
        if (meta_commit(&rec) != 0) {
            d.action = META_ACTION_RECOVERY;
        }
    } else if (d.action == META_ACTION_ROLLBACK) {
        uint8_t flags = (uint8_t)(meta_flags_of(&rec, rec.active_slot) |
                                  META_FLAG_BAD);
        meta_set_flags(&rec, rec.active_slot, flags);
        flags = (uint8_t)((meta_flags_of(&rec, d.target_slot) | META_FLAG_VALID) &
                          ~(uint8_t)META_FLAG_TRIAL);
        meta_set_flags(&rec, d.target_slot, flags);
        rec.active_slot = d.target_slot;
        rec.attempts = 0u;
        if (meta_commit(&rec) != 0) {
            d.action = META_ACTION_RECOVERY;
            if (!meta_log_read(&rec)) {
                meta_defaults(&rec);
            }
        }
    }

    proto_init(&ctx);
    ctx.active_slot = rec.active_slot;

    if (d.action == META_ACTION_RECOVERY) {
        uart_puts("no valid image: recovery mode\n");
        led_pattern(1, 1);
        while (!ctx.do_boot && !ctx.do_rollback) {
            proto_poll(&ctx, 60000u);       /* stay until host acts */
        }
    } else {
        /* short window for the host to take control */
        for (i = 0; i < 20; i++) {          /* blink while waiting */
            led_pattern((uint8_t)((i & 1) ^ 1), 0);
            proto_poll(&ctx, 50u);
            if (ctx.host_seen) {
                break;
            }
        }
    }

    if (ctx.host_seen && !ctx.do_boot) {
        uart_puts("update mode (5 s idle = exit)\n");
        led_pattern(1, 1);
        proto_poll(&ctx, 5000u);            /* stall timeout -> keep old slot */
    }

    if (ctx.do_rollback) {
        run_rollback(&ctx, &rec);
    }

    /* the update session may have changed the metadata (SET_ACTIVE_SLOT):
     * re-read before the final boot decision so we boot the *new* slot */
    if (meta_log_read(&rec)) {
        /* refreshed */
    }

    /* Never leave recovery until the selected slot is actually valid. */
    while (!slot_image_valid(rec.active_slot)) {
        uart_puts("active image invalid: recovery mode\n");
        ctx.do_boot = 0;
        proto_poll(&ctx, 60000u);
        if (ctx.do_rollback) {
            run_rollback(&ctx, &rec);
        }
        if (!meta_log_read(&rec)) {
            meta_defaults(&rec);
        }
    }

    /* SET_ACTIVE_SLOT followed by CMD_BOOT is the first trial attempt. */
    while ((meta_flags_of(&rec, rec.active_slot) & META_FLAG_TRIAL) != 0u &&
           rec.attempts == 0u) {
        rec.attempts = 1u;
        if (meta_commit(&rec) == 0) {
            break;
        }
        uart_puts("trial state not durable: recovery mode\n");
        ctx.do_boot = 0;
        proto_poll(&ctx, 60000u);
        if (ctx.do_rollback) {
            run_rollback(&ctx, &rec);
        }
        if (!meta_log_read(&rec)) {
            meta_defaults(&rec);
        }
    }

    uart_puts("arming watchdog\n");
    wdt_init(CFG_WDT_TIMEOUT_MS);
    jump_to_app(slot_start_of(rec.active_slot));
    return 0;
}
