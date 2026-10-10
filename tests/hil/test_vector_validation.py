#!/usr/bin/env python3
"""HIL: device verification must reject invalid application vectors."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import Bootlink, find_port, report, HilFailure, DIST
from xmcup.crc import crc32_ieee
from xmcup.framing import ST_ERR_VERIFY, WRITE_CHUNK_MAX_DATA
from xmcup.protocol import DeviceStatus
from xmcup.update import run_update

NAME = "test_vector_validation"


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    link = Bootlink(port)
    try:
        link.catch_bootloader(timeout=30.0)
        before = link.info()
        target = 1 - before.active_slot
        path = os.path.join(DIST, "app_traffic_%s.img" % "AB"[target])
        with open(path, "rb") as f:
            valid_image = f.read()

        image = bytearray(valid_image)
        struct.pack_into("<I", image, 32, 0x10004000)  # flash, not SRAM
        payload_length = struct.unpack_from("<I", image, 16)[0]
        payload = bytes(image[32:32 + payload_length])
        struct.pack_into("<I", image, 20, crc32_ieee(payload))
        struct.pack_into("<I", image, 28, crc32_ieee(bytes(image[:28])))

        link.client.erase_slot(target)
        padded = bytes(image) + b"\xFF" * ((-len(image)) % 16)
        chunk_size = WRITE_CHUNK_MAX_DATA - (WRITE_CHUNK_MAX_DATA % 16)
        for offset in range(0, len(padded), chunk_size):
            link.client.write_chunk(target, offset,
                                    padded[offset:offset + chunk_size])
        try:
            link.client.verify_slot(target)
            raise HilFailure("device accepted an initial SP outside SRAM")
        except DeviceStatus as exc:
            if exc.code != ST_ERR_VERIFY:
                raise HilFailure("unexpected verify status 0x%02X" % exc.code)

        run_update(link.client, valid_image, target, set_active=False, boot=False)
        after = link.info()
        if after.active_slot != before.active_slot:
            raise HilFailure("active slot changed during vector test")
        return report(NAME, True,
                      "invalid stack pointer rejected; inactive image restored")
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
