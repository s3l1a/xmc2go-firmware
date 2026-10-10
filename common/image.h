/*
 * image.h - application image header, fixed 32 bytes, little-endian.
 * Layout (docs/DESIGN.md):
 *   0x00 u32 magic        = 0x314D4358 ('X','C','M','1' as LE bytes)
 *   0x04 u16 format_ver   = 1
 *   0x06 u16 slot_id      0 = slot A, 1 = slot B
 *   0x08 u8  ver_major
 *   0x09 u8  ver_minor
 *   0x0A u8  ver_patch
 *   0x0B u8  reserved (0)
 *   0x0C u32 build_number
 *   0x10 u32 payload_length  (bytes following the header)
 *   0x14 u32 payload_crc32   (CRC-32 IEEE over payload bytes)
 *   0x18 u32 entry_point     (app reset handler, must equal *(slot+0x24))
 *   0x1C u32 header_crc32    (CRC-32 IEEE over bytes 0x00..0x1B)
 *
 * The raw application binary is linked at (slot_start + 0x20): the XMC1100
 * "user vector table" [initial SP][reset][0][0][CLK_VAL1][CLK_VAL2] lives at
 * the start of the raw binary, i.e. at slot_start + 0x20 in the slot.
 */
#ifndef XMC_IMAGE_H
#define XMC_IMAGE_H

#include <stdint.h>
#include "crc32.h"
#include "config.h"

#define IMAGE_MAGIC 0x314D4358u
#define IMAGE_FORMAT_VERSION 1u
#define IMAGE_HEADER_SIZE 32u
#define IMAGE_VTABLE_OFFSET 32u /* vector table starts right after header */

#define IMG_OK 0
#define IMG_ERR_MAGIC 1
#define IMG_ERR_FORMAT 2
#define IMG_ERR_HEADER_CRC 3
#define IMG_ERR_LENGTH 4
#define IMG_ERR_PAYLOAD_CRC 5
#define IMG_ERR_SLOT_ID 6
#define IMG_ERR_ENTRY 7

typedef struct {
    uint32_t magic;
    uint16_t format_version;
    uint16_t slot_id;
    uint8_t ver_major;
    uint8_t ver_minor;
    uint8_t ver_patch;
    uint8_t reserved;
    uint32_t build_number;
    uint32_t payload_length;
    uint32_t payload_crc32;
    uint32_t entry_point;
    uint32_t header_crc32;
} image_header_t;

_Static_assert(sizeof(image_header_t) == IMAGE_HEADER_SIZE, "image header size");

/* Compute the CRC of a header's first 28 bytes (little-endian layout). */
static inline uint32_t image_header_crc(const image_header_t *h)
{
    return crc32_ieee((const uint8_t *)h, IMAGE_HEADER_SIZE - 4u);
}

/*
 * Validate a header located at `slot_start`. `slot_id` is the slot the header
 * claims to belong to (0 = A, 1 = B). slot_size is the size of the slot.
 * Does not touch the payload CRC.
 */
static inline int image_header_check(const image_header_t *h, uint32_t slot_start,
                                     uint32_t slot_size, uint16_t slot_id)
{
    if (h->magic != IMAGE_MAGIC) {
        return IMG_ERR_MAGIC;
    }
    if (h->format_version != IMAGE_FORMAT_VERSION) {
        return IMG_ERR_FORMAT;
    }
    if (image_header_crc(h) != h->header_crc32) {
        return IMG_ERR_HEADER_CRC;
    }
    if (h->slot_id != slot_id) {
        return IMG_ERR_SLOT_ID;
    }
    if (h->payload_length < 24u ||
        h->payload_length > (slot_size - IMAGE_HEADER_SIZE)) {
        return IMG_ERR_LENGTH;
    }
    /* entry point must be the reset handler inside the slot, Thumb bit set */
    if (h->entry_point < (slot_start + IMAGE_VTABLE_OFFSET) ||
        h->entry_point >= (slot_start + IMAGE_HEADER_SIZE + h->payload_length) ||
        (h->entry_point & 1u) == 0u) {
        return IMG_ERR_ENTRY;
    }
    return IMG_OK;
}

/* Validate the application vector words used during the final handoff. */
static inline int image_vector_check(const image_header_t *h, uint32_t slot_start)
{
    const uint32_t *vt =
        (const uint32_t *)(uintptr_t)(slot_start + IMAGE_VTABLE_OFFSET);
    uint32_t sp = vt[0];
    uint32_t reset = vt[1];

    if (sp < CFG_RAM_START || sp > CFG_RAM_END || (sp & 7u) != 0u) {
        return IMG_ERR_ENTRY;
    }
    if (reset != h->entry_point) {
        return IMG_ERR_ENTRY;
    }
    return IMG_OK;
}

/* Validate the payload CRC of an image whose header is at `slot_start`. */
static inline int image_payload_check(const image_header_t *h, uint32_t slot_start)
{
    const uint8_t *payload =
        (const uint8_t *)(uintptr_t)(slot_start + IMAGE_HEADER_SIZE);
    if (crc32_ieee(payload, h->payload_length) != h->payload_crc32) {
        return IMG_ERR_PAYLOAD_CRC;
    }
    return IMG_OK;
}

#endif /* XMC_IMAGE_H */
