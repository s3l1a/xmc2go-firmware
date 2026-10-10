/*
 * app_crash - faults before reporting healthy (writes to an invalid address,
 * which raises a HardFault; the weak HardFault handler loops without
 * servicing the watchdog). Used to verify rollback on crash/hang.
 */
#include "xmc1100_regs.h"
#include "system.h"
#include "uart.h"
#include "delay.h"
#include "led.h"
#include "timer.h"

int main(void)
{
    volatile uint32_t *bad;

    sys_tick_init();
    uart_init();
    led_init();
    timer_init_1ms();

    uart_puts("app_crash: about to fault before healthy\n");
    uart_flush_tx();
    delay_ms(50);

    /* invalid write -> HardFault -> hang -> watchdog reset -> rollback */
    bad = (volatile uint32_t *)0x00000000u;
    *bad = 0xDEADBEEFu;

    /* not reached */
    for (;;) {
    }
    return 0;
}
