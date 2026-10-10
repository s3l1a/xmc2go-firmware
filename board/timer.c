/*
 * timer.c - CCU40 slice 0 periodic 1 ms tick.
 *
 * fCNT = fPER / 2^PSC.PSIV = PCLK / 32 = 1 MHz (PCLK = 32 MHz),
 * period PRS = 999 -> 1.000 ms.
 * Period match -> service request SR0 -> CCU40_0_IRQn (IRQ 21).
 */
#include "xmc1100_regs.h"
#include "timer.h"
#include "config.h"

#define TIMER_PSC_VALUE 5u      /* /2^5 = /32 -> 1 MHz */
#define TIMER_PERIOD    999u    /* 1000 counts = 1 ms */

static volatile uint32_t s_ms;

void timer_init_1ms(void)
{
    SCU_CLOCK->CGATCLR0 = SCU_CLOCK_CGAT_CCU40;

    CCU40->GIDLC = CCU4_GIDLC_CS0I | CCU4_GIDLC_SPRB;  /* run slice 0 */
    CCU40_CC40->TC = 0u;
    CCU40_CC40->PSC = TIMER_PSC_VALUE;
    CCU40_CC40->PRS = TIMER_PERIOD;
    CCU40_CC40->SRS = 0u;               /* period match -> SR0 */
    CCU40_CC40->INTE = CCU4_INTE_PME;
    /* GCSS (RM 16-93): S0SE (bit 0) transfers Period+Compare+Passive shadow
     * registers (PRS -> PR); S0PSE (bit 2) is the *prescaler* transfer. */
    CCU40->GCSS = CCU4_GCSS_S0SE | CCU4_GCSS_S0PSE;
    PPB->NVIC_ISER = (1u << IRQN_CCU40_0);
    CCU40_CC40->TCSET = CCU4_TCSET_TRBS;
}

uint32_t timer_millis(void)
{
    return s_ms;
}

/* strong handler overrides the weak default in system.c */
void CCU40_0_IRQHandler(void)
{
    CCU40_CC40->SWR = CCU4_SWR_RPM;   /* clear period match flag */
    s_ms++;
}
