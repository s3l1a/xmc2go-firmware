#ifndef XMC_FLASH_H
#define XMC_FLASH_H

#include <stdint.h>
#include <stddef.h>

/* NVM driver (RM chapter 8):
 *   write unit = 16-byte block (4 words, ECC generated automatically)
 *   erase unit = 256-byte page
 *   protection unit = 4 KB sector (NVMCONF.SECPROT, optional)
 *
 * Range checks: every operation is refused unless the target range lies fully
 * inside one application slot. The bootloader region, the metadata region and
 * the configuration sector (CS0, holds the BMI at 0x10000E00) are protected in
 * software; writing CS0 could change the BMI and brick the board (CAVEATS.md).
 */

/* Returns 0 on success, negative error otherwise. */
int flash_erase_slot(uint32_t slot_start, uint32_t slot_size);
int flash_erase_page(uint32_t addr);            /* addr 256-byte aligned */
int flash_write_block(uint32_t addr, const uint8_t data[16]);
int flash_write_block_verify(uint32_t addr, const uint8_t data[16]);

/* Range check helper used by all of the above (also unit-testable on host). */
int flash_range_is_writable(uint32_t addr, uint32_t len);

/* Optional hardware write-protection of the bootloader sectors.
 * Disabled by default (see docs/ENVIRONMENT.md TODO). */
void flash_protect_bootloader(void);

#define FLASH_OK 0
#define FLASH_ERR_RANGE -1
#define FLASH_ERR_ALIGN -2
#define FLASH_ERR_BUSY -3
#define FLASH_ERR_VERIFY -4

#endif
