"""Image header build/parse tests: valid, bad magic, bad CRC, length too big,
wrong slot id, bad entry point."""
import os
import sys
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))

from xmcup.image import (ImageHeader, build_image, parse_image_header,
                         check_header, check_image, IMAGE_MAGIC,
                         IMAGE_HEADER_SIZE, IMG_ERR_MAGIC, IMG_ERR_FORMAT,
                         IMG_ERR_HEADER_CRC, IMG_ERR_LENGTH, IMG_ERR_PAYLOAD_CRC,
                         IMG_ERR_SLOT_ID, IMG_ERR_ENTRY, ImageError)
from xmcup.crc import crc32_ieee

SLOT_A = 0x10003000
SLOT_B = 0x10005000
SLOT_SIZE = 0x2000


def make_raw_bin(size=256, entry=None):
    """Synthetic app .bin: XMC vector table + filler."""
    if entry is None:
        entry = SLOT_A + IMAGE_HEADER_SIZE + 1  # Thumb address inside slot A
    data = bytearray(b"\xFF" * size)
    struct.pack_into("<I", data, 0, 0x20003E00)   # initial SP (RAM top-ish)
    struct.pack_into("<I", data, 4, entry)        # reset handler
    return bytes(data)


class TestImageHeader(unittest.TestCase):
    def test_build_and_check_valid(self):
        raw = make_raw_bin()
        image = build_image(raw, SLOT_A, SLOT_SIZE, 0, ver=(1, 2, 3, 4),
                            build_number=7)
        hdr = check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(hdr.ver_major, 1)
        self.assertEqual(hdr.ver_minor, 2)
        self.assertEqual(hdr.ver_patch, 3)
        self.assertEqual(hdr.build_number, 7)
        self.assertEqual(hdr.payload_length, len(raw))
        self.assertEqual(len(image), IMAGE_HEADER_SIZE + len(raw))

    def test_header_crc_field(self):
        raw = make_raw_bin()
        image = build_image(raw, SLOT_A, SLOT_SIZE, 0)
        hdr = parse_image_header(image)
        body = image[:IMAGE_HEADER_SIZE - 4]
        self.assertEqual(hdr.header_crc32, crc32_ieee(body))

    def test_bad_magic_rejected(self):
        raw = make_raw_bin()
        image = bytearray(build_image(raw, SLOT_A, SLOT_SIZE, 0))
        image[0] ^= 0xFF
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_MAGIC)

    def test_bad_header_crc_rejected(self):
        raw = make_raw_bin()
        image = bytearray(build_image(raw, SLOT_A, SLOT_SIZE, 0))
        image[8] ^= 0x01  # touch ver_major without fixing header CRC
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_HEADER_CRC)

    def test_bad_payload_crc_rejected(self):
        raw = make_raw_bin()
        image = bytearray(build_image(raw, SLOT_A, SLOT_SIZE, 0))
        image[-1] ^= 0xFF  # corrupt payload, header CRC still fine
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_PAYLOAD_CRC)

    def test_payload_length_too_big_for_slot(self):
        hdr = ImageHeader(slot_id=0, payload_length=SLOT_SIZE,  # == full slot
                          payload_crc32=0, entry_point=SLOT_A + 33)
        hdr.pack(with_crc=True)
        with self.assertRaises(ImageError) as cm:
            check_header(hdr, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_LENGTH)

    def test_wrong_slot_id_rejected(self):
        raw = make_raw_bin()
        image = build_image(raw, SLOT_A, SLOT_SIZE, 0)
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 1)  # claims B, we ask for A
        self.assertEqual(cm.exception.code, IMG_ERR_SLOT_ID)

    def test_entry_point_must_be_in_slot(self):
        raw = make_raw_bin(entry=SLOT_B + 33)  # points into the *other* slot
        with self.assertRaises(ImageError) as cm:
            build_and_check(raw)
        self.assertEqual(cm.exception.code, IMG_ERR_ENTRY)

    def test_entry_point_must_be_thumb(self):
        raw = make_raw_bin(entry=SLOT_A + 32)  # even address -> not Thumb
        with self.assertRaises(ImageError) as cm:
            build_and_check(raw)
        self.assertEqual(cm.exception.code, IMG_ERR_ENTRY)

    def test_entry_point_must_be_inside_payload(self):
        raw = make_raw_bin(entry=SLOT_A + 0x1001)
        with self.assertRaises(ImageError) as cm:
            build_and_check(raw)
        self.assertEqual(cm.exception.code, IMG_ERR_ENTRY)

    def test_stack_pointer_must_be_in_ram_and_aligned(self):
        raw = bytearray(make_raw_bin())
        struct.pack_into("<I", raw, 0, 0x10004000)
        with self.assertRaises(ImageError) as cm:
            build_and_check(raw)
        self.assertEqual(cm.exception.code, IMG_ERR_ENTRY)

    def test_reset_vector_must_match_header(self):
        image = bytearray(build_image(make_raw_bin(), SLOT_A, SLOT_SIZE, 0))
        struct.pack_into("<I", image, IMAGE_HEADER_SIZE + 4, SLOT_A + 0x81)
        payload = bytes(image[IMAGE_HEADER_SIZE:])
        struct.pack_into("<I", image, 20, crc32_ieee(payload))
        struct.pack_into("<I", image, 28, crc32_ieee(bytes(image[:28])))
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_ENTRY)

    def test_format_version_checked(self):
        raw = make_raw_bin()
        image = bytearray(build_image(raw, SLOT_A, SLOT_SIZE, 0))
        struct.pack_into("<H", image, 4, 2)  # format_version = 2
        crc = crc32_ieee(bytes(image[:IMAGE_HEADER_SIZE - 4]))
        struct.pack_into("<I", image, IMAGE_HEADER_SIZE - 4, crc)
        with self.assertRaises(ImageError) as cm:
            check_image(image, SLOT_A, SLOT_SIZE, 0)
        self.assertEqual(cm.exception.code, IMG_ERR_FORMAT)


def build_and_check(raw):
    """build_image + check_image against slot A (raises ImageError)."""
    image = build_image(raw, SLOT_A, SLOT_SIZE, 0)
    return check_image(image, SLOT_A, SLOT_SIZE, 0)


if __name__ == "__main__":
    unittest.main()
