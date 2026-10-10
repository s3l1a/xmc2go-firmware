#include "xmc1100_regs.h"
#include "wdt.h"
#include "system.h"
#include "config.h"

void wdt_init(uint32_t timeout_ms)
{
    uint32_t ticks = (timeout_ms * CFG_WDT_HZ) / 1000u;
    SCU_CLOCK->CGATCLR0 = SCU_CLOCK_CGAT_WDT;   /* register interface clock */
    WDT->CTR = 0u;
    WDT->WLB = 0u;                 /* window disabled: service any time */
    WDT->WUB = (ticks == 0u) ? 1u : (ticks - 1u);
    WDT->WDTCLR = WDT_WDTCLR_ALMC;
    /* enable; no pre-warning; stop during debug halt (DSP=0) */
    WDT->CTR = WDT_CTR_ENB;
    wdt_service();
}

void wdt_service(void)
{
    WDT->SRV = WDT_SRV_MAGIC;
}

void wdt_off(void)
{
    WDT->CTR = 0u;
}

int wdt_fired_last_reset(void)
{
    return (g_reset_cause & SCU_RESET_RSTSTAT_WDT) ? 1 : 0;
}
