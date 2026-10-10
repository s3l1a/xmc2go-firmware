#!/usr/bin/env python3
"""HIL: power loss / interruption during an update must not damage the
currently active slot.

Automated variant: an update is cancelled in the middle of the write phase
(the same code path a link loss takes) and afterwards:
  - the active slot is unchanged
  - the active slot's image is still valid (verify passes)
  - the old app still boots

Manual power-loss procedure (stronger test, recommended once):
  1. Install app_traffic in slot A (test_update_and_boot).
  2. Start an update of slot B with a large image from the GUI.
  3. While the progress bar is between 10% and 90%, unplug the USB cable
     (cutting both power and the serial link).
  4. Replug, run this script with --check: it must find the old slot still
     active, valid and bootable. Then redo the update to completion.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import (Bootlink, find_port, report, prompt, HilFailure,
                        DIST, STATE_NAMES)

NAME = "test_power_loss_during_update"


def check_old_slot_intact(link, original):
    link.catch_bootloader(timeout=30.0, allow_app_reset=False)
    info = link.info()
    print("  after : " + link.info_str(info))
    if info.active_slot != original:
        raise HilFailure("active slot changed to %s (was %s)"
                         % ("AB"[info.active_slot], "AB"[original]))
    client = link.client
    client.verify_slot(original)   # raises on CRC failure
    state = STATE_NAMES.get(info.slot_a_state if original == 0
                            else info.slot_b_state)
    if state == "bad":
        raise HilFailure("original slot is marked bad")
    return info


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    port = find_port(args[0] if args and not args[0].startswith("--") else None)

    link = Bootlink(port)
    try:
        if check_only:
            print("%s: --check mode" % NAME)
            link.catch_bootloader(timeout=30.0)
            info = link.info()
            # after a manual power loss the original active slot must hold
            check_old_slot_intact(link, info.active_slot)
            return report(NAME, True,
                          "old slot %s intact and bootable"
                          % "AB"[info.active_slot])

        print("%s: connecting on %s" % (NAME, port))
        link.catch_bootloader(timeout=30.0)
        info = link.info()
        print("  before: " + link.info_str(info))
        original = info.active_slot
        target = 1 - original
        img = os.path.join(DIST, "app_traffic_%s.img" % "AB"[target])
        if not os.path.exists(img):
            raise HilFailure("missing %s" % img)

        # start the update but cancel after the first chunks
        with open(img, "rb") as f:
            image = f.read()
        from xmcup.update import run_update, UpdateCancelled
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 4    # let erase + 2 chunks through

        print("  starting update of slot %s and interrupting it..."
              % "AB"[target])
        try:
            run_update(link.client, image, target, slot_size=0x2000,
                       boot=False, cancel=cancel)
            return report(NAME, False, "update completed but was supposed to "
                                       "be interrupted")
        except UpdateCancelled as exc:
            print("  update interrupted: %s" % exc)

        time.sleep(1.0)
        link.ser.close()
        link.ser.open()
        info = check_old_slot_intact(link, original)
        print("  old slot %s is intact; retrying update to completion"
              % "AB"[original])
        link.update(img, boot=True)
        time.sleep(3.0)
        link.try_reset_via_app()
        link.catch_bootloader(timeout=20.0, allow_app_reset=False)
        info = link.info()
        print("  final : " + link.info_str(info))
        return report(NAME, True,
                      "interrupted update left slot %s intact; retry succeeded"
                      % "AB"[original])
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
