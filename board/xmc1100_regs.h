/*
 * xmc1100_regs.h - minimal XMC1100 register definitions, ONLY what this
 * project uses. Addresses and bit positions verified against:
 *   - Keil/CMSIS XMC1100.h (SVD-generated from XMC1100 Reference Manual v1.0)
 *     https://www.keil.com/dd/docs/arm/infineon/xmc1100/xmc1100.h
 *   - XMC1100 Reference Manual v1.0 (2013-03): chapters 2 (CPU/vecs), 8 (NVM),
 *     10 (WDT), 12 (SCU), 14 (USIC), 17 (Ports), 18 (Boot/SSW)
 *   - XMC1100 AB-Step Datasheet (pin mux Table 9)
 * Anything not verified is marked TODO(verify). Never invent addresses.
 */
#ifndef XMC1100_REGS_H
#define XMC1100_REGS_H

#include <stdint.h>

#define __IO volatile
#define __I  volatile const

/* ---- memory map (RM 8.2, 18.2) ---- */
#define XMC_FLASH_BASE      0x10001000u  /* program flash (CS0 at 0x10000000!) */
#define XMC_RAM_BASE        0x20000000u
#define XMC_RAM_SIZE        0x4000u      /* 16 KB */
#define XMC_VENEER_BASE     0x2000000Cu  /* remapped vector table (RM 2.5.4.1) */

/* ---- peripheral bases (CMSIS XMC1100.h) ---- */
#define SCU_GENERAL_BASE    0x40010000u
#define SCU_CLOCK_BASE      0x40010300u
#define SCU_RESET_BASE      0x40010400u
#define WDT_BASE            0x40020000u
#define NVM_BASE            0x40050000u
#define PORT0_BASE          0x40040000u
#define PORT1_BASE          0x40040100u
#define PORT2_BASE          0x40040200u
#define USIC0_CH0_BASE      0x48000000u
#define USIC0_CH1_BASE      0x48000200u
#define CCU40_BASE          0x48040000u
#define CCU40_CC40_BASE     0x48040100u
#define PPB_BASE            0xE000E000u

/* ---- SCU_GENERAL (0x40010000) ---- */
typedef struct {
    __I  uint32_t DBGROMID;   /* 0x00 */
    __IO uint32_t IDCHIP;     /* 0x04 */
    __I  uint32_t ID;         /* 0x08 */
    __I  uint32_t RESERVED0[2];
    __IO uint32_t SSW0;       /* 0x14 */
    __I  uint32_t RESERVED1[3];
    __IO uint32_t PASSWD;     /* 0x24 */
    __I  uint32_t RESERVED2[2];
    __I  uint32_t CCUCON;     /* 0x30 */
} SCU_GENERAL_Type;

#define SCU_GENERAL ((SCU_GENERAL_Type *)SCU_GENERAL_BASE)
#define SCU_GENERAL_PASSWD_PASS_Pos 3u   /* password field [7:3] */
#define SCU_GENERAL_PASSWD_PROTS_Pos 2u

/* ---- SCU_CLOCK (0x40010300) ---- */
typedef struct {
    __IO uint32_t CLKCR;      /* 0x00 */
    __IO uint32_t PWRSVCR;    /* 0x04 */
    __I  uint32_t CGATSTAT0;  /* 0x08 */
    __IO uint32_t CGATSET0;   /* 0x0C */
    __IO uint32_t CGATCLR0;   /* 0x10 */
    __IO uint32_t OSCCSR;     /* 0x14 */
} SCU_CLOCK_Type;

#define SCU_CLOCK ((SCU_CLOCK_Type *)SCU_CLOCK_BASE)
#define SCU_CLOCK_CLKCR_FDIV_Pos 0u    /* [7:0] */
#define SCU_CLOCK_CLKCR_IDIV_Pos 8u    /* [15:8] */
#define SCU_CLOCK_CLKCR_PCLKSEL_Pos 16u
/* MCLK = dco1_dclk(64MHz) / (2 * (IDIV + FDIV/256)); IDIV=1,FDIV=0 -> 32 MHz */

/* CGATCLR0/CGATSET0/CGATSTAT0 bit positions (CMSIS + RM 12.5.3) */
#define SCU_CLOCK_CGAT_VADC   (1u << 0)
#define SCU_CLOCK_CGAT_CCU80  (1u << 1)
#define SCU_CLOCK_CGAT_CCU40  (1u << 2)
#define SCU_CLOCK_CGAT_USIC0  (1u << 3)
#define SCU_CLOCK_CGAT_WDT    (1u << 9)
#define SCU_CLOCK_CGAT_RTC    (1u << 10)

/* ---- SCU_RESET (0x40010400) ---- */
typedef struct {
    __I  uint32_t RSTSTAT;    /* 0x00 */
    __IO uint32_t RSTSET;     /* 0x04 */
    __IO uint32_t RSTCLR;     /* 0x08 */
    __IO uint32_t RSTCON;     /* 0x0C */
} SCU_RESET_Type;

#define SCU_RESET ((SCU_RESET_Type *)SCU_RESET_BASE)
/* RSTSTAT[9:0] (RM 12.4.2): bit0 POR/BOR, bit1 master reset via MRSTEN,
 * bit2 CPU system reset, bit3 CPU lockup, bit4 flash ECC, bit5 WDT reset,
 * bit6 loss of clock, bit7 parity error */
#define SCU_RESET_RSTSTAT_PORST   (1u << 0)
#define SCU_RESET_RSTSTAT_MRSTEN  (1u << 1)
#define SCU_RESET_RSTSTAT_SWRESET (1u << 2)
#define SCU_RESET_RSTSTAT_LOCKUP  (1u << 3)
#define SCU_RESET_RSTSTAT_ECC     (1u << 4)
#define SCU_RESET_RSTSTAT_WDT     (1u << 5)
#define SCU_RESET_RSTSTAT_LOCS    (1u << 6)
#define SCU_RESET_RSTSTAT_PARITY  (1u << 7)
#define SCU_RESET_RSTCLR_RSCLR    (1u << 0)

/* ---- WDT (0x40020000, RM chapter 10) ---- */
typedef struct {
    __I  uint32_t ID;      /* 0x00 */
    __IO uint32_t CTR;     /* 0x04 */
    __IO uint32_t SRV;     /* 0x08 */
    __I  uint32_t TIM;     /* 0x0C */
    __IO uint32_t WLB;     /* 0x10 */
    __IO uint32_t WUB;     /* 0x14 */
    __I  uint32_t WDTSTS;  /* 0x18 */
    __IO uint32_t WDTCLR;  /* 0x1C */
} WDT_Type;

#define WDT ((WDT_Type *)WDT_BASE)
#define WDT_CTR_ENB   (1u << 0)   /* enable */
#define WDT_CTR_PRE   (1u << 1)   /* pre-warning enable */
#define WDT_CTR_DSP   (1u << 4)   /* 0 = stop in debug halt (default) */
#define WDT_CTR_SPW_Pos 8u        /* service pulse width [15:8] */
#define WDT_SRV_MAGIC 0xABADCAFEu /* RM 10.9.1: service magic word */
#define WDT_WDTSTS_ALMS (1u << 0)
#define WDT_WDTCLR_ALMC (1u << 0)
/* WLB = 0 disables the window (service allowed at any count < WUB) */

/* ---- NVM (0x40050000, RM chapter 8) ---- */
typedef struct {
    __I  uint16_t NVMSTATUS;  /* 0x00 */
    __I  uint16_t RESERVED0;
    __IO uint16_t NVMPROG;    /* 0x04 */
    __I  uint16_t RESERVED1;
    __IO uint16_t NVMCONF;    /* 0x08 */
} NVM_Type;

#define NVM ((NVM_Type *)NVM_BASE)
#define NVM_STATUS_BUSY      (1u << 0)
#define NVM_STATUS_SLEEP     (1u << 1)
#define NVM_STATUS_VERR_Msk  (3u << 2)
#define NVM_STATUS_ECC1READ  (1u << 4)
#define NVM_STATUS_ECC2READ  (1u << 5)
#define NVM_STATUS_WRPERR    (1u << 6)
/* NVMPROG.ACTION values (RM 8.8) */
#define NVM_ACTION_IDLE          0x00u
#define NVM_ACTION_WRITE_VERIFY  0x51u  /* one-shot write, auto verify */
#define NVM_ACTION_WRITE         0x91u  /* one-shot write, no verify */
#define NVM_ACTION_PAGE_ERASE    0x92u  /* one-shot page erase */
/* NVMCONF */
#define NVM_CONF_NVM_ON   (1u << 15)
#define NVM_CONF_SECPROT_Pos 4u   /* [11:4] protect sectors 0..N-1 */

/* ---- PORT (0x40040x00, RM chapter 17) ---- */
typedef struct {
    __IO uint32_t OUT;        /* 0x00 */
    __IO uint32_t OMR;        /* 0x04 */
    __I  uint32_t RESERVED0[2];
    __IO uint32_t IOCR0;      /* 0x10  PC0..PC3 at [7:3],[15:11],[23:19],[31:27] */
    __IO uint32_t IOCR4;      /* 0x14 */
    __IO uint32_t IOCR8;      /* 0x18 */
    __IO uint32_t IOCR12;     /* 0x1C */
    __I  uint32_t RESERVED1;
    __I  uint32_t IN;         /* 0x24 */
    __I  uint32_t RESERVED2[14];
    __IO uint32_t PDISC;      /* 0x60  PDISx: 1 = pad DISABLED (RM 17.8.3);
                               * P2_PDISC resets with all pads disabled */
    __I  uint32_t RESERVED3[3];
    __IO uint32_t PPS;        /* 0x70 */
    __IO uint32_t HWSEL;      /* 0x74 */
} PORT_Type;

#define PORT0 ((PORT_Type *)PORT0_BASE)
#define PORT1 ((PORT_Type *)PORT1_BASE)
#define PORT2 ((PORT_Type *)PORT2_BASE)

#define PORT_OMR_PS(pin)  (1u << (pin))          /* set output bit */
#define PORT_OMR_PR(pin)  (1u << (16u + (pin)))  /* reset output bit */
/* Table 17-5 PC coding */
#define PORT_PC_INPUT          0x00u
#define PORT_PC_INPUT_PULLUP   0x02u
#define PORT_PC_OUT_GPIO_PP    0x10u
#define PORT_PC_OUT_GPIO_OD    0x18u
#define PORT_PC_OUT_ALT6_PP    0x16u  /* push-pull alternate output 6 */

/* ---- USIC channel (0x48000000 / 0x48000200, RM chapter 14) ---- */
typedef struct {
    __I  uint32_t RESERVED0;
    __I  uint32_t CCFG;       /* 0x04 */
    __I  uint32_t RESERVED1;
    __IO uint32_t KSCFG;      /* 0x0C */
    __IO uint32_t FDR;        /* 0x10 */
    __IO uint32_t BRG;        /* 0x14 */
    __IO uint32_t INPR;       /* 0x18 */
    __IO uint32_t DX0CR;      /* 0x1C */
    __IO uint32_t DX1CR;      /* 0x20 */
    __IO uint32_t DX2CR;      /* 0x24 */
    __IO uint32_t DX3CR;      /* 0x28 */
    __IO uint32_t DX4CR;      /* 0x2C */
    __IO uint32_t DX5CR;      /* 0x30 */
    __IO uint32_t SCTR;       /* 0x34 */
    __IO uint32_t TCSR;       /* 0x38 */
    __IO uint32_t PCR;        /* 0x3C (ASC mode layout) */
    __IO uint32_t CCR;        /* 0x40 */
    __I  uint32_t CMTR;       /* 0x44 */
    __I  uint32_t PSR;        /* 0x48 */
    __IO uint32_t PSCR;       /* 0x4C */
    __I  uint32_t RBUFSR;     /* 0x50 */
    __I  uint32_t RBUF;       /* 0x54 */
    __I  uint32_t RBUFD;      /* 0x58 */
    __I  uint32_t RBUF0;      /* 0x5C */
    __I  uint32_t RBUF1;      /* 0x60 */
    __I  uint32_t RBUF01SR;   /* 0x64 */
    __IO uint32_t FMR;        /* 0x68 */
    __I  uint32_t RESERVED2[5];
    __IO uint32_t TBUF[32];   /* 0x80 */
} USIC_CH_Type;

#define USIC0_CH0 ((USIC_CH_Type *)USIC0_CH0_BASE)
#define USIC0_CH1 ((USIC_CH_Type *)USIC0_CH1_BASE)

#define USIC_KSCFG_MODEN   (1u << 0)
#define USIC_KSCFG_BPMODEN (1u << 1)
#define USIC_FDR_STEP_Pos  0u    /* [9:0] */
#define USIC_FDR_DM_Pos    14u   /* [15:14] 10b = fractional divider */
#define USIC_FDR_DM_FRACTIONAL (2u << 14u)
#define USIC_BRG_CLKSEL_Pos 0u   /* [1:0] 00b = fPIN = fFD */
#define USIC_BRG_CTQSEL_Pos 6u   /* [7:6] 00b = fCTQIN = fPDIV */
#define USIC_BRG_PCTQ_Pos   8u   /* [9:8] */
#define USIC_BRG_DCTQ_Pos   10u  /* [14:10] time quanta per bit - 1 */
#define USIC_BRG_PDIV_Pos   16u  /* [25:16] */
#define USIC_DX_DSEL_Pos    0u   /* [2:0] source A..G */
#define USIC_DX_DSEN        (1u << 6)
#define USIC_SCTR_SDIR      (1u << 0)  /* MSB first */
#define USIC_SCTR_PDL       (1u << 1)  /* passive data level: 1 = idle high */
#define USIC_SCTR_TRM_Pos   8u   /* [9:8] transmission mode: 01b = active-high,
                                   * required for any data transfer (RM 14.11) */
#define USIC_SCTR_TRM_ACTIVE_HIGH (1u << 8)
#define USIC_SCTR_FLE_Pos   16u  /* [21:16] frame length - 1 */
#define USIC_SCTR_WLE_Pos   24u  /* [27:24] word length - 1 */
#define USIC_PCR_SMD        (1u << 0)  /* majority decision sampling */
#define USIC_PCR_STPB       (1u << 1)  /* 2 stop bits */
#define USIC_PCR_SP_Pos     8u   /* [12:8] sample point */
#define USIC_PCR_RSTEN      (1u << 16) /* PSR.BUSY follows receiver */
#define USIC_PCR_TSTEN      (1u << 17) /* PSR.BUSY follows transmitter */
#define USIC_CCR_MODE_Pos   0u   /* [3:0] 2 = ASC (UART) */
#define USIC_CCR_MODE_ASC   (2u << 0)
#define USIC_PSR_RXIDLE     (1u << 1)
#define USIC_PSR_RFF        (1u << 7)  /* receive frame finished */
#define USIC_PSR_TFF        (1u << 8)  /* transmit frame finished */
#define USIC_PSR_BUSY       (1u << 9)
#define USIC_TBUF_TDATA_Pos 0u

/* ---- CCU4 (0x48040000 + 0x100*n, RM chapter 17 of CCU4 doc set) ---- */
typedef struct {
    __IO uint32_t GCTRL;      /* 0x00 */
    __I  uint32_t GSTAT;      /* 0x04 */
    __IO uint32_t GIDLS;      /* 0x08 */
    __IO uint32_t GIDLC;      /* 0x0C */
    __IO uint32_t GCSS;       /* 0x10 */
    __IO uint32_t GCSC;       /* 0x14 */
    __I  uint32_t GCST;       /* 0x18 */
} CCU4_GLOBAL_Type;

typedef struct {
    __IO uint32_t INS;        /* 0x00 */
    __IO uint32_t CMC;        /* 0x04 */
    __I  uint32_t TCST;       /* 0x08 */
    __IO uint32_t TCSET;      /* 0x0C */
    __IO uint32_t TCCLR;      /* 0x10 */
    __IO uint32_t TC;         /* 0x14 */
    __IO uint32_t PSL;        /* 0x18 */
    __I  uint32_t DIT;        /* 0x1C */
    __I  uint32_t DITS;       /* 0x20 */
    __IO uint32_t PSC;        /* 0x24 */
    __IO uint32_t FPC;        /* 0x28 */
    __IO uint32_t FPCS;       /* 0x2C */
    __IO uint32_t PR;         /* 0x30 */
    __IO uint32_t PRS;        /* 0x34 */
    __I  uint32_t CR;         /* 0x38 */
    __I  uint32_t CRS;        /* 0x3C */
    __I  uint32_t RESERVED0[12];
    __I  uint32_t TIMER;      /* 0x70 */
    __I  uint32_t RESERVED1[11];
    __I  uint32_t INTS;       /* 0xA0 */
    __IO uint32_t INTE;       /* 0xA4 */
    __IO uint32_t SRS;        /* 0xA8 */
    __IO uint32_t SWS;        /* 0xAC */
    __IO uint32_t SWR;        /* 0xB0 */
} CCU4_CC4_Type;

#define CCU40      ((CCU4_GLOBAL_Type *)CCU40_BASE)
#define CCU40_CC40 ((CCU4_CC4_Type *)CCU40_CC40_BASE)

#define CCU4_GIDLC_CS0I   (1u << 0)  /* clear slice 0 idle */
#define CCU4_GIDLC_SPRB   (1u << 8)  /* start prescalers */
#define CCU4_GCSS_S0SE    (1u << 0)  /* slice 0 shadow transfer (PRS->PR etc) */
#define CCU4_GCSS_S0PSE   (1u << 2)  /* slice 0 prescaler shadow transfer */
#define CCU4_TCSET_TRBS   (1u << 0)  /* start timer */
#define CCU4_TCCLR_TRBC   (1u << 0)  /* stop timer */
#define CCU4_PSC_PSIV_Pos 0u         /* [3:0] prescaler: /2^PSIV */
#define CCU4_INTS_PMUS    (1u << 0)  /* period match status */
#define CCU4_INTE_PME     (1u << 0)  /* period match interrupt enable */
#define CCU4_SRS_POSR_Pos 0u         /* [1:0] period match service request */
#define CCU4_SWR_RPM      (1u << 0)  /* clear period match flag */

/* ---- PPB: NVIC (CMSIS core_cm0) ---- */
typedef struct {
    __I  uint32_t RESERVED0[4];
    __IO uint32_t SYST_CSR;   /* 0x10 */
    __IO uint32_t SYST_RVR;   /* 0x14 */
    __IO uint32_t SYST_CVR;   /* 0x18 */
    __I  uint32_t SYST_CALIB; /* 0x1C */
    __I  uint32_t RESERVED1[56];
    __IO uint32_t NVIC_ISER;  /* 0x100 (ARMv6-M standard NVIC; verified on
                               * silicon: writes read back at 0xE000E100) */
} PPB_Type;

#define PPB ((PPB_Type *)PPB_BASE)

/* IRQ numbers (CMSIS IRQn_Type) */
#define IRQN_SCU_0     0
#define IRQN_USIC0_0   9
#define IRQN_CCU40_0   21

#endif /* XMC1100_REGS_H */
