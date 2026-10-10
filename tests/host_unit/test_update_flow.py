"""End-to-end update flow tests against a scripted device model.

Covers: happy-path update, abort/cancel keeps the old slot active, stalled
transfer aborts safely, verify failure prevents activation, protection rules
(active slot, out of bounds).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))
sys.path.insert(0, os.path.dirname(__file__))

from xmcup.serial_fake import FakeSerial
from xmcup.protocol import Client, DeviceStatus, ProtocolError
from xmcup.update import (run_update, UpdateCancelled, UpdateError,
                          pick_target_slot)
from xmcup.image import build_image, IMAGE_HEADER_SIZE
from xmcup.framing import (ST_ERR_PROTECTED, ST_ERR_STATE, ST_ERR_VERIFY,
                           CMD_ERASE_SLOT, CMD_WRITE_CHUNK)

from fake_device import FakeDevice, SLOT_SIZE, SLOT_ADDRS


def make_image(slot, size=512, ver=(1, 0, 0), build=1):
    start = SLOT_ADDRS[slot]
    raw = bytearray(b"\xAA" * size)
    raw[0:4] = (0x20003E00).to_bytes(4, "little")       # initial SP
    raw[4:8] = (start + IMAGE_HEADER_SIZE + 1).to_bytes(4, "little")  # reset
    return build_image(bytes(raw), start, SLOT_SIZE, slot, ver=ver,
                       build_number=build)


class FlowHarness(object):
    def __init__(self, **kw):
        self.serial = FakeSerial()
        self.serial.open()
        self.device = FakeDevice(self.serial, **kw)
        self.client = Client(self.serial, timeout=0.5, retries=1,
                             op_timeout=0.5)
        self.progress = []

    def run_update(self, image, slot, **kw):
        kw.setdefault("progress",
                      lambda f, m: self.progress.append((f, m)))
        return run_update(self.client, image, slot, slot_size=SLOT_SIZE, **kw)


class TestHappyPath(unittest.TestCase):
    def test_full_update_activates_other_slot(self):
        h = FlowHarness(active_slot=0)
        image = make_image(slot=1)
        hdr = h.run_update(image, 1, boot=True)
        self.assertEqual(hdr.slot_id, 1)
        self.assertEqual(h.device.active_slot, 1)
        self.assertEqual(h.device.trial_slot, 1)   # marked trial
        self.assertTrue(h.device.booted)
        # old slot untouched
        self.assertEqual(h.device.slots[0][0], 0xFF)
        self.assertGreater(len(h.progress), 3)
        self.assertEqual(h.progress[-1][0], 1.0)

    def test_update_other_direction(self):
        h = FlowHarness(active_slot=1)
        slot, reason = pick_target_slot(h.device)
        self.assertEqual(slot, 0)
        h.run_update(make_image(slot=0), 0)
        self.assertEqual(h.device.active_slot, 0)

    def test_update_can_skip_boot(self):
        h = FlowHarness(active_slot=0)
        h.run_update(make_image(slot=1), 1, boot=False)
        self.assertFalse(h.device.booted)
        self.assertEqual(h.device.active_slot, 1)


class TestSafetyRules(unittest.TestCase):
    def test_erase_active_slot_rejected(self):
        h = FlowHarness(active_slot=0)
        with self.assertRaises(DeviceStatus) as cm:
            h.client.erase_slot(0)
        self.assertEqual(cm.exception.code, ST_ERR_PROTECTED)

    def test_write_active_slot_rejected(self):
        h = FlowHarness(active_slot=1)
        with self.assertRaises(DeviceStatus) as cm:
            h.client.write_chunk(1, 0, b"\x00" * 16)
        self.assertEqual(cm.exception.code, ST_ERR_PROTECTED)

    def test_write_out_of_bounds_rejected(self):
        h = FlowHarness(active_slot=0)
        h.client.erase_slot(1)
        with self.assertRaises(DeviceStatus) as cm:
            h.client.write_chunk(1, SLOT_SIZE, b"\x00" * 16)
        self.assertEqual(cm.exception.code, ST_ERR_PROTECTED)

    def test_set_active_without_verify_refused(self):
        h = FlowHarness(active_slot=0)
        h.client.erase_slot(1)
        h.client.write_chunk(1, 0, b"\x11" * 16)
        with self.assertRaises(DeviceStatus) as cm:
            h.client.set_active_slot(1)
        self.assertEqual(cm.exception.code, ST_ERR_STATE)
        self.assertEqual(h.device.active_slot, 0)  # unchanged

    def test_set_active_refused_when_verify_fails(self):
        h = FlowHarness(active_slot=0)
        h.device.fail_verify = True
        image = make_image(slot=1)
        with self.assertRaises(DeviceStatus) as cm:
            h.run_update(image, 1)
        self.assertEqual(cm.exception.code, ST_ERR_VERIFY)
        self.assertEqual(h.device.active_slot, 0)  # old slot still active
        self.assertIsNone(h.device.trial_slot)

    def test_corrupt_image_rejected_on_host_before_touching_device(self):
        h = FlowHarness(active_slot=0)
        image = bytearray(make_image(slot=1))
        image[-1] ^= 0xFF
        with self.assertRaises(UpdateError):
            h.run_update(bytes(image), 1)
        # device saw no erase/write at all
        self.assertEqual(len(h.serial.pending()), 0)


class TestAbortAndStall(unittest.TestCase):
    def test_cancel_before_start(self):
        h = FlowHarness(active_slot=0)
        with self.assertRaises(UpdateCancelled):
            h.run_update(make_image(slot=1), 1, cancel=lambda: True)
        self.assertEqual(h.device.active_slot, 0)
        self.assertEqual(len(h.serial.pending()), 0)

    def test_cancel_during_write_keeps_old_slot(self):
        h = FlowHarness(active_slot=0)
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 3   # allow erase + first chunks, then abort

        with self.assertRaises(UpdateCancelled) as cm:
            h.run_update(make_image(slot=1, size=4096), 1, cancel=cancel)
        self.assertIn("old slot still active", str(cm.exception))
        self.assertEqual(h.device.active_slot, 0)
        self.assertIsNone(h.device.trial_slot)
        self.assertFalse(h.device.booted)

    def test_stalled_transfer_aborts_and_keeps_old_slot(self):
        h = FlowHarness(active_slot=0)
        h.device.no_response = True   # device stops answering
        with self.assertRaises(ProtocolError):
            h.run_update(make_image(slot=1), 1)
        self.assertEqual(h.device.active_slot, 0)
        self.assertIsNone(h.device.trial_slot)

    def test_flash_error_during_erase_keeps_old_slot(self):
        h = FlowHarness(active_slot=0)
        h.device.flash_errors_injected[(CMD_ERASE_SLOT, 1)] = 0x04  # FLASH
        with self.assertRaises(DeviceStatus):
            h.run_update(make_image(slot=1), 1)
        self.assertEqual(h.device.active_slot, 0)

    def test_flash_error_during_write_keeps_old_slot(self):
        h = FlowHarness(active_slot=0)
        h.device.flash_errors_injected[(CMD_WRITE_CHUNK, 1)] = 0x04
        with self.assertRaises(DeviceStatus):
            h.run_update(make_image(slot=1), 1)
        self.assertEqual(h.device.active_slot, 0)


class TestPingInfo(unittest.TestCase):
    def test_ping(self):
        h = FlowHarness()
        r = h.client.ping()
        self.assertEqual(r["bl_version"], (1, 0, 0))

    def test_info(self):
        h = FlowHarness(active_slot=1)
        info = h.client.info()
        self.assertEqual(info.active_slot, 1)
        self.assertEqual(info.slot_a_state, 0)   # empty
        self.assertEqual(info.slot_b_state, 0)


if __name__ == "__main__":
    unittest.main()
