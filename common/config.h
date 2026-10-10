/*
 * config.h - board and layout configuration shared by bootloader, apps and host.
 *
 * LED pin mapping (READ THIS):
 * The XMC 2Go user manual contradicts itself:
 *   - Table 1 (key features) and Figure 1 (block diagram): LED1 = P1.0, LED2 = P1.1
 *   - Section 2.3 text: "port pins P1.0 and P1.2 ... connected to LEDs"
 *   - Table 2: LED1 = P1.1, LED2 = P1.0
 * The board SCHEMATIC (Figure 5 of the manual, net labels P1.0/LED1 and P1.1/LED2)
 * shows LED1 on P1.0 and LED2 on P1.1. We use the schematic mapping.
 * TODO(verify): confirm against the physical board/schematic before relying on
 * which LED is "LED1"; if swapped, only the two CFG_LEDx defines must change.
 */
#ifndef XMC_CFG_H
#define XMC_CFG_H

/* ---- LED pins (see header comment; schematic mapping) ---- */
#define CFG_LED1_PORT 1u   /* LED1 = P1.0 */
#define CFG_LED1_PIN  0u
#define CFG_LED2_PORT 1u   /* LED2 = P1.1 */
#define CFG_LED2_PIN  1u

/* ---- System clock ---- */
/* DCO1 = 64 MHz; MCLK = dco1_dclk / (2 * (IDIV + FDIV/256)).
 * IDIV=1, FDIV=0 -> MCLK = 32 MHz, PCLK = 32 MHz (CLKCR.PCLKSEL=0).
 * CLK_VAL1 word at 0x10001010 makes the SSW program this before our reset runs. */
#define CFG_MCLK_HZ 32000000u
#define CFG_PCLK_HZ 32000000u
#define CFG_CLKCR_VALUE 0x00000100u /* IDIV=1, FDIV=0, PCLKSEL=0 */

/* ---- UART (USBCOM of the onboard J-Link) ----
 * TX = P2.1 (USIC0_CH0.DOUT0, ALT6), RX = P2.2 (via DX3A -> DX3INS -> DX0G).
 * 115200 8N1. fFD = PCLK * 59/1024 = 1.84375 MHz; 16 TQ/bit -> 115234 baud
 * (+0.03% error). */
#define CFG_UART_BAUD 115200u

/* ---- Watchdog (window WDT, fWDT = 32.768 kHz standby clock) ----
 * WUB = ticks until reset; WLB = 0 disables the window (service any time).
 * 5.0 s: 5 * 32768 = 163840 ticks. */
#define CFG_WDT_TIMEOUT_MS 5000u
#define CFG_WDT_HZ 32768u
#define CFG_WDT_WUB (((CFG_WDT_TIMEOUT_MS * CFG_WDT_HZ) / 1000u) - 1u)
#define CFG_WDT_MAGIC 0xABADCAFEu
#define CFG_WDT_TRIAL_ATTEMPTS 2u /* failed trials before rollback */

/* ---- Flash map (32 KB device minimum: XMC1100-Q024F0032) ----
 * Program flash base 0x10001000 (RM 8.2: sector address of 0x10001000 = 1;
 * 0x10000000..0x10000FFF is configuration sector CS0 holding the BMI - NEVER
 * write there). Erase unit = 256 B page; write unit = 16 B block; protection
 * unit = 4 KB sector. */
#define CFG_FLASH_BASE 0x10001000u
#define CFG_FLASH_SIZE_MAX 0x8000u      /* 32 KB layout used */
#define CFG_FLASH_PAGE_SIZE 256u
#define CFG_FLASH_BLOCK_SIZE 16u
#define CFG_FLASH_SECTOR_SIZE 4096u

#define CFG_BOOT_START 0x10001000u
#define CFG_BOOT_SIZE 0x2000u           /* 8 KB */
#define CFG_SLOT_A_START 0x10003000u
#define CFG_SLOT_B_START 0x10005000u
#define CFG_SLOT_SIZE 0x2000u           /* 8 KB per slot */
#define CFG_META_START 0x10007000u
#define CFG_META_SIZE 0x1000u           /* 4 KB = 1 sector = 16 pages */
#define CFG_META_BACKUP_START 0x10008000u /* second bank for atomic rollover */

/* ---- SRAM bounds used to validate an application's initial stack pointer ---- */
#define CFG_RAM_START 0x20000000u
#define CFG_RAM_END 0x20004000u         /* 16 KB SRAM, end is a valid initial SP */

/* ---- Protocol version ---- */
#define CFG_PROTO_VERSION 1u
#define CFG_BL_VERSION_MAJOR 1u
#define CFG_BL_VERSION_MINOR 0u
#define CFG_BL_VERSION_PATCH 0u

#endif /* XMC_CFG_H */
