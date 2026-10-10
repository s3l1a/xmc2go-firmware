/*
 * startup.S - XMC1100 user vector table + remapped veneer table (GNU as).
 *
 * Boot model (XMC1100 Reference Manual 2.5.4.1 + 18.2.1):
 *  - The ROM vector table is fixed at 0x00000000 and its entries point to RAM
 *    addresses: HardFault 0x2000000C, SVCall 0x2000002C, PendSV 0x20000038,
 *    SysTick 0x2000003C, IRQn 0x20000040 + 4*n. Region 0x2000000C..0x200000BF.
 *  - Each RAM slot holds a 4-byte veneer: LDR R0,=handler / BX R0. The literal
 *    pool follows the slots.
 *  - The SSW reads initial SP from 0x10001000 and jumps to the address at
 *    0x10001004 (image start + 4). CLK_VAL1/CLK_VAL2 at image+0x10/0x14 are
 *    installed into SCU_CLKCR/SCU_CGATCLR0 when bit31=0 (RM 18.1.3.1).
 *  - App images (slots A/B) use the same layout at their slot start + 0x20;
 *    their startup copies their own veneers over 0x2000000C before use.
 */

.syntax unified
.cpu cortex-m0
.thumb

/* CLK_VAL1: IDIV=1, FDIV=0 -> MCLK = 64MHz/(2*1) = 32 MHz (RM 12.5.2) */
#define CLK_VAL1_VALUE 0x00000100
/* CLK_VAL2: enable CCU40 (bit2), USIC0 (bit3), WDT (bit9) clocks */
#define CLK_VAL2_VALUE 0x0000020C

.section .isr_vector,"a",%progbits
.align 2
.globl g_vectors
g_vectors:
    .word __stack_top          /* 0x00 initial SP (SSW loads this) */
    .word Reset_Handler        /* 0x04 reset (SSW jumps here) */
    .word 0                    /* 0x08 reserved */
    .word 0                    /* 0x0C reserved */
    .word CLK_VAL1_VALUE       /* 0x10 CLK_VAL1 -> SCU_CLKCR[19:0] */
    .word CLK_VAL2_VALUE       /* 0x14 CLK_VAL2 -> SCU_CGATCLR0[10:0] */

.section ".XmcVeneerCode","ax",%progbits
.align 2
.globl VeneerStart
VeneerStart:
    /* 0x2000000C: HardFault (exception 3) */
    ldr r0, =HardFault_Handler
    bx  r0
    /* 0x20000010..0x20000028: reserved exceptions 4..10 */
    .space 28
    /* 0x2000002C: SVCall (exception 11) */
    ldr r0, =SVC_Handler
    bx  r0
    /* 0x20000030..0x20000034: reserved exceptions 12..13 */
    .space 8
    /* 0x20000038: PendSV */
    ldr r0, =PendSV_Handler
    bx  r0
    /* 0x2000003C: SysTick */
    ldr r0, =SysTick_Handler
    bx  r0
    /* 0x20000040: IRQ0..IRQ31 */
    ldr r0, =SCU_0_IRQHandler        /* IRQ0 */
    bx  r0
    ldr r0, =SCU_1_IRQHandler        /* IRQ1 */
    bx  r0
    ldr r0, =SCU_2_IRQHandler        /* IRQ2 */
    bx  r0
    ldr r0, =ERU0_0_IRQHandler       /* IRQ3 */
    bx  r0
    ldr r0, =ERU0_1_IRQHandler       /* IRQ4 */
    bx  r0
    ldr r0, =ERU0_2_IRQHandler       /* IRQ5 */
    bx  r0
    ldr r0, =ERU0_3_IRQHandler       /* IRQ6 */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ7 reserved */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ8 reserved */
    bx  r0
    ldr r0, =USIC0_0_IRQHandler      /* IRQ9 */
    bx  r0
    ldr r0, =USIC0_1_IRQHandler      /* IRQ10 */
    bx  r0
    ldr r0, =USIC0_2_IRQHandler      /* IRQ11 */
    bx  r0
    ldr r0, =USIC0_3_IRQHandler      /* IRQ12 */
    bx  r0
    ldr r0, =USIC0_4_IRQHandler      /* IRQ13 */
    bx  r0
    ldr r0, =USIC0_5_IRQHandler      /* IRQ14 */
    bx  r0
    ldr r0, =VADC0_C0_0_IRQHandler   /* IRQ15 */
    bx  r0
    ldr r0, =VADC0_C0_1_IRQHandler   /* IRQ16 */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ17 reserved */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ18 reserved */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ19 reserved */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ20 reserved */
    bx  r0
    ldr r0, =CCU40_0_IRQHandler      /* IRQ21 */
    bx  r0
    ldr r0, =CCU40_1_IRQHandler      /* IRQ22 */
    bx  r0
    ldr r0, =CCU40_2_IRQHandler      /* IRQ23 */
    bx  r0
    ldr r0, =CCU40_3_IRQHandler      /* IRQ24 */
    bx  r0
    ldr r0, =Default_Handler         /* IRQ25..IRQ31 reserved */
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
    ldr r0, =Default_Handler
    bx  r0
.globl VeneerEnd
VeneerEnd:
    .ltorg
