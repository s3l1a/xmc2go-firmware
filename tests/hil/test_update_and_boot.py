#!/usr/bin/env python3
"""HIL: update the inactive slot with app_traffic, boot it, confirm it reports
healthy and the device is healthy afterwards.

PASS criteria:
  - update + set-active succeeds
  - after boot the app reports healthy (slot state becomes 'valid', attempts 0)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import (Bootlink, find_port, report, prompt, HilFailure,
                        DIST, STATE_NAMES)

NAME = "test_update_and_boot"


def pick_images(target_slot):
    return os.path.join(DIST, "app_traffic_%s.img" % ("AB"[target_slot]))


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    link = Bootlink(port)
    try:
        print("%s: connecting on %s" % (NAME, port))
        link.catch_bootloader(timeout=30.0)
        info = link.info()
        print("  before: " + link.info_str(info))
        target = 1 - info.active_slot
        img = pick_images(target)
        if not os.path.exists(img):
            raise HilFailure("missing %s - run 'python tools/build_fw.py all' "
                             "first" % img)

        print("  updating slot %s from %s" % ("AB"[target],
                                              os.path.basename(img)))
        hdr = link.update(img, boot=True)
        print("  installed v%d.%d.%d build %d"
              % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch, hdr.build_number))

        print("  waiting 5 s for the app self-check + healthy mark...")
        time.sleep(5.0)

        link.try_reset_via_app()
        time.sleep(0.3)
        link.catch_bootloader(timeout=20.0, allow_app_reset=False)
        info = link.info()
        print("  after : " + link.info_str(info))

        if info.active_slot != target:
            return report(NAME, False, "active slot is %s, expected %s"
                          % ("AB"[info.active_slot], "AB"[target]))
        state = STATE_NAMES.get(info.slot_a_state if target == 0
                                else info.slot_b_state)
        if state != "valid":
            return report(NAME, False,
                          "slot %s state is '%s', expected 'valid' (did the "
                          "app report healthy?)" % ("AB"[target], state))
        if info.boot_attempts != 0:
            return report(NAME, False, "boot attempts %d != 0"
                          % info.boot_attempts)
        return report(NAME, True, "slot %s active, healthy, v%d.%d.%d"
                      % ("AB"[target], hdr.ver_major, hdr.ver_minor,
                         hdr.ver_patch))
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
