"""Frame encoding/decoding for the bootloader link (docs/PROTOCOL.md).

Frame layout (little-endian):
    SOF(0xA5) | CMD(1) | SEQ(1) | LEN(2 LE) | PAYLOAD(LEN) | CRC16(2 LE)
CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF) computed over CMD..PAYLOAD.
Response frames echo CMD and put a 1-byte status at PAYLOAD[0].
"""
import struct
from .crc import crc16_ccitt

SOF = 0xA5
MAX_PAYLOAD = 128
HEADER_SIZE = 5      # SOF CMD SEQ LEN(2)
CRC_SIZE = 2
MAX_FRAME = HEADER_SIZE + MAX_PAYLOAD + CRC_SIZE

CMD_PING = 0x01
CMD_INFO = 0x02
CMD_ERASE_SLOT = 0x10
CMD_WRITE_CHUNK = 0x11
CMD_VERIFY_SLOT = 0x12
CMD_SET_ACTIVE_SLOT = 0x13
CMD_BOOT = 0x14
CMD_ROLLBACK = 0x15

ST_OK = 0x00
ST_ERR_BAD_CMD = 0x01
ST_ERR_BAD_PARAM = 0x02
ST_ERR_BUSY = 0x03
ST_ERR_FLASH = 0x04
ST_ERR_VERIFY = 0x05
ST_ERR_PROTECTED = 0x06
ST_ERR_STATE = 0x07
ST_ERR_TIMEOUT = 0x08
ST_ERR_INTERNAL = 0x09

STATUS_NAMES = {
    ST_OK: "OK",
    ST_ERR_BAD_CMD: "BAD_CMD",
    ST_ERR_BAD_PARAM: "BAD_PARAM",
    ST_ERR_BUSY: "BUSY",
    ST_ERR_FLASH: "FLASH",
    ST_ERR_VERIFY: "VERIFY",
    ST_ERR_PROTECTED: "PROTECTED",
    ST_ERR_STATE: "STATE",
    ST_ERR_TIMEOUT: "TIMEOUT",
    ST_ERR_INTERNAL: "INTERNAL",
}

WRITE_CHUNK_MAX_DATA = 112


class Frame(object):
    __slots__ = ("cmd", "seq", "payload")

    def __init__(self, cmd, seq, payload=b""):
        self.cmd = cmd
        self.seq = seq
        self.payload = bytes(payload)

    def __eq__(self, other):
        return (isinstance(other, Frame) and self.cmd == other.cmd
                and self.seq == other.seq and self.payload == other.payload)

    def __repr__(self):
        return "Frame(cmd=0x%02X, seq=%d, payload=%r)" % (
            self.cmd, self.seq, self.payload)


def encode_frame(cmd, seq, payload=b""):
    """Encode one frame; raises ValueError on oversized payload."""
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large: %d > %d" % (len(payload), MAX_PAYLOAD))
    body = struct.pack("<BBH", cmd & 0xFF, seq & 0xFF, len(payload)) + payload
    crc = crc16_ccitt(body)
    return bytes([SOF]) + body + struct.pack("<H", crc)


class FrameParser(object):
    """Incremental parser with resync: on bad CRC/oversized length the leading
    SOF byte is dropped and scanning restarts at the next SOF."""

    def __init__(self):
        self._buf = bytearray()
        self.stats = {"frames": 0, "crc_errors": 0, "sof_drops": 0,
                      "oversized": 0, "truncated": 0}

    def feed(self, data):
        """Feed raw bytes; return the list of decoded Frames."""
        self._buf.extend(data)
        frames = []
        while True:
            idx = self._buf.find(bytes([SOF]))
            if idx < 0:
                self.stats["sof_drops"] += len(self._buf)
                del self._buf[:]
                break
            if idx > 0:
                self.stats["sof_drops"] += idx
                del self._buf[:idx]
            if len(self._buf) < HEADER_SIZE:
                self.stats["truncated"] += 1
                break
            length = self._buf[3] | (self._buf[4] << 1)
            if length > MAX_PAYLOAD:
                self.stats["oversized"] += 1
                del self._buf[:1]
                continue
            total = HEADER_SIZE + length + CRC_SIZE
            if len(self._buf) < total:
                self.stats["truncated"] += 1
                break
            body = bytes(self._buf[1:HEADER_SIZE + length])
            (crc_rx,) = struct.unpack(
                "<H", bytes(self._buf[HEADER_SIZE + length:total]))
            if crc16_ccitt(body) != crc_rx:
                self.stats["crc_errors"] += 1
                del self._buf[:1]
                continue
            cmd = self._buf[1]
            seq = self._buf[2]
            payload = bytes(self._buf[HEADER_SIZE:HEADER_SIZE + length])
            frames.append(Frame(cmd, seq, payload))
            self.stats["frames"] += 1
            del self._buf[:total]
        return frames
