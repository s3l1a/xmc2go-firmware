#include "crc32.h"

uint32_t crc32_ieee_update(uint32_t crc, const uint8_t *data, size_t len)
{
    size_t i;
    int b;
    for (i = 0; i < len; i++) {
        crc ^= data[i];
        for (b = 0; b < 8; b++) {
            if (crc & 1u) {
                crc = (crc >> 1) ^ 0xEDB88320u;
            } else {
                crc = crc >> 1;
            }
        }
    }
    return crc;
}

uint32_t crc32_ieee(const uint8_t *data, size_t len)
{
    return crc32_ieee_update(0xFFFFFFFFu, data, len) ^ 0xFFFFFFFFu;
}
