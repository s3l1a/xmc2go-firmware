#ifndef XMC_CRC32_H
#define XMC_CRC32_H

#include <stdint.h>
#include <stddef.h>

/* CRC-32 IEEE 802.3 (zlib): poly 0xEDB88320 reflected, init 0xFFFFFFFF,
 * xorout 0xFFFFFFFF. Check value for "123456789" is 0xCBF43926. */
uint32_t crc32_ieee(const uint8_t *data, size_t len);
uint32_t crc32_ieee_update(uint32_t crc, const uint8_t *data, size_t len);

#endif
