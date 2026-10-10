/*
 * c_vectors.c - runs the same known-answer vectors and metadata boot-decision
 * scenarios as the Python tests, directly against the C sources in common/.
 * Built and run by run_c_vectors.bat (MSVC) or `make host-test-c` (gcc).
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "crc16.h"
#include "crc32.h"
#include "metadata.h"
#include "image.h"
#include "flash.h"
#include "config.h"

static int failures = 0;

static void check_u32(const char *name, uint32_t got, uint32_t want)
{
    if (got != want) {
        printf("FAIL %s: got 0x%08X want 0x%08X\n", name, got, want);
        failures++;
    } else {
        printf("ok   %s\n", name);
    }
}

static void check_int(const char *name, int got, int want)
{
    if (got != want) {
        printf("FAIL %s: got %d want %d\n", name, got, want);
        failures++;
    } else {
        printf("ok   %s\n", name);
    }
}

static void crc_vectors(void)
{
    static const uint8_t z1[1] = { 0x00 };
    static const uint8_t one[1] = { 0x01 };
    static const uint8_t A_[1] = { 0x41 };
    static const uint8_t body[4] = { 0x01, 0x01, 0x00, 0x00 };
    uint8_t zeros28[28];

    memset(zeros28, 0, sizeof(zeros28));

    check_u32("crc16(\"123456789\")", crc16_ccitt((const uint8_t *)"123456789", 9), 0x29B1u);
    check_u32("crc16(\"\")", crc16_ccitt((const uint8_t *)"", 0), 0xFFFFu);
    check_u32("crc16(0x00)", crc16_ccitt(z1, 1), 0xE1F0u);
    check_u32("crc16(0x01)", crc16_ccitt(one, 1), 0xF1D1u);
    check_u32("crc16('A')", crc16_ccitt(A_, 1), 0xB915u);
    check_u32("crc16(ping body)", crc16_ccitt(body, 4), 0xC544u);

    check_u32("crc32(\"123456789\")", crc32_ieee((const uint8_t *)"123456789", 9), 0xCBF43926u);
    check_u32("crc32(\"\")", crc32_ieee((const uint8_t *)"", 0), 0x00000000u);
    check_u32("crc32(0x00)", crc32_ieee(z1, 1), 0xD202EF8Du);
    check_u32("crc32(\"a\")", crc32_ieee((const uint8_t *)"a", 1), 0xE8B7BE43u);
    check_u32("crc32(zeros28)", crc32_ieee(zeros28, 28), 0x807077E9u);
}

static void metadata_vectors(void)
{
    meta_record_t r;
    meta_decision_t d;

    check_int("sizeof(meta_record_t)", (int)sizeof(meta_record_t), 16);
    check_int("sizeof(image_header_t)", (int)sizeof(image_header_t), 32);

    /* normal boot */
    memset(&r, 0, sizeof(r));
    r.magic = META_MAGIC; r.seq = 1; r.active_slot = 0;
    r.flags_a = META_FLAG_VALID;
    d = meta_boot_decision(&r, 1, 0, 2);
    check_int("normal_boot.action", (int)d.action, (int)META_ACTION_BOOT_NORMAL);
    check_int("normal_boot.slot", (int)d.target_slot, 0);

    /* trial boot increments attempts */
    r.flags_a = META_FLAG_VALID | META_FLAG_TRIAL;
    r.attempts = 0;
    d = meta_boot_decision(&r, 1, 1, 2);
    check_int("trial_boot.action", (int)d.action, (int)META_ACTION_BOOT_TRIAL);
    check_int("trial_boot.attempts", (int)d.attempts, 1);

    /* rollback after attempt limit */
    r.attempts = 2;   /* 3rd boot with limit 2 */
    r.flags_b = META_FLAG_VALID;
    d = meta_boot_decision(&r, 1, 1, 2);
    check_int("rollback.action", (int)d.action, (int)META_ACTION_ROLLBACK);
    check_int("rollback.slot", (int)d.target_slot, 1);

    /* trial exhausted, no other image -> recovery */
    r.flags_b = 0;
    d = meta_boot_decision(&r, 1, 0, 2);
    check_int("exhausted.action", (int)d.action, (int)META_ACTION_RECOVERY);

    /* invalid active image rolls back even when flags say valid */
    r.attempts = 0;
    r.flags_a = META_FLAG_VALID;
    r.flags_b = META_FLAG_VALID;
    d = meta_boot_decision(&r, 0, 1, 2);
    check_int("invalid_active.action", (int)d.action, (int)META_ACTION_ROLLBACK);
    check_int("invalid_active.slot", (int)d.target_slot, 1);

    /* both images invalid -> recovery */
    d = meta_boot_decision(&r, 0, 0, 2);
    check_int("both_invalid.action", (int)d.action, (int)META_ACTION_RECOVERY);

    /* healthy record: trial cleared -> normal boot */
    r.flags_a = META_FLAG_VALID;   /* healthy() cleared TRIAL */
    d = meta_boot_decision(&r, 1, 0, 2);
    check_int("healthy.action", (int)d.action, (int)META_ACTION_BOOT_NORMAL);

    /* record CRC round-trip */
    r.seq = 7; r.attempts = 3;
    r.crc16 = meta_record_crc(&r);
    check_int("record_valid", meta_record_valid(&r), 1);
    r.attempts = 4;   /* corrupt without fixing CRC */
    check_int("record_corrupt_detected", meta_record_valid(&r), 0);
}

static void image_vectors(void)
{
    image_header_t h;
    uint8_t payload[64];
    uint32_t slot = CFG_SLOT_A_START;
    int i;

    for (i = 0; i < (int)sizeof(payload); i++) {
        payload[i] = (uint8_t)i;
    }

    memset(&h, 0, sizeof(h));
    h.magic = IMAGE_MAGIC;
    h.format_version = IMAGE_FORMAT_VERSION;
    h.slot_id = 0;
    h.ver_major = 1; h.ver_minor = 2; h.ver_patch = 3;
    h.build_number = 7;
    h.payload_length = sizeof(payload);
    h.payload_crc32 = crc32_ieee(payload, sizeof(payload));
    h.entry_point = slot + IMAGE_VTABLE_OFFSET + 1;  /* Thumb */
    h.header_crc32 = image_header_crc(&h);

    check_int("header_valid", image_header_check(&h, slot, CFG_SLOT_SIZE, 0), IMG_OK);
    check_int("header_wrong_slot", image_header_check(&h, slot, CFG_SLOT_SIZE, 1), IMG_ERR_SLOT_ID);
    h.magic = 0;
    check_int("header_bad_magic", image_header_check(&h, slot, CFG_SLOT_SIZE, 0), IMG_ERR_MAGIC);
    h.magic = IMAGE_MAGIC;
    h.header_crc32 ^= 1u;
    check_int("header_bad_crc", image_header_check(&h, slot, CFG_SLOT_SIZE, 0), IMG_ERR_HEADER_CRC);
}

static void flash_range_vectors(void)
{
    /* bootloader region and CS0 must be locked out; slots and metadata ok */
    check_int("range: bootloader start",
              flash_range_is_writable(CFG_BOOT_START, 16), FLASH_ERR_RANGE);
    check_int("range: bootloader end",
              flash_range_is_writable(CFG_BOOT_START + CFG_BOOT_SIZE - 16, 16),
              FLASH_ERR_RANGE);
    check_int("range: config sector CS0 (BMI)",
              flash_range_is_writable(0x10000E00u, 16), FLASH_ERR_RANGE);
    check_int("range: cross boot->slotA",
              flash_range_is_writable(CFG_BOOT_START + CFG_BOOT_SIZE - 8, 16),
              FLASH_ERR_RANGE);
    check_int("range: slot A block",
              flash_range_is_writable(CFG_SLOT_A_START, 16), FLASH_OK);
    check_int("range: slot B page",
              flash_range_is_writable(CFG_SLOT_B_START, 256), FLASH_OK);
    check_int("range: metadata block",
              flash_range_is_writable(CFG_META_START, 16), FLASH_OK);
    check_int("range: slot A overflow into B",
              flash_range_is_writable(CFG_SLOT_B_START - 16, 32),
              FLASH_ERR_RANGE);
    check_int("range: metadata backup block",
              flash_range_is_writable(CFG_META_BACKUP_START, 16), FLASH_OK);
    check_int("range: zero length",
              flash_range_is_writable(CFG_SLOT_A_START, 0), FLASH_ERR_RANGE);
    check_int("range: full slot A",
              flash_range_is_writable(CFG_SLOT_A_START, CFG_SLOT_SIZE),
              FLASH_OK);
}

int main(void)
{
    printf("== C known-answer vectors ==\n");
    crc_vectors();
    metadata_vectors();
    image_vectors();
    flash_range_vectors();
    if (failures == 0) {
        printf("ALL C VECTORS PASS\n");
        return 0;
    }
    printf("%d C VECTOR FAILURES\n", failures);
    return 1;
}
