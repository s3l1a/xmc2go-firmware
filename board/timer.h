#ifndef XMC_TIMER_H
#define XMC_TIMER_H

#include <stdint.h>

/* CCU40 slice 0: 1 ms periodic interrupt (CCU40_0_IRQn). Used by apps for
 * FSM timing - no busy-wait loops. */
void timer_init_1ms(void);
uint32_t timer_millis(void);   /* ms since timer_init_1ms() */

#endif
