/*
 * meta.c - append-only metadata log in two flash sectors.
 * A record is 16 bytes = one flash block. Blocks are appended in order; a
 * half-written block (power loss) fails its CRC and is ignored. When one bank
 * fills, the other is erased and receives the next record before the old bank
 * is touched. At least one valid record therefore survives rollover.
 */
#include "meta.h"
#include "flash.h"
#include "config.h"

static meta_record_t *block_ptr(uint32_t bank, unsigned idx)
{
    return (meta_record_t *)(uintptr_t)(bank + idx * META_RECORD_SIZE);
}

static int scan_bank(uint32_t bank, meta_record_t *out, unsigned *free_idx)
{
    unsigned i;
    int found = 0;
    uint32_t best_seq = 0;

    *free_idx = CFG_META_SIZE / META_RECORD_SIZE;
    for (i = 0; i < CFG_META_SIZE / META_RECORD_SIZE; i++) {
        meta_record_t *r = block_ptr(bank, i);
        const uint32_t *words = (const uint32_t *)(const void *)r;
        if (*free_idx >= CFG_META_SIZE / META_RECORD_SIZE &&
            words[0] == 0xFFFFFFFFu && words[1] == 0xFFFFFFFFu &&
            words[2] == 0xFFFFFFFFu && words[3] == 0xFFFFFFFFu) {
            *free_idx = i;
        }
        if (meta_record_valid(r)) {
            if (!found || r->seq >= best_seq) {
                *out = *r;
                best_seq = r->seq;
                found = 1;
            }
        }
    }
    return found;
}

int meta_log_read(meta_record_t *out)
{
    meta_record_t a;
    meta_record_t b;
    unsigned free_idx;
    int have_a = scan_bank(CFG_META_START, &a, &free_idx);
    int have_b = scan_bank(CFG_META_BACKUP_START, &b, &free_idx);

    if (!have_a && !have_b) {
        return 0;
    }
    *out = (!have_b || (have_a && a.seq >= b.seq)) ? a : b;
    return 1;
}

static int erase_bank(uint32_t bank)
{
    uint32_t off;
    for (off = 0; off < CFG_META_SIZE; off += CFG_FLASH_PAGE_SIZE) {
        if (flash_erase_page(bank + off) != FLASH_OK) {
            return -1;
        }
    }
    return 0;
}

int meta_log_append(meta_record_t *rec)
{
    meta_record_t latest_a;
    meta_record_t latest_b;
    unsigned free_a;
    unsigned free_b;
    int have_a = scan_bank(CFG_META_START, &latest_a, &free_a);
    int have_b = scan_bank(CFG_META_BACKUP_START, &latest_b, &free_b);
    uint32_t bank;
    unsigned free_idx;

    rec->magic = META_MAGIC;
    rec->crc16 = meta_record_crc(rec);

    if (!have_b || (have_a && latest_a.seq >= latest_b.seq)) {
        bank = CFG_META_START;
        free_idx = free_a;
    } else {
        bank = CFG_META_BACKUP_START;
        free_idx = free_b;
    }

    if (free_idx >= CFG_META_SIZE / META_RECORD_SIZE) {
        /* Preserve the full bank until record 0 is valid in the other bank. */
        bank = (bank == CFG_META_START) ? CFG_META_BACKUP_START : CFG_META_START;
        if (erase_bank(bank) != 0) {
            return -1;
        }
        free_idx = 0;
    }

    return flash_write_block_verify(bank + free_idx * META_RECORD_SIZE,
                                    (const uint8_t *)rec) == FLASH_OK ? 0 : -1;
}
