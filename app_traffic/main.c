/*
 * app_traffic - traffic light demo application (slot A/B image).
 *
 * - Traffic light FSM (app_traffic/traffic_fsm.c, pure C, host-testable).
 * - Timing via CCU40 1 ms interrupt (no busy waits).
 * - Serial console inputs: 'P' pedestrian button, 'R' reset cycle, 'S' status.
 * - Every state transition is logged with a millisecond timestamp.
 * - Watchdog contract: self-check ~2 s -> app_mark_healthy(), then
 *   app_service_watchdog() in the main loop forever.
 *
 * LED mapping (only 2 LEDs on the XMC 2Go, see common/config.h):
 *   LED1 = GREEN aspect, LED2 = RED aspect, YELLOW = both on,
 *   PEDESTRIAN_REQUEST: LED2 on + LED1 blinking (walk), FAULT: both blink.
 */
#include <stdio.h>
#include "xmc1100_regs.h"
#include "system.h"
#include "uart.h"
#include "delay.h"
#include "led.h"
#include "timer.h"
#include "wdt.h"
#include "app_api.h"
#include "config.h"
#include "traffic_fsm.h"

static traffic_fsm_t g_fsm;

static void log_line(const char *msg)
{
    char buf[64];
    unsigned i = 0;
    uint32_t ms = app_millis();
    /* simple "%u: " prefix without printf float weight */
    char num[12];
    unsigned n = 0;
    uint32_t v = ms;
    do {
        num[n++] = (char)('0' + (v % 10u));
        v /= 10u;
    } while (v && n < sizeof(num));
    while (n > 0 && i < sizeof(buf) - 2u) {
        buf[i++] = num[--n];
    }
    buf[i++] = ':';
    buf[i++] = ' ';
    while (*msg && i < sizeof(buf) - 1u) {
        buf[i++] = *msg++;
    }
    buf[i] = '\0';
    uart_puts(buf);
    uart_putc('\n');
}

static void log_transition(traffic_state_t from, traffic_state_t to,
                           traffic_transition_t why)
{
    char msg[80];
    unsigned i = 0;
    const char *a = traffic_state_name(from);
    const char *b = traffic_state_name(to);
    while (*a && i < sizeof(msg) - 2u) {
        msg[i++] = *a++;
    }
    msg[i++] = '-';
    msg[i++] = '>';
    msg[i++] = ' ';
    while (*b && i < sizeof(msg) - 1u) {
        msg[i++] = *b++;
    }
    msg[i] = '\0';
    (void)why;
    log_line(msg);
}

static void print_status(void)
{
    traffic_status_t st;
    traffic_fsm_get_status(&g_fsm, &st);
    log_line(traffic_state_name(st.state));
    {
        char msg[40];
        unsigned i = 0;
        const char *p = "t_rem=";
        uint32_t v = st.time_remaining_ms / 1000u;
        while (*p && i < sizeof(msg) - 2u) {
            msg[i++] = *p++;
        }
        msg[i++] = (char)('0' + (v % 10u));
        msg[i++] = 's';
        if (st.ped_pending) {
            msg[i++] = ' ';
            msg[i++] = 'P';
        }
        msg[i] = '\0';
        log_line(msg);
    }
}

int main(void)
{
    uint32_t last_ms;
    uint32_t healthy_ms;
    int healthy_logged = 0;

    sys_tick_init();
    uart_init();
    led_init();
    timer_init_1ms();
    if ((WDT->CTR & WDT_CTR_ENB) == 0u) {
        wdt_init(CFG_WDT_TIMEOUT_MS);   /* standalone (no bootloader) case */
    }

    traffic_fsm_init(&g_fsm);
    log_line("app_traffic start");

    last_ms = timer_millis();
    healthy_ms = last_ms;

    for (;;) {
        traffic_state_t before;
        traffic_transition_t t;
        int c;

        /* run the FSM clock: one TICK per elapsed millisecond */
        while (timer_millis() != last_ms) {
            before = g_fsm.state;
            t = traffic_fsm_step(&g_fsm, TRAFFIC_EVT_TICK);
            last_ms++;
            if (g_fsm.state != before) {
                log_transition(before, g_fsm.state, t);
            }
            led_pattern(g_fsm.led1, g_fsm.led2);
        }

        /* serial input */
        c = uart_getc_nonblock();
        if (c >= 0) {
            before = g_fsm.state;
            switch (c) {
            case 'P': case 'p':
                t = traffic_fsm_step(&g_fsm, TRAFFIC_EVT_PED_BUTTON);
                log_line("pedestrian button");
                break;
            case 'R': case 'r':
                t = traffic_fsm_step(&g_fsm, TRAFFIC_EVT_RESET_CYCLE);
                log_line("cycle reset");
                break;
            case 'S': case 's':
                t = traffic_fsm_step(&g_fsm, TRAFFIC_EVT_STATUS_REQ);
                print_status();
                break;
            case 'X': case 'x':
                /* reset into the bootloader window (HIL/dev convenience) */
                log_line("reset to bootloader");
                uart_flush_tx();
                SystemReset();
                break;
            default:
                t = traffic_fsm_step(&g_fsm, TRAFFIC_EVT_INVALID);
                log_line("invalid input");
                break;
            }
            if (g_fsm.state != before) {
                log_transition(before, g_fsm.state, t);
            }
            led_pattern(g_fsm.led1, g_fsm.led2);
        }

        /* watchdog contract: healthy after 2 s self-check */
        if (!healthy_logged && (timer_millis() - healthy_ms) >= 2000u) {
            if (app_mark_healthy() == 0) {
                log_line("healthy: trial cleared");
            } else {
                log_line("healthy: meta write failed");
            }
            healthy_logged = 1;
        }

        app_service_watchdog();
    }
    return 0;
}
