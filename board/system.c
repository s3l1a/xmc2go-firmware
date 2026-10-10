/*
 * system.c - XMC1100 reset handler and minimal C runtime init.
 */
#include "xmc1100_regs.h"
#include "system.h"
#include "config.h"

uint32_t g_reset_cause;

/* linker symbols (see link_*.ld) */
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss;
extern uint32_t VeneerLoadAddr, VeneerStart, VeneerEnd;
extern int main(void);

void Reset_Handler(void)
{
    uint32_t *src, *dst, *end;

    /* 1. install the veneer table at 0x2000000C (from our flash image) */
    src = &VeneerLoadAddr;
    dst = &VeneerStart;
    end = &VeneerEnd;
    while (dst < end) {
        *dst++ = *src++;
    }

    /* 2. copy .data */
    src = &_sidata;
    dst = &_sdata;
    end = &_edata;
    while (dst < end) {
        *dst++ = *src++;
    }

    /* 3. zero .bss */
    dst = &_sbss;
    end = &_ebss;
    while (dst < end) {
        *dst++ = 0u;
    }

    SystemInit();
    (void)main();
    for (;;) {
    }
}

void SystemInit(void)
{
    /* Clock: SSW already installed our CLK_VAL1 (CLKCR = IDIV 1 -> 32 MHz).
     * Re-apply explicitly so we do not depend on SSW details, then enable the
     * peripheral clocks we use (RM 12.5.3: most modules are gated after reset).
     */
    SCU_CLOCK->CLKCR = CFG_CLKCR_VALUE;
    SCU_CLOCK->CGATCLR0 = SCU_CLOCK_CGAT_CCU40 | SCU_CLOCK_CGAT_USIC0 |
                          SCU_CLOCK_CGAT_WDT;

    /* Capture and clear the reset cause (RM 18.1.2: clear with RSTCLR). */
    g_reset_cause = SCU_RESET->RSTSTAT;
    SCU_RESET->RSTCLR = SCU_RESET_RSTCLR_RSCLR;

    /* Interrupts: the bootloader hands over with PRIMASK set (cpsid i during
     * the MSP switch). Every image re-enables them once initialized so ISRs
     * can fire; NVIC sources stay masked until explicitly enabled. */
    __asm volatile("cpsie i");
}

void SystemReset(void)
{
    /* AIRCR: SYSRESETREQ (CMSIS core_cm0) */
    volatile uint32_t *aircr = (volatile uint32_t *)0xE000ED0Cu;
    *aircr = (0x5FAu << 16) | (1u << 2);
    for (;;) {
    }
}

/* ---- default handlers: veneers route unused IRQs here ---- */
__attribute__((weak)) void Default_Handler(void)
{
    for (;;) {
    }
}

__attribute__((weak)) void HardFault_Handler(void)
{
    for (;;) {
    }
}

__attribute__((weak)) void SVC_Handler(void) {}
__attribute__((weak)) void PendSV_Handler(void) {}
__attribute__((weak)) void SysTick_Handler(void) {}
__attribute__((weak)) void SCU_0_IRQHandler(void) {}
__attribute__((weak)) void SCU_1_IRQHandler(void) {}
__attribute__((weak)) void SCU_2_IRQHandler(void) {}
__attribute__((weak)) void ERU0_0_IRQHandler(void) {}
__attribute__((weak)) void ERU0_1_IRQHandler(void) {}
__attribute__((weak)) void ERU0_2_IRQHandler(void) {}
__attribute__((weak)) void ERU0_3_IRQHandler(void) {}
__attribute__((weak)) void USIC0_0_IRQHandler(void) {}
__attribute__((weak)) void USIC0_1_IRQHandler(void) {}
__attribute__((weak)) void USIC0_2_IRQHandler(void) {}
__attribute__((weak)) void USIC0_3_IRQHandler(void) {}
__attribute__((weak)) void USIC0_4_IRQHandler(void) {}
__attribute__((weak)) void USIC0_5_IRQHandler(void) {}
__attribute__((weak)) void VADC0_C0_0_IRQHandler(void) {}
__attribute__((weak)) void VADC0_C0_1_IRQHandler(void) {}
__attribute__((weak)) void CCU40_0_IRQHandler(void) {}
__attribute__((weak)) void CCU40_1_IRQHandler(void) {}
__attribute__((weak)) void CCU40_2_IRQHandler(void) {}
__attribute__((weak)) void CCU40_3_IRQHandler(void) {}
