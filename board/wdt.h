#ifndef XMC_WDT_H
#define XMC_WDT_H

#include <stdint.h>

/* Window watchdog (RM chapter 10): fWDT = 32.768 kHz standby clock.
 * WLB=0 disables the window so the dog can be serviced at any count < WUB.
 * Service = write 0xABADCAFE to SRV; wrong magic = immediate reset. */
void wdt_init(uint32_t timeout_ms);
void wdt_service(void);
void wdt_off(void);   /* only used before jumping to an app is NOT done; kept
                       * for completeness/tests - the design always arms WDT */
int wdt_fired_last_reset(void);  /* RSTSTAT.WDT of the last reset */

#endif
