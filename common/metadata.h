/*
 * metadata.h - persistent boot metadata, append-only log in two flash sectors.
 *
 * Record = 16 bytes = one flash block (write unit). Each 4 KB bank holds 256
 * records. The valid record with the highest sequence across both banks wins.
 * A full bank remains intact until the first record is valid in the other bank,
 * so power loss during append or rollover leaves the previous state available.
 *
 * meta_boot_decision() is pure logic (no hardware) so it can be unit-tested on
 * the host (mirrored in host/updater/xmcup/metadata.py).
 */
#ifndef XMC_METADATA_H
#define XMC_METADATA_H

#include <stdint.h>
#include "crc16.h"
#include "config.h"

#define META_MAGIC 0x4154454Du /* 'M','E','T','A' */
#define META_RECORD_SIZE 16u

/* per-slot flag bits */
#define META_FLAG_VALID 0x01u  /* image was verified at least once */
#define META_FLAG_TRIAL 0x02u  /* booted but not yet marked healthy */
#define META_FLAG_BAD 0x04u    /* failed trial limit or corrupt: never boot */

typedef struct {
    uint32_t magic;
    uint32_t seq;
    uint8_t active_slot;   /* 0 = A, 1 = B */
    uint8_t flags_a;
    uint8_t flags_b;
    uint8_t attempts;      /* failed boot attempts of the current trial */
    uint16_t boot_count;   /* informational */
    uint16_t crc16;        /* CRC-16/CCITT-FALSE over bytes 0x00..0x0D */
} meta_record_t;

_Static_assert(sizeof(meta_record_t) == META_RECORD_SIZE, "meta record size");

static inline uint16_t meta_record_crc(const meta_record_t *r)
{
    return crc16_ccitt((const uint8_t *)r, META_RECORD_SIZE - 2u);
}

static inline int meta_record_valid(const meta_record_t *r)
{
    if (r->magic != META_MAGIC) {
        return 0;
    }
    if (r->active_slot > 1u) {
        return 0;
    }
    return meta_record_crc(r) == r->crc16;
}

static inline uint8_t meta_flags_of(const meta_record_t *r, uint8_t slot)
{
    return (slot == 0u) ? r->flags_a : r->flags_b;
}

static inline void meta_set_flags(meta_record_t *r, uint8_t slot, uint8_t flags)
{
    if (slot == 0u) {
        r->flags_a = flags;
    } else {
        r->flags_b = flags;
    }
}

/* ---- boot decision (pure) ---- */
typedef enum {
    META_ACTION_BOOT_TRIAL = 0,   /* boot active slot, trial: bump attempts */
    META_ACTION_BOOT_NORMAL = 1,  /* boot active slot */
    META_ACTION_ROLLBACK = 2,     /* mark active slot bad, boot other slot */
    META_ACTION_RECOVERY = 3      /* no bootable image: stay in bootloader */
} meta_action_t;

typedef struct {
    meta_action_t action;
    uint8_t target_slot;   /* slot to boot for BOOT_x and ROLLBACK actions */
    uint8_t attempts;      /* attempts value to persist (BOOT_TRIAL only) */
} meta_decision_t;

/*
 * rec:              last valid metadata record (or zeroed defaults)
 * active_valid:     active slot image passes header+payload checks
 * other_valid:      the other slot image passes header+payload checks
 * max_attempts:     trial boot attempts allowed before rollback (>=1)
 */
static inline meta_decision_t meta_boot_decision(const meta_record_t *rec,
                                                 int active_valid, int other_valid,
                                                 uint8_t max_attempts)
{
    meta_decision_t d;
    uint8_t slot = rec->active_slot;
    uint8_t other = (uint8_t)(1u - slot);
    uint8_t flags = meta_flags_of(rec, slot);

    d.target_slot = slot;
    d.attempts = rec->attempts;

    if (!active_valid) {
        if (other_valid) {
            d.action = META_ACTION_ROLLBACK;
            d.target_slot = other;
        } else {
            d.action = META_ACTION_RECOVERY;
        }
        return d;
    }

    if ((flags & META_FLAG_TRIAL) != 0u) {
        uint8_t attempts = (uint8_t)(rec->attempts + 1u);
        if (attempts > max_attempts) {
            /* trial exhausted: mark bad and roll back if possible */
            if (other_valid) {
                d.action = META_ACTION_ROLLBACK;
                d.target_slot = other;
            } else {
                d.action = META_ACTION_RECOVERY;
            }
            return d;
        }
        d.action = META_ACTION_BOOT_TRIAL;
        d.attempts = attempts;
        return d;
    }

    d.action = META_ACTION_BOOT_NORMAL;
    return d;
}

#endif /* XMC_METADATA_H */
