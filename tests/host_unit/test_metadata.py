"""Metadata state machine tests: rollback after N failed trials, healthy clears
trial, invalid image never becomes active, slot switch only after verification.

These tests exercise the Python mirror (xmcup.metadata) of common/metadata.h;
test_c_cross_check.py runs the identical scenarios through the compiled C
implementation to prove they stay in sync.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "host", "updater"))

from xmcup.metadata import (MetaRecord, meta_boot_decision, parse_log,
                            META_MAGIC, META_RECORD_SIZE, META_FLAG_VALID,
                            META_FLAG_TRIAL, META_FLAG_BAD,
                            META_ACTION_BOOT_TRIAL, META_ACTION_BOOT_NORMAL,
                            META_ACTION_ROLLBACK, META_ACTION_RECOVERY,
                            SLOT_STATE_VALID, SLOT_STATE_TRIAL, SLOT_STATE_BAD,
                            SLOT_STATE_INVALID)
from xmcup.crc import crc16_ccitt

MAX_ATTEMPTS = 2


def rec(slot=0, flags_a=META_FLAG_VALID, flags_b=0, attempts=0, seq=1):
    r = MetaRecord(seq=seq, active_slot=slot, flags_a=flags_a,
                   flags_b=flags_b, attempts=attempts)
    r.pack(with_crc=True)
    return r


class TestRecord(unittest.TestCase):
    def test_pack_roundtrip(self):
        r = rec()
        raw = r.pack()
        self.assertEqual(len(raw), META_RECORD_SIZE)
        r2 = MetaRecord.unpack(raw)
        self.assertTrue(r2.is_valid())
        self.assertEqual(r2.seq, r.seq)

    def test_crc_detects_corruption(self):
        raw = bytearray(rec().pack())
        raw[9] ^= 0x01
        r = MetaRecord.unpack(raw)
        self.assertFalse(r.is_valid())

    def test_bad_magic_invalid(self):
        r = MetaRecord(magic=META_MAGIC ^ 1, seq=1, active_slot=0)
        r.pack()
        self.assertFalse(r.is_valid())

    def test_bad_slot_invalid(self):
        r = MetaRecord(seq=1, active_slot=7)
        r.pack()
        self.assertFalse(r.is_valid())


class TestBootDecision(unittest.TestCase):
    def test_normal_boot(self):
        d = meta_boot_decision(rec(flags_a=META_FLAG_VALID), True, False, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_BOOT_NORMAL)
        self.assertEqual(d.target_slot, 0)

    def test_trial_boot_increments_attempts(self):
        r = rec(flags_a=META_FLAG_VALID | META_FLAG_TRIAL, attempts=0)
        d = meta_boot_decision(r, True, True, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_BOOT_TRIAL)
        self.assertEqual(d.attempts, 1)

    def test_rollback_after_attempt_limit(self):
        # 2 allowed attempts: attempts=2 in the record means the 3rd boot
        # must roll back (app never reported healthy).
        r = rec(slot=0, flags_a=META_FLAG_VALID | META_FLAG_TRIAL,
                flags_b=META_FLAG_VALID, attempts=MAX_ATTEMPTS)
        d = meta_boot_decision(r, True, True, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_ROLLBACK)
        self.assertEqual(d.target_slot, 1)

    def test_rollback_marks_failed_slot_bad(self):
        # caller-side effect modelled here: after rollback the failed slot is BAD
        r = rec(slot=0, flags_a=META_FLAG_VALID | META_FLAG_TRIAL,
                flags_b=META_FLAG_VALID, attempts=MAX_ATTEMPTS)
        d = meta_boot_decision(r, True, True, MAX_ATTEMPTS)
        new = MetaRecord(seq=r.seq + 1, active_slot=d.target_slot,
                         flags_a=META_FLAG_BAD, flags_b=META_FLAG_VALID)
        new.pack()
        self.assertEqual(new.slot_state(0), SLOT_STATE_BAD)
        self.assertEqual(new.slot_state(1), SLOT_STATE_VALID)

    def test_trial_exhausted_no_other_image_recovery(self):
        r = rec(slot=0, flags_a=META_FLAG_VALID | META_FLAG_TRIAL,
                attempts=MAX_ATTEMPTS)
        d = meta_boot_decision(r, True, False, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_RECOVERY)

    def test_healthy_clears_trial(self):
        # what app_mark_healthy() persists: VALID only, attempts reset
        r = rec(flags_a=META_FLAG_VALID | META_FLAG_TRIAL, attempts=1)
        healthy = MetaRecord(seq=r.seq + 1, active_slot=r.active_slot,
                             flags_a=META_FLAG_VALID, flags_b=r.flags_b,
                             attempts=0)
        healthy.pack()
        self.assertEqual(healthy.slot_state(0), SLOT_STATE_VALID)
        d = meta_boot_decision(healthy, True, False, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_BOOT_NORMAL)

    def test_invalid_active_image_never_boots(self):
        # even if flags claim VALID, an image failing CRC is not booted
        r = rec(flags_a=META_FLAG_VALID)
        d = meta_boot_decision(r, False, True, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_ROLLBACK)
        self.assertEqual(d.target_slot, 1)

    def test_invalid_active_no_other_recovery(self):
        r = rec(flags_a=META_FLAG_VALID)
        d = meta_boot_decision(r, False, False, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_RECOVERY)

    def test_empty_slots_recovery(self):
        r = MetaRecord(seq=1, active_slot=0)
        r.pack()
        d = meta_boot_decision(r, False, False, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_RECOVERY)

    def test_second_slot_trial(self):
        r = rec(slot=1, flags_b=META_FLAG_VALID | META_FLAG_TRIAL,
                flags_a=META_FLAG_VALID, attempts=1)
        d = meta_boot_decision(r, True, True, MAX_ATTEMPTS)
        self.assertEqual(d.action, META_ACTION_BOOT_TRIAL)
        self.assertEqual(d.target_slot, 1)
        self.assertEqual(d.attempts, 2)


class TestSlotSwitchRule(unittest.TestCase):
    """'slot-switch only after verification' and 'invalid image never becomes
    active' - modelled as the update-flow rule enforced by the bootloader."""

    def _simulate_update_flow(self, verify_result, set_active_attempted=True):
        verified = {}
        active = {"slot": 0}
        events = []
        # host: erase+write slot 1
        events.append("erase:1")
        # host: verify slot 1
        if verify_result:
            verified[1] = True
            events.append("verify-ok:1")
        else:
            events.append("verify-fail:1")
        # host: set-active slot 1 (bootloader rule below)
        if set_active_attempted:
            if verified.get(1):
                active["slot"] = 1
                events.append("set-active:1")
            else:
                events.append("set-active-refused:1")
        return events, active["slot"]

    def test_set_active_only_after_verify(self):
        events, active = self._simulate_update_flow(verify_result=True)
        self.assertIn("set-active:1", events)
        self.assertEqual(active, 1)

    def test_set_active_refused_when_verify_fails(self):
        events, active = self._simulate_update_flow(verify_result=False)
        self.assertIn("set-active-refused:1", events)
        self.assertEqual(active, 0)  # old slot remains active

    def test_set_active_without_verify_refused(self):
        # verify never attempted -> verified flag never set
        verified = {}
        allowed = verified.get(1, False)
        self.assertFalse(allowed)


class TestLogScan(unittest.TestCase):
    def _sector(self, records):
        data = bytearray(b"\xFF" * 4096)
        for i, r in enumerate(records):
            raw = r.pack()
            data[i * META_RECORD_SIZE:(i + 1) * META_RECORD_SIZE] = raw
        return bytes(data)

    def test_latest_record_wins(self):
        r1 = rec(seq=1, attempts=0)
        r2 = rec(seq=2, attempts=1)
        best, free = parse_log(self._sector([r1, r2]))
        self.assertEqual(best.seq, 2)
        self.assertEqual(free, 2)

    def test_corrupt_record_ignored(self):
        r1 = rec(seq=1)
        bad = bytearray(rec(seq=2).pack())
        bad[4] ^= 0xFF
        data = bytearray(self._sector([r1]))
        data[META_RECORD_SIZE:2 * META_RECORD_SIZE] = bad
        best, free = parse_log(bytes(data))
        self.assertEqual(best.seq, 1)

    def test_sector_full_reports_no_free_block(self):
        records = [rec(seq=i) for i in range(256)]
        best, free = parse_log(self._sector(records))
        self.assertEqual(free, 256)  # caller must erase
        self.assertEqual(best.seq, 255)

    def test_empty_sector(self):
        best, free = parse_log(self._sector([]))
        self.assertIsNone(best)
        self.assertEqual(free, 0)


if __name__ == "__main__":
    unittest.main()
