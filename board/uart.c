/*
 * uart.c - USIC0_CH0 ASC (UART) driver, polled.
 *
 * Pin routing (XMC1100 datasheet Table 9 + RM Table 14-22):
 *   TX: P2.1 = USIC0_CH0.DOUT0, alternate output 6 -> IOCR PC = 0x16
 *   RX: P2.2 -> USIC0_CH0.DX3A (DX3CR.DSEL=0/A), the DX3 input stage output
 *       (DX3INS) feeds DX0G (DX0CR.DSEL=6/G) which is the ASC receiver input
 *       DIN0 (RM 14.3.2.2 "receiver input signal DIN0").
 *
 * Baud rate (RM 14.3.3.2, eq. 14.6):
 *   fASC = fPIN / ((PDIV+1) * (PCTQ+1) * (DCTQ+1)), fPIN = fFD
 *   fFD  = fPB * STEP/1024 (FDR fractional mode)
 *   PCLK = 32 MHz: STEP=59 -> fFD = 1.84375 MHz; PDIV=0, PCTQ=0, DCTQ=15
 *   -> fASC = 115234 baud (+0.03% vs 115200).
 *
 * Critical register facts (verified against RM 14.11 and against the factory
 * demo configuration read off a live board):
 *   SCTR.TRM must be 01b or "data frame transfers are not possible"
 *   SCTR.PDL = 1: passive (idle) level high, as UART requires
 *   TCSR.TDEN = 01b: transmission start allowed when TCSR.TDV = 1
 *   TCSR.TDSSM = 1: TDV is cleared by the TBI event
 */
#include "xmc1100_regs.h"
#include "uart.h"
#include "delay.h"
#include "config.h"

#define UART_CHANNEL USIC0_CH0
#define UART_PORT   PORT2
#define UART_TX_PIN 1u   /* P2.1 */
#define UART_RX_PIN 2u   /* P2.2 */

#define SCTR_VALUE ((7u << USIC_SCTR_WLE_Pos) | (7u << USIC_SCTR_FLE_Pos) | \
                    USIC_SCTR_TRM_ACTIVE_HIGH | USIC_SCTR_PDL)
#define PCR_VALUE  (USIC_PCR_SMD | (9u << USIC_PCR_SP_Pos))
#define TCSR_VALUE ((1u << 10) | (1u << 8))  /* TDEN=01, TDSSM=1 */
#define BRG_VALUE  (0u /* CLKSEL=fFD */ | (0u << USIC_BRG_CTQSEL_Pos) | \
                    (0u << USIC_BRG_PCTQ_Pos) | (15u << USIC_BRG_DCTQ_Pos) | \
                    (0u << USIC_BRG_PDIV_Pos))
#define FDR_VALUE  (USIC_FDR_DM_FRACTIONAL | 59u)

void uart_init(void)
{
    /* clocks: USIC0 already un-gated in SystemInit; be explicit */
    SCU_CLOCK->CGATCLR0 = SCU_CLOCK_CGAT_USIC0;

    /* Enable the pads! P2_PDISC resets with every pad disabled (RM 17.8.3:
     * PDISx = 1 disables the pad). Without this nothing reaches the pin. */
    UART_PORT->PDISC &= ~((1u << UART_TX_PIN) | (1u << UART_RX_PIN));

    /* pins: TX push-pull ALT6, RX plain input (P2.2 is input-only) */
    UART_PORT->IOCR0 =
        (UART_PORT->IOCR0 & ~(0x1Fu << (3u + 8u * UART_TX_PIN))) |
        ((uint32_t)PORT_PC_OUT_ALT6_PP << (3u + 8u * UART_TX_PIN));
    UART_PORT->IOCR0 =
        (UART_PORT->IOCR0 & ~(0x1Fu << (3u + 8u * UART_RX_PIN))) |
        ((uint32_t)PORT_PC_INPUT << (3u + 8u * UART_RX_PIN));

    /* enable channel kernel (RM 14.2.2.2: MODEN with BPMODEN) */
    UART_CHANNEL->KSCFG = USIC_KSCFG_MODEN | USIC_KSCFG_BPMODEN;

    /* ASC mode */
    UART_CHANNEL->CCR = 0u;
    UART_CHANNEL->SCTR = SCTR_VALUE;
    UART_CHANNEL->TCSR = TCSR_VALUE;
    UART_CHANNEL->FDR = FDR_VALUE;
    UART_CHANNEL->BRG = BRG_VALUE;

    /* RX routing: P2.2 -> DX3A -> DX3INS -> DX0G -> ASC DIN0 */
    UART_CHANNEL->DX3CR = (0u << USIC_DX_DSEL_Pos); /* source A = P2.2 */
    UART_CHANNEL->DX0CR = (6u << USIC_DX_DSEL_Pos); /* source G = DX3INS */

    UART_CHANNEL->PCR = PCR_VALUE;
    UART_CHANNEL->PSCR = 0xFFFFFFFFu;   /* clear stale flags */
    UART_CHANNEL->CCR = USIC_CCR_MODE_ASC;
}

/* PSR.TBIF (bit 13) is an *event*: it is only set once a transmission has
 * started ("TBUF free again"). Waiting for it before the very first byte
 * deadlocks, so track outstanding data in software. */
static volatile uint8_t s_tx_busy;

static void uart_wait_tbuf_free(void)
{
    if (s_tx_busy) {
        while ((UART_CHANNEL->PSR & (1u << 13)) == 0u) {  /* PSR.TBIF */
        }
        UART_CHANNEL->PSCR = (1u << 13);                  /* clear TBIF */
    }
}

void uart_putc(char c)
{
    if (c == '\n') {
        uart_putc('\r');
    }
    uart_wait_tbuf_free();
    UART_CHANNEL->TBUF[0] = (uint16_t)(uint8_t)c;
    s_tx_busy = 1u;
}

void uart_write(const uint8_t *data, size_t len)
{
    size_t i;
    for (i = 0; i < len; i++) {
        uart_wait_tbuf_free();
        UART_CHANNEL->TBUF[0] = data[i];
        s_tx_busy = 1u;
    }
}

void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

void uart_flush_tx(void)
{
    if (s_tx_busy) {
        while ((UART_CHANNEL->PSR & (1u << 13)) == 0u) {  /* TBUF consumed */
        }
        UART_CHANNEL->PSCR = (1u << 13);
        s_tx_busy = 0u;
    }
    while ((UART_CHANNEL->PSR & USIC_PSR_BUSY) != 0u) {   /* frame done */
    }
}

int uart_getc_nonblock(void)
{
    if ((UART_CHANNEL->PSR & USIC_PSR_RFF) != 0u) {
        uint16_t v = (uint16_t)(UART_CHANNEL->RBUF & 0xFFu);
        UART_CHANNEL->PSCR = USIC_PSR_RFF;
        return (int)v;
    }
    return -1;
}

int uart_getc_timeout(uint32_t timeout_ms)
{
    uint32_t start = sys_tick_now_ms();
    for (;;) {
        int c = uart_getc_nonblock();
        if (c >= 0) {
            return c;
        }
        if (timeout_ms == 0u) {
            return -1;
        }
        if ((sys_tick_now_ms() - start) >= timeout_ms) {
            return -1;
        }
    }
}
