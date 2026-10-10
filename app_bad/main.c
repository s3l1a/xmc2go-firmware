/*
 * app_bad - deliberately never reports healthy and never services the
 * watchdog. Used to verify watchdog rollback: the bootloader arms the WDT,
 * this app runs, the WDT resets the board, and after CFG_WDT_TRIAL_ATTEMPTS
 * failed trials the bootloader rolls back to the other slot.
 */
#include "xmc1100_regs.h"
#include "system.h"
#include "uart.h"
#include "delay.h"
#include "led.h"
#include "timer.h"
#include "wdt.h"

int main(void)
{
    uint32_t t;

    sys_tick_init();
    uart_init();
    led_init();
    timer_init_1ms();

    uart_puts("app_bad: running, will NEVER report healthy\n");

    /* blink both LEDs forever; no app_mark_healthy(), no watchdog service */
    for (;;) {
        t = timer_millis();
        led_pattern((uint8_t)((t / 250u) & 1u), (uint8_t)((t / 250u) & 1u));
    }
    return 0;
}
