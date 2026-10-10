#!/usr/bin/env python3
"""HIL: malformed WRITE_CHUNK offsets must not escape the inactive slot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import Bootlink, find_port, report, HilFailure
from xmcup.framing import ST_ERR_PROTECTED
from xmcup.protocol import DeviceStatus

NAME = "test_write_bounds"


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    link = Bootlink(port)
    try:
        link.catch_bootloader(timeout=30.0)
        before = link.info()
        target = 1 - before.active_slot

        for offset, size in ((0x2000, 16), (0x1FF0, 32), (0xFFFFFFF0, 32)):
            try:
                link.client.write_chunk(target, offset, b"\xAA" * size)
                raise HilFailure("offset 0x%08X was accepted" % offset)
            except DeviceStatus as exc:
                if exc.code != ST_ERR_PROTECTED:
                    raise HilFailure("offset 0x%08X returned status 0x%02X"
                                     % (offset, exc.code))

        after = link.info()
        if after.active_slot != before.active_slot:
            raise HilFailure("active slot changed during rejected writes")
        link.client.verify_slot(before.active_slot)
        return report(NAME, True,
                      "cross-slot, metadata, and wraparound writes rejected")
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
