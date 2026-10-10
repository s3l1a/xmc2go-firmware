"""A scripted bootloader model speaking the wire protocol over FakeSerial.

Used by test_update_flow.py to exercise the host update flow end-to-end
without hardware. The model enforces the same safety rules as the bootloader:
- refuse to erase/write the active slot
- refuse writes outside slot bounds
- SET_ACTIVE_SLOT only after a successful VERIFY_SLOT in this session
"""
import os
import sys
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))

from xmcup.framing import (Frame, FrameParser, encode_frame,
                           CMD_PING, CMD_INFO, CMD_ERASE_SLOT, CMD_WRITE_CHUNK,
                           CMD_VERIFY_SLOT, CMD_SET_ACTIVE_SLOT, CMD_BOOT,
                           CMD_ROLLBACK, ST_OK, ST_ERR_BAD_CMD,
                           ST_ERR_BAD_PARAM, ST_ERR_FLASH, ST_ERR_VERIFY,
                           ST_ERR_PROTECTED, ST_ERR_STATE)
from xmcup.crc import crc32_ieee
from xmcup.image import (IMAGE_MAGIC, IMAGE_HEADER_SIZE, parse_image_header,
                         check_image, ImageError)

SLOT_ADDRS = {0: 0x10003000, 1: 0x10005000}
SLOT_SIZE = 0x2000


class FakeDevice(object):
    def __init__(self, serial, active_slot=0, initial_images=None):
        self.serial = serial
        self.parser = FrameParser()
        self.active_slot = active_slot
        self.slots = {0: bytearray(b"\xFF" * SLOT_SIZE),
                      1: bytearray(b"\xFF" * SLOT_SIZE)}
        if initial_images:
            for slot, img in initial_images.items():
                self.slots[slot][:len(img)] = img
        self.verified = {}
        self.trial_slot = None
        self.booted = False
        self.rolled_back = False
        self.flash_errors_injected = {}   # (cmd, slot) -> status
        self.fail_verify = False
        self.no_response = False             # simulate a stalled link
        serial.on_tx = self._on_tx

    # -- device internals --
    def _respond(self, cmd, seq, status, extra=b""):
        if self.no_response:
            return
        self.serial.device_send(encode_frame(cmd, seq, bytes([status]) + extra))

    def _on_tx(self, data):
        for frame in self.parser.feed(data):
            self._handle(frame)

    def _handle(self, frame):
        cmd, seq, payload = frame.cmd, frame.seq, frame.payload
        if cmd == CMD_PING:
            self._respond(cmd, seq, ST_OK,
                          bytes([1, 1, 0, 0]))  # proto, bl 1.0.0
        elif cmd == CMD_INFO:
            self._respond(cmd, seq, ST_OK, self._info_payload())
        elif cmd == CMD_ERASE_SLOT:
            self._erase(frame, seq, payload)
        elif cmd == CMD_WRITE_CHUNK:
            self._write_chunk(frame, seq, payload)
        elif cmd == CMD_VERIFY_SLOT:
            self._verify(frame, seq, payload)
        elif cmd == CMD_SET_ACTIVE_SLOT:
            self._set_active(frame, seq, payload)
        elif cmd == CMD_BOOT:
            self.booted = True
            self._respond(cmd, seq, ST_OK)
        elif cmd == CMD_ROLLBACK:
            self.rolled_back = True
            self._respond(cmd, seq, ST_OK)
        else:
            self._respond(cmd, seq, ST_ERR_BAD_CMD)

    def _info_payload(self):
        out = bytearray(26)                  # payload after status byte
        out[0] = 1                           # proto version
        out[1], out[2], out[3] = 1, 0, 0     # bl version
        out[4] = self.active_slot
        out[5] = self._slot_state(0)
        out[6] = self._slot_state(1)
        out[7] = 0                           # attempts
        out[8] = 0x01                        # reset cause: power-on
        out[9] = 0                           # flags
        out[10], out[11], out[12] = 1, 0, 0  # slot A version
        out[14] = self._slot_build(0) & 0xFF
        out[18], out[19], out[20] = 1, 0, 0  # slot B version
        out[22] = self._slot_build(1) & 0xFF
        return bytes(out)

    def _slot_build(self, slot):
        img = self.slots[slot]
        if img[0] == 0xFF:
            return 0
        return struct.unpack("<I", bytes(img[12:16]))[0]

    def _slot_state(self, slot):
        img = self.slots[slot]
        if img[0] == 0xFF:
            return 0                    # invalid/empty
        return 1                        # valid (simplified)

    def _erase(self, frame, seq, payload):
        if len(payload) != 1:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        slot = payload[0]
        if slot not in self.slots:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        if slot == self.active_slot:
            self._respond(frame.cmd, seq, ST_ERR_PROTECTED)
            return
        err = self.flash_errors_injected.get((frame.cmd, slot))
        if err is not None:
            self._respond(frame.cmd, seq, err)
            return
        self.slots[slot] = bytearray(b"\xFF" * SLOT_SIZE)
        self.verified.pop(slot, None)
        self._respond(frame.cmd, seq, ST_OK)

    def _write_chunk(self, frame, seq, payload):
        if len(payload) < 1 + 4 + 16:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        slot = payload[0]
        (offset,) = struct.unpack("<I", bytes(payload[1:5]))
        data = bytes(payload[5:])
        if slot not in self.slots:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        if slot == self.active_slot:
            self._respond(frame.cmd, seq, ST_ERR_PROTECTED)
            return
        if offset % 16 or len(data) % 16 or len(data) == 0:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        if offset + len(data) > SLOT_SIZE:
            self._respond(frame.cmd, seq, ST_ERR_PROTECTED)
            return
        err = self.flash_errors_injected.get((frame.cmd, slot))
        if err is not None:
            self._respond(frame.cmd, seq, err)
            return
        self.slots[slot][offset:offset + len(data)] = data
        self.verified.pop(slot, None)   # image changed: must re-verify
        self._respond(frame.cmd, seq, ST_OK)

    def _verify(self, frame, seq, payload):
        if len(payload) != 1:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        slot = payload[0]
        if slot not in self.slots:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        if self.fail_verify:
            self._respond(frame.cmd, seq, ST_ERR_VERIFY)
            return
        img = bytes(self.slots[slot])
        try:
            check_image(img, SLOT_ADDRS[slot], SLOT_SIZE, slot)
        except ImageError:
            self._respond(frame.cmd, seq, ST_ERR_VERIFY)
            return
        self.verified[slot] = True
        self._respond(frame.cmd, seq, ST_OK)

    def _set_active(self, frame, seq, payload):
        if len(payload) != 1:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        slot = payload[0]
        if slot not in self.slots:
            self._respond(frame.cmd, seq, ST_ERR_BAD_PARAM)
            return
        if not self.verified.get(slot):
            # rule: slot-switch only after successful verification
            self._respond(frame.cmd, seq, ST_ERR_STATE)
            return
        self.active_slot = slot
        self.trial_slot = slot
        self._respond(frame.cmd, seq, ST_OK)
