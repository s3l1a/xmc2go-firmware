/*
 * delay.c - SysTick polling time base (1 ms at CFG_MCLK_HZ = 32 MHz).
 * The core SysTick timer is polled (COUNTFLAG), so no veneer/interrupt is
 * required. Used for the bootloader's recovery window and UART timeouts.
 */
#include "xmc1100_regs.h"
#include "delay.h"
#include "config.h"

#define SYST_CSR ((volatile uint32_t *)0xE000E010u)
#define SYST_RVR ((volatile uint32_t *)0xE000E014u)
#define SYST_CVR ((volatile uint32_t *)0xE000E018u)

static uint32_t s_ms;

void sys_tick_init(void)
{
    *SYST_RVR = (CFG_MCLK_HZ / 1000u) - 1u;
    *SYST_CVR = 0u;
    *SYST_CSR = 0x5u; /* ENABLE | CLKSOURCE = core clock */
    s_ms = 0u;
}

uint32_t sys_tick_now_ms(void)
{
    if ((*SYST_CSR & 0x10000u) != 0u) { /* COUNTFLAG */
        s_ms++;
    }
    return s_ms;
}

void delay_ms(uint32_t ms)
{
    uint32_t start = sys_tick_now_ms();
    while ((sys_tick_now_ms() - start) < ms) {
    }
}
