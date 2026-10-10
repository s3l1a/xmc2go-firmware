#!/usr/bin/env python3
"""HIL: flash app_crash (HardFault before healthy), confirm rollback to the
previous slot after the attempt limit.

PASS criteria:
  - app_crash boots in trial state and faults
  - watchdog resets; after CFG_WDT_TRIAL_ATTEMPTS the bootloader rolls back
    (active slot back to the original, crash slot marked 'bad')
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import (Bootlink, find_port, report, HilFailure,
                        DIST, STATE_NAMES)

NAME = "test_rollback_crash"


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    link = Bootlink(port)
    try:
        print("%s: connecting on %s" % (NAME, port))
        link.catch_bootloader(timeout=30.0)
        info = link.info()
        print("  before: " + link.info_str(info))
        original = info.active_slot
        target = 1 - original
        img = os.path.join(DIST, "app_crash_%s.img" % "AB"[target])
        if not os.path.exists(img):
            raise HilFailure("missing %s" % img)

        print("  flashing app_crash into slot %s (original slot %s)"
              % ("AB"[target], "AB"[original]))
        link.update(img, boot=True)

        print("  waiting for crash + watchdog trials + rollback (~25 s)...")
        time.sleep(25.0)

        link.catch_bootloader(timeout=30.0, allow_app_reset=False)
        info = link.info()
        print("  after : " + link.info_str(info))

        bad_state = STATE_NAMES.get(info.slot_a_state if target == 0
                                    else info.slot_b_state)
        if info.active_slot != original:
            return report(NAME, False,
                          "active slot %s, expected rollback to %s"
                          % ("AB"[info.active_slot], "AB"[original]))
        if bad_state != "bad":
            return report(NAME, False,
                          "slot %s state '%s', expected 'bad'"
                          % ("AB"[target], bad_state))
        return report(NAME, True,
                      "rollback worked: slot %s bad, active %s"
                      % ("AB"[target], "AB"[original]))
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
