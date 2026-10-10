#ifndef XMC_CRC16_H
#define XMC_CRC16_H

#include <stdint.h>
#include <stddef.h>

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, refin=false, refout=false,
 * xorout=0x0000. Check value for "123456789" is 0x29B1. */
uint16_t crc16_ccitt(const uint8_t *data, size_t len);
uint16_t crc16_ccitt_update(uint16_t crc, const uint8_t *data, size_t len);

#endif
