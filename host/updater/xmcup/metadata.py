"""Metadata record and boot decision logic - mirror of common/metadata.h."""
import struct
from .crc import crc16_ccitt

META_MAGIC = 0x4154454D  # 'M','E','T','A'
META_RECORD_SIZE = 16

META_FLAG_VALID = 0x01
META_FLAG_TRIAL = 0x02
META_FLAG_BAD = 0x04

_REC_STRUCT = struct.Struct("<IIBBBBHH")  # 16 bytes

SLOT_STATE_INVALID = 0
SLOT_STATE_VALID = 1
SLOT_STATE_TRIAL = 2
SLOT_STATE_BAD = 3

META_ACTION_BOOT_TRIAL = 0
META_ACTION_BOOT_NORMAL = 1
META_ACTION_ROLLBACK = 2
META_ACTION_RECOVERY = 3


class MetaRecord(object):
    __slots__ = ("magic", "seq", "active_slot", "flags_a", "flags_b",
                 "attempts", "boot_count", "crc16")

    def __init__(self, magic=META_MAGIC, seq=0, active_slot=0, flags_a=0,
                 flags_b=0, attempts=0, boot_count=0, crc16=0):
        self.magic = magic
        self.seq = seq
        self.active_slot = active_slot
        self.flags_a = flags_a
        self.flags_b = flags_b
        self.attempts = attempts
        self.boot_count = boot_count
        self.crc16 = crc16

    def flags_of(self, slot):
        return self.flags_a if slot == 0 else self.flags_b

    def set_flags(self, slot, flags):
        if slot == 0:
            self.flags_a = flags
        else:
            self.flags_b = flags

    def pack(self, with_crc=True):
        raw = _REC_STRUCT.pack(self.magic, self.seq, self.active_slot,
                               self.flags_a, self.flags_b, self.attempts,
                               self.boot_count, self.crc16)
        if with_crc:
            crc = crc16_ccitt(raw[:META_RECORD_SIZE - 2])
            raw = raw[:META_RECORD_SIZE - 2] + struct.pack("<H", crc)
            self.crc16 = crc
        return raw

    @classmethod
    def unpack(cls, raw):
        fields = _REC_STRUCT.unpack(bytes(raw[:META_RECORD_SIZE]))
        return cls(*fields)

    def is_valid(self):
        if self.magic != META_MAGIC or self.active_slot > 1:
            return False
        return crc16_ccitt(self.pack(with_crc=False)
                           [:META_RECORD_SIZE - 2]) == self.crc16

    def slot_state(self, slot):
        flags = self.flags_of(slot)
        if flags & META_FLAG_BAD:
            return SLOT_STATE_BAD
        if flags & META_FLAG_TRIAL:
            return SLOT_STATE_TRIAL
        if flags & META_FLAG_VALID:
            return SLOT_STATE_VALID
        return SLOT_STATE_INVALID

    def __repr__(self):
        return ("MetaRecord(seq=%d, active=%d, A=0x%02X, B=0x%02X, attempts=%d)"
                % (self.seq, self.active_slot, self.flags_a, self.flags_b,
                   self.attempts))


class MetaDecision(object):
    __slots__ = ("action", "target_slot", "attempts")

    def __init__(self, action, target_slot, attempts):
        self.action = action
        self.target_slot = target_slot
        self.attempts = attempts

    def __repr__(self):
        return "MetaDecision(action=%d, target=%d, attempts=%d)" % (
            self.action, self.target_slot, self.attempts)


def meta_boot_decision(rec, active_valid, other_valid, max_attempts):
    """Mirror of meta_boot_decision() in common/metadata.h."""
    slot = rec.active_slot
    other = 1 - slot
    flags = rec.flags_of(slot)

    if not active_valid:
        if other_valid:
            return MetaDecision(META_ACTION_ROLLBACK, other, rec.attempts)
        return MetaDecision(META_ACTION_RECOVERY, slot, rec.attempts)

    if flags & META_FLAG_TRIAL:
        attempts = (rec.attempts + 1) & 0xFF
        if attempts > max_attempts:
            if other_valid:
                return MetaDecision(META_ACTION_ROLLBACK, other, rec.attempts)
            return MetaDecision(META_ACTION_RECOVERY, slot, rec.attempts)
        return MetaDecision(META_ACTION_BOOT_TRIAL, slot, attempts)

    return MetaDecision(META_ACTION_BOOT_NORMAL, slot, rec.attempts)


def parse_log(data):
    """Scan a metadata sector image; return (best_record_or_None, next_free_index).

    Records are 16-byte blocks; a record is valid iff magic+crc match.
    """
    best = None
    next_free = None
    nblocks = len(data) // META_RECORD_SIZE
    for i in range(nblocks):
        block = data[i * META_RECORD_SIZE:(i + 1) * META_RECORD_SIZE]
        if block == b"\xFF" * META_RECORD_SIZE:
            if next_free is None:
                next_free = i
            continue
        rec = MetaRecord.unpack(block)
        if rec.is_valid():
            if best is None or rec.seq >= best.seq:
                best = rec
    if next_free is None:
        next_free = nblocks  # sector full: caller must erase
    return best, next_free
