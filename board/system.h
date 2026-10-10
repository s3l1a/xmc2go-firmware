#ifndef XMC_SYSTEM_H
#define XMC_SYSTEM_H

#include <stdint.h>

/* Captured SCU_RESET.RSTSTAT at startup, cleared afterwards (RM 18.1.2). */
extern uint32_t g_reset_cause;

void SystemInit(void);
void SystemReset(void);           /* software reset via AIRCR */

#endif
