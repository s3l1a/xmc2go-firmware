"""High-level update flow: erase inactive slot -> write chunks -> verify ->
set active (trial) -> optional boot.

Safety: the flow only ever touches the *inactive* slot. Cancelling at any
point (or a stalled transfer) leaves the previously active slot untouched.
"""
import struct

from .framing import WRITE_CHUNK_MAX_DATA
from .image import IMAGE_HEADER_SIZE, check_image, ImageError
from .protocol import ProtocolError, Client


class UpdateError(Exception):
    pass


class UpdateCancelled(UpdateError):
    pass


SLOT_SIZE_DEFAULT = 0x2000


def slot_start(slot, slot_size=SLOT_SIZE_DEFAULT):
    if slot == 0:
        return 0x10003000
    if slot == 1:
        return 0x10005000
    raise UpdateError("bad slot %r" % (slot,))


def pick_target_slot(info):
    """Choose the slot to update: never the active one; prefer the invalid or
    the older/other slot. Returns (slot, reason)."""
    if info.active_slot == 0:
        return 1, "active slot is A, updating B"
    return 0, "active slot is B, updating A"


def run_update(client, image, slot, slot_size=SLOT_SIZE_DEFAULT,
               progress=None, verify=True, set_active=True, boot=False,
               cancel=None):
    """Perform a full update of `slot` with `image` (header+payload bytes).

    progress(fraction, message) is called as work proceeds (0.0..1.0).
    Raises UpdateCancelled if `cancel()` returns True (old slot stays active).
    """
    def _cancel_now():
        return bool(cancel and cancel())

    def _report(frac, msg):
        if progress:
            progress(frac, msg)

    if _cancel_now():
        raise UpdateCancelled("before start")

    # Validate on the host before touching the device.
    start = slot_start(slot, slot_size)
    try:
        hdr = check_image(image, start, slot_size, slot)
    except ImageError as exc:
        raise UpdateError("image rejected on host: %s" % exc)

    total = len(image)
    _report(0.0, "image OK: v%d.%d.%d build %d, %d bytes"
            % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch, hdr.build_number,
               total))

    _report(0.02, "erasing slot %s" % "AB"[slot])
    client.erase_slot(slot)

    # Pad to whole flash blocks (16 B) with 0xFF; CRC/length in the header
    # bound the real payload so the padding is harmless.
    data = bytes(image)
    pad = (-len(data)) % 16
    if pad:
        data += b"\xFF" * pad

    chunk = WRITE_CHUNK_MAX_DATA - (WRITE_CHUNK_MAX_DATA % 16)  # 112
    offset = 0
    while offset < len(data):
        if _cancel_now():
            raise UpdateCancelled("during write at offset %d (old slot still "
                                  "active)" % offset)
        block = data[offset:offset + chunk]
        client.write_chunk(slot, offset, block)
        offset += len(block)
        frac = 0.02 + 0.88 * (float(offset) / len(data))
        _report(frac, "wrote %d/%d bytes" % (offset, len(data)))

    if verify:
        if _cancel_now():
            raise UpdateCancelled("before verify")
        _report(0.92, "verifying slot %s" % "AB"[slot])
        client.verify_slot(slot)

    if set_active:
        if _cancel_now():
            raise UpdateCancelled("before set-active (old slot still active)")
        _report(0.96, "setting active slot %s (trial)" % "AB"[slot])
        client.set_active_slot(slot)

    if boot:
        _report(0.99, "rebooting device")
        client.boot()

    _report(1.0, "update complete")
    return hdr


def parse_raw_binary_version(data):
    """No version info in raw .bin files; return a placeholder."""
    return (0, 0, 0, 0)
