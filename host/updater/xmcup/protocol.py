"""Request/response client for the bootloader protocol.

All I/O happens through a SerialBase-compatible object, so the same client
drives the Win32 backend, pyserial, or the fake backend in unit tests.
"""
import struct
import time

from .crc import crc16_ccitt  # noqa: F401  (kept for symmetry with C side)
from .framing import (Frame, FrameParser, encode_frame, MAX_PAYLOAD,
                      CMD_PING, CMD_INFO, CMD_ERASE_SLOT, CMD_WRITE_CHUNK,
                      CMD_VERIFY_SLOT, CMD_SET_ACTIVE_SLOT, CMD_BOOT,
                      CMD_ROLLBACK, ST_OK, STATUS_NAMES, WRITE_CHUNK_MAX_DATA)

PROTO_VERSION = 1


class ProtocolError(Exception):
    pass


class DeviceStatus(ProtocolError):
    def __init__(self, code, cmd):
        self.code = code
        self.cmd = cmd
        super(DeviceStatus, self).__init__(
            "command 0x%02X failed: %s (0x%02X)"
            % (cmd, STATUS_NAMES.get(code, "UNKNOWN"), code))


class LinkTimeout(ProtocolError):
    pass


class Info(object):
    """Parsed INFO response (layout mirrors common/protocol.h)."""
    __slots__ = ("proto_version", "bl_version", "active_slot", "slot_a_state",
                 "slot_b_state", "boot_attempts", "reset_cause", "flags",
                 "slot_a_version", "slot_b_version")

    def __init__(self, payload):
        if len(payload) < 27:
            raise ProtocolError("INFO response too short: %d" % len(payload))
        b = bytes(payload)
        self.proto_version = b[1]
        self.bl_version = (b[2], b[3], b[4])
        self.active_slot = b[5]
        self.slot_a_state = b[6]
        self.slot_b_state = b[7]
        self.boot_attempts = b[8]
        self.reset_cause = b[9]
        self.flags = b[10]
        self.slot_a_version = (b[11], b[12], b[13],
                               struct.unpack("<I", b[15:19])[0])
        self.slot_b_version = (b[19], b[20], b[21],
                               struct.unpack("<I", b[23:27])[0])

    def __repr__(self):
        return ("Info(bl=%d.%d.%d, active=%d, A=%d, B=%d, attempts=%d, rst=0x%02X)"
                % (self.bl_version + (self.active_slot, self.slot_a_state,
                                      self.slot_b_state, self.boot_attempts,
                                      self.reset_cause)))


class Client(object):
    def __init__(self, serial, timeout=2.0, on_log=None, cancel=None,
                 retries=2, op_timeout=8.0):
        self.serial = serial
        self.timeout = timeout
        self.op_timeout = op_timeout   # flash ops (erase/write/verify) can be slow
        self.retries = retries
        self._parser = FrameParser()
        self._seq = 0
        self.on_log = on_log       # callable(str)
        self.cancel = cancel       # callable() -> bool (True = abort)

    # ---- low level ----
    def _log(self, msg):
        if self.on_log:
            self.on_log(msg)

    def _cancelled(self):
        return bool(self.cancel and self.cancel())

    def _next_seq(self):
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def transact(self, cmd, payload=b"", timeout=None, retries=None):
        """Send one request frame and wait for the matching response."""
        deadline_budget = self.timeout if timeout is None else timeout
        if retries is None:
            retries = self.retries
        last_err = None
        for _ in range(max(1, retries)):
            if self._cancelled():
                raise ProtocolError("cancelled")
            seq = self._next_seq()
            frame = encode_frame(cmd, seq, payload)
            self._log("TX cmd=0x%02X seq=%d len=%d" % (cmd, seq, len(payload)))
            self.serial.write(frame)
            resp = self._wait_response(cmd, seq, deadline_budget)
            if resp is not None:
                return resp
            last_err = LinkTimeout("no response to cmd 0x%02X (seq %d)" % (cmd, seq))
            self._log("  timeout, retrying")
        raise last_err

    def _wait_response(self, cmd, seq, budget):
        deadline = time.monotonic() + budget
        while True:
            if self._cancelled():
                raise ProtocolError("cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            data = self.serial.read(256, timeout=min(remaining, 0.2))
            if data:
                for frame in self._parser.feed(data):
                    if frame.cmd == cmd and frame.seq == seq:
                        self._log("RX cmd=0x%02X seq=%d len=%d"
                                  % (frame.cmd, frame.seq, len(frame.payload)))
                        return frame
                    self._log("RX unexpected frame cmd=0x%02X seq=%d (ignored)"
                              % (frame.cmd, frame.seq))
            else:
                time.sleep(0.005)

    def _check_status(self, frame):
        if not frame.payload:
            raise ProtocolError("empty response payload")
        status = frame.payload[0]
        if status != ST_OK:
            raise DeviceStatus(status, frame.cmd)
        return frame.payload

    # ---- commands ----
    def ping(self):
        payload = self._check_status(self.transact(CMD_PING))
        if len(payload) < 5:
            raise ProtocolError("PING response too short")
        return {"proto_version": payload[1],
                "bl_version": (payload[2], payload[3], payload[4])}

    def info(self):
        payload = self._check_status(self.transact(CMD_INFO))
        return Info(payload)

    def erase_slot(self, slot):
        self._check_status(self.transact(CMD_ERASE_SLOT, bytes([slot & 0xFF]),
                                        timeout=self.op_timeout))

    def write_chunk(self, slot, offset, data):
        data = bytes(data)
        if len(data) == 0 or len(data) > WRITE_CHUNK_MAX_DATA:
            raise ProtocolError("bad chunk size %d" % len(data))
        if len(data) % 16 != 0:
            raise ProtocolError("chunk size must be a multiple of 16")
        if offset % 16 != 0:
            raise ProtocolError("chunk offset must be 16-byte aligned")
        payload = bytes([slot & 0xFF]) + struct.pack("<I", offset) + data
        self._check_status(self.transact(CMD_WRITE_CHUNK, payload, timeout=self.op_timeout))

    def verify_slot(self, slot):
        self._check_status(self.transact(CMD_VERIFY_SLOT, bytes([slot & 0xFF]),
                                        timeout=self.op_timeout))

    def set_active_slot(self, slot):
        self._check_status(self.transact(CMD_SET_ACTIVE_SLOT,
                                        bytes([slot & 0xFF]), timeout=self.op_timeout))

    def boot(self):
        self._check_status(self.transact(CMD_BOOT, timeout=self.op_timeout))

    def rollback(self):
        self._check_status(self.transact(CMD_ROLLBACK, timeout=self.op_timeout))
