/*
 * flash.c - NVM page erase / block write with strict range checks (RM 8.8).
 *
 * The bootloader region, the metadata region on non-metadata callers, and the
 * configuration sector CS0 (0x10000000..0x10000FFF, contains the BMI) can
 * never be written through this driver. Changing the BMI can make the board
 * unusable (board manual section 2.4), so CS0 is excluded unconditionally.
 */
#include "xmc1100_regs.h"
#include "flash.h"
#include "config.h"

#define FLASH_SECPROT_ENABLE 0  /* TODO(verify): J-Link recovery interaction */

typedef struct {
    uint32_t start;
    uint32_t size;
} flash_region_t;

/* Writable regions: application slots and the two metadata log banks. */
static const flash_region_t k_writable[] = {
    { CFG_SLOT_A_START, CFG_SLOT_SIZE },
    { CFG_SLOT_B_START, CFG_SLOT_SIZE },
    { CFG_META_START,   CFG_META_SIZE },
    { CFG_META_BACKUP_START, CFG_META_SIZE },
};

int flash_range_is_writable(uint32_t addr, uint32_t len)
{
    unsigned i;
    uint32_t end;

    if (len == 0u) {
        return FLASH_ERR_RANGE;
    }
    end = addr + len - 1u;
    if (end < addr) { /* overflow */
        return FLASH_ERR_RANGE;
    }
    for (i = 0; i < sizeof(k_writable) / sizeof(k_writable[0]); i++) {
        uint32_t s = k_writable[i].start;
        uint32_t e = s + k_writable[i].size - 1u;
        if (addr >= s && end <= e) {
            return FLASH_OK;
        }
    }
    return FLASH_ERR_RANGE;
}

static void nvm_wait(void)
{
    while ((NVM->NVMSTATUS & NVM_STATUS_BUSY) != 0u) {
    }
}

int flash_erase_page(uint32_t addr)
{
    int tries;
    if ((addr & (CFG_FLASH_PAGE_SIZE - 1u)) != 0u) {
        return FLASH_ERR_ALIGN;
    }
    if (flash_range_is_writable(addr, CFG_FLASH_PAGE_SIZE) != FLASH_OK) {
        return FLASH_ERR_RANGE;
    }
    for (tries = 0; tries < 2; tries++) {
        volatile const uint8_t *p = (volatile const uint8_t *)(uintptr_t)addr;
        unsigned i;
        nvm_wait();
        NVM->NVMPROG = NVM_ACTION_PAGE_ERASE;
        *(volatile uint32_t *)addr = 0x42u;   /* trigger (RM 8.8.2.1) */
        nvm_wait();
        NVM->NVMPROG = NVM_ACTION_IDLE;
        /* verify the erase by readback (robust against verify-mode quirks) */
        for (i = 0; i < CFG_FLASH_PAGE_SIZE; i++) {
            if (p[i] != 0xFFu) {
                break;
            }
        }
        if (i == CFG_FLASH_PAGE_SIZE) {
            return FLASH_OK;
        }
    }
    return FLASH_ERR_VERIFY;
}

int flash_erase_slot(uint32_t slot_start, uint32_t slot_size)
{
    uint32_t off;
    if ((slot_start & (CFG_FLASH_SECTOR_SIZE - 1u)) != 0u) {
        return FLASH_ERR_ALIGN;
    }
    if (flash_range_is_writable(slot_start, slot_size) != FLASH_OK) {
        return FLASH_ERR_RANGE;
    }
    for (off = 0; off < slot_size; off += CFG_FLASH_PAGE_SIZE) {
        int rc = flash_erase_page(slot_start + off);
        if (rc != FLASH_OK) {
            return rc;
        }
    }
    return FLASH_OK;
}

static int flash_write_block_common(uint32_t addr, const uint8_t data[16],
                                    int verify)
{
    uint32_t words[4];
    volatile uint32_t *dst = (volatile uint32_t *)(uintptr_t)addr;
    volatile const uint32_t *src = (volatile const uint32_t *)(uintptr_t)addr;
    int i;

    if ((addr & (CFG_FLASH_BLOCK_SIZE - 1u)) != 0u) {
        return FLASH_ERR_ALIGN;
    }
    if (flash_range_is_writable(addr, CFG_FLASH_BLOCK_SIZE) != FLASH_OK) {
        return FLASH_ERR_RANGE;
    }
    /* copy to an aligned buffer: the source may be a byte in a frame */
    for (i = 0; i < 4; i++) {
        words[i] = (uint32_t)data[4u * i] |
                   ((uint32_t)data[4u * i + 1u] << 8) |
                   ((uint32_t)data[4u * i + 2u] << 16) |
                   ((uint32_t)data[4u * i + 3u] << 24);
    }
    nvm_wait();
    /* one-shot write WITHOUT auto-verify: hardware "hardread" verify is
     * unreliable on marginally-erased blocks; we verify by readback below. */
    NVM->NVMPROG = NVM_ACTION_WRITE;
    for (i = 0; i < 4; i++) {
        dst[i] = words[i];   /* 4 ascending words of one block (RM 8.3.3) */
    }
    nvm_wait();
    NVM->NVMPROG = NVM_ACTION_IDLE;
    if (verify) {
        for (i = 0; i < 4; i++) {
            if (src[i] != words[i]) {
                return FLASH_ERR_VERIFY;
            }
        }
    }
    return FLASH_OK;
}

int flash_write_block(uint32_t addr, const uint8_t data[16])
{
    return flash_write_block_common(addr, data, 0);
}

int flash_write_block_verify(uint32_t addr, const uint8_t data[16])
{
    return flash_write_block_common(addr, data, 1);
}

void flash_protect_bootloader(void)
{
#if FLASH_SECPROT_ENABLE
    /* Protect sectors 0..2: configuration sector (CS0) + both bootloader
     * sectors (RM 8.3.6: sectors 0..SECPROT-1 cannot be written/erased).
     * TODO(verify): SECPROT sector numbering on silicon and whether J-Link
     * can still reflash protected sectors; leave disabled until tested. */
    NVM->NVMCONF = (uint16_t)((NVM->NVMCONF & ~(0xFFu << NVM_CONF_SECPROT_Pos)) |
                              (3u << NVM_CONF_SECPROT_Pos));
#else
    /* software range checks only (documented in CAVEATS.md) */
#endif
}
