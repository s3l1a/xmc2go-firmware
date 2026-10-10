"""CRC16 / CRC32 known-answer tests.

Golden anchors are published check values (CRC-16/CCITT-FALSE and CRC-32 IEEE
802.3 catalogs, both over ASCII "123456789"). The same vectors are checked in
C by tests/host_unit/c_vectors.c and cross-compared in test_c_cross_check.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))

from xmcup.crc import crc16_ccitt, crc16_ccitt_update, crc32_ieee, crc32_ieee_update


class TestCrc16(unittest.TestCase):
    def test_check_value_standard(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_empty(self):
        self.assertEqual(crc16_ccitt(b""), 0xFFFF)

    def test_single_bytes(self):
        self.assertEqual(crc16_ccitt(b"\x00"), 0xE1F0)
        self.assertEqual(crc16_ccitt(b"\x01"), 0xF1D1)
        self.assertEqual(crc16_ccitt(b"\x41"), 0xB915)  # 'A'

    def test_frame_body_vector(self):
        # body of a PING request frame: CMD=0x01 SEQ=0x01 LEN=0x0000
        self.assertEqual(crc16_ccitt(b"\x01\x01\x00\x00"), 0xC544)

    def test_incremental_matches_block(self):
        data = bytes(range(64))
        whole = crc16_ccitt(data)
        part = crc16_ccitt_update(0xFFFF, data[:37])
        part = crc16_ccitt_update(part, data[37:])
        self.assertEqual(whole, part)


class TestCrc32(unittest.TestCase):
    def test_check_value_standard(self):
        self.assertEqual(crc32_ieee(b"123456789"), 0xCBF43926)

    def test_empty(self):
        self.assertEqual(crc32_ieee(b""), 0x00000000)

    def test_single_bytes(self):
        self.assertEqual(crc32_ieee(b"\x00"), 0xD202EF8D)
        self.assertEqual(crc32_ieee(b"a"), 0xE8B7BE43)

    def test_incremental_matches_block(self):
        data = bytes(range(100))
        whole = crc32_ieee(data)
        mid = len(data) // 3
        c = crc32_ieee_update(0xFFFFFFFF, data[:mid])
        c = crc32_ieee_update(c, data[mid:])
        self.assertEqual(c ^ 0xFFFFFFFF, whole)

    def test_zero_block_vector(self):
        self.assertEqual(crc32_ieee(b"\x00" * 28), 0x807077E9)


if __name__ == "__main__":
    unittest.main()
