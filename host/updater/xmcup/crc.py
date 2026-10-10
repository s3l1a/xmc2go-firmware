"""CRC implementations matching common/crc16.c and common/crc32.c exactly."""


def crc16_ccitt_update(crc, data):
    """CRC-16/CCITT-FALSE incremental (poly 0x1021, init 0xFFFF)."""
    for byte in data:
        crc ^= (byte & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc16_ccitt(data):
    return crc16_ccitt_update(0xFFFF, data)


def crc32_ieee_update(crc, data):
    """CRC-32 IEEE 802.3 incremental; caller provides init and final xor."""
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc & 0xFFFFFFFF


def crc32_ieee(data):
    return (crc32_ieee_update(0xFFFFFFFF, data) ^ 0xFFFFFFFF) & 0xFFFFFFFF
