#!/usr/bin/env python3
"""HIL: flash app_bad (never reports healthy, never services the watchdog),
confirm the bootloader rolls back to the previous slot after the attempt limit.

PASS criteria:
  - app_bad boots in trial state
  - after CFG_WDT_TRIAL_ATTEMPTS watchdog resets the bootloader rolls back
    (active slot back to the original, app_bad slot marked 'bad')
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import (Bootlink, find_port, report, HilFailure,
                        DIST, STATE_NAMES)

NAME = "test_rollback_bad"


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
        img = os.path.join(DIST, "app_bad_%s.img" % "AB"[target])
        if not os.path.exists(img):
            raise HilFailure("missing %s" % img)

        print("  flashing app_bad into slot %s (original slot %s)"
              % ("AB"[target], "AB"[original]))
        link.update(img, boot=True)

        # two watchdog trials at 5 s each + margins; the bootloader window is
        # ~1-2 s after each reset
        print("  waiting for watchdog trials + rollback (~25 s)...")
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
