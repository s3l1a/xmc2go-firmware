#ifndef XMC_DELAY_H
#define XMC_DELAY_H

#include <stdint.h>

/* SysTick polling time base (1 ms at CFG_MCLK_HZ). No interrupts used. */
void sys_tick_init(void);
uint32_t sys_tick_now_ms(void);
void delay_ms(uint32_t ms);

#endif
