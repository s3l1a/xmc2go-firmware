"""Frame encode/decode tests: round trip, bad CRC, bad SOF, truncation,
oversized payload, resync after garbage."""
import os
import sys
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))

from xmcup.framing import (Frame, FrameParser, encode_frame, SOF, MAX_PAYLOAD,
                           CMD_PING, CMD_INFO, CMD_WRITE_CHUNK)
from xmcup.crc import crc16_ccitt


class TestEncode(unittest.TestCase):
    def test_roundtrip_empty_payload(self):
        raw = encode_frame(CMD_PING, 1, b"")
        self.assertEqual(raw[0], SOF)
        p = FrameParser()
        frames = p.feed(raw)
        self.assertEqual(frames, [Frame(CMD_PING, 1, b"")])

    def test_roundtrip_with_payload(self):
        payload = bytes(range(100))
        raw = encode_frame(CMD_WRITE_CHUNK, 0xA5, payload)
        p = FrameParser()
        frames = p.feed(raw)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, payload)
        self.assertEqual(frames[0].seq, 0xA5)

    def test_oversized_payload_rejected(self):
        with self.assertRaises(ValueError):
            encode_frame(CMD_INFO, 0, b"x" * (MAX_PAYLOAD + 1))

    def test_crc_covers_body_only(self):
        raw = encode_frame(CMD_PING, 7, b"\x01\x02")
        body = raw[1:-2]
        self.assertEqual(struct.unpack("<H", raw[-2:])[0], crc16_ccitt(body))

    def test_known_frame_bytes(self):
        # exact bytes for PING seq=1 (docs/PROTOCOL.md test vector 1)
        raw = encode_frame(CMD_PING, 1, b"")
        self.assertEqual(raw.hex(), "a50101000044c5")


class TestDecode(unittest.TestCase):
    def test_bad_crc_dropped_and_resync(self):
        good = encode_frame(CMD_INFO, 2, b"\x11\x22")
        bad = bytearray(good)
        bad[-1] ^= 0xFF  # corrupt CRC
        p = FrameParser()
        frames = p.feed(bytes(bad) + good)
        self.assertEqual(len(frames), 1)           # only the good one
        self.assertEqual(frames[0].seq, 2)
        self.assertEqual(p.stats["crc_errors"], 1)

    def test_bad_sof_hunted(self):
        good = encode_frame(CMD_PING, 3, b"")
        noise = bytes([0x00, 0x13, 0x37, SOF - 1, 0xFF])
        p = FrameParser()
        frames = p.feed(noise + good)
        self.assertEqual(frames, [Frame(CMD_PING, 3, b"")])
        self.assertGreaterEqual(p.stats["sof_drops"], len(noise))

    def test_truncated_then_completed(self):
        raw = encode_frame(CMD_INFO, 4, b"\xAA" * 20)
        p = FrameParser()
        self.assertEqual(p.feed(raw[:5]), [])      # header only
        self.assertEqual(p.feed(raw[5:10]), [])    # partial payload
        frames = p.feed(raw[10:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, b"\xAA" * 20)

    def test_oversized_length_resyncs(self):
        # LEN field larger than MAX_PAYLOAD must not stall the parser
        bogus = bytes([SOF, CMD_INFO, 9]) + struct.pack("<H", 5000) + b"\x00" * 8
        good = encode_frame(CMD_PING, 5, b"")
        p = FrameParser()
        frames = p.feed(bogus + good)
        self.assertEqual(frames, [Frame(CMD_PING, 5, b"")])
        self.assertEqual(p.stats["oversized"], 1)

    def test_back_to_back_frames(self):
        raw = (encode_frame(CMD_PING, 1, b"")
               + encode_frame(CMD_INFO, 2, b"\x01")
               + encode_frame(CMD_INFO, 3, b"\x02"))
        p = FrameParser()
        frames = p.feed(raw)
        self.assertEqual([f.seq for f in frames], [1, 2, 3])

    def test_garbage_between_frames(self):
        raw = (encode_frame(CMD_PING, 1, b"") + b"\x00\x01\x02"
               + encode_frame(CMD_PING, 2, b""))
        p = FrameParser()
        frames = p.feed(raw)
        self.assertEqual([f.seq for f in frames], [1, 2])

    def test_crc_body_scope_is_cmd_to_payload(self):
        # changing SEQ must change the CRC; SOF must not be included
        raw1 = encode_frame(CMD_PING, 1, b"")
        raw2 = encode_frame(CMD_PING, 2, b"")
        self.assertNotEqual(raw1[-2:], raw2[-2:])


if __name__ == "__main__":
    unittest.main()
