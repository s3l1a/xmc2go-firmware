#!/usr/bin/env python3
"""HIL: run app_traffic for several minutes and confirm there is no spurious
watchdog reset (the healthy path must keep running forever).

PASS criteria:
  - exactly one 'app_traffic start' banner during the observation window
  - exactly one 'healthy: trial cleared' line
  - the app still answers the 'S' status command at the end
  - after an 'X' reset: INFO shows slot 'valid' with attempts 0

Usage: python test_watchdog_healthy.py [COMx] [--minutes N]  (default 3)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hil_common import (Bootlink, find_port, report, HilFailure,
                        DIST, STATE_NAMES)

NAME = "test_watchdog_healthy"


def main():
    args = sys.argv[1:]
    port = find_port()
    minutes = 3.0
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--minutes" and i + 1 < len(args):
            minutes = float(args[i + 1])
            i += 2
        else:
            rest.append(args[i])
            i += 1
    if rest:
        port = rest[0]

    link = Bootlink(port)
    try:
        print("%s: connecting on %s (%.0f minute observation)"
              % (NAME, port, minutes))
        link.catch_bootloader(timeout=30.0)
        info = link.info()
        print("  before: " + link.info_str(info))
        target = 1 - info.active_slot
        img = os.path.join(DIST, "app_traffic_%s.img" % "AB"[target])
        if not os.path.exists(img):
            raise HilFailure("missing %s" % img)
        link.update(img, boot=True)
        print("  app_traffic installed in slot %s; observing serial output..."
              % "AB"[target])

        starts = 0
        healthy = 0
        regressions = 0
        last_ts = -1
        deadline = time.monotonic() + minutes * 60.0
        buf = b""
        while time.monotonic() < deadline:
            chunk = link.ser.read(256, timeout=0.5)
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("ascii", "replace").strip()
                    if text:
                        print("    | " + text)
                    if "app_traffic start" in text:
                        starts += 1
                    if "healthy" in text and "trial cleared" in text:
                        healthy += 1
                    # "<ms>: ..." lines: a backwards ms jump = spurious reset
                    if ":" in text:
                        head = text.split(":", 1)[0].strip()
                        if head.isdigit():
                            ts = int(head)
                            if last_ts >= 0 and ts < last_ts:
                                regressions += 1
                                raise HilFailure(
                                    "timestamp regression %d -> %d: spurious "
                                    "reset detected" % (last_ts, ts))
                            last_ts = ts

        # app still responsive?
        link.ser.write(b"S")
        time.sleep(0.5)
        tail = link.ser.read(256, timeout=1.0)
        if not tail:
            raise HilFailure("app did not answer the status command after "
                             "%.0f minutes" % minutes)

        link.try_reset_via_app()
        time.sleep(0.3)
        link.catch_bootloader(timeout=20.0, allow_app_reset=False)
        info = link.info()
        print("  after : " + link.info_str(info))
        state = STATE_NAMES.get(info.slot_a_state if target == 0
                                else info.slot_b_state)

        if starts > 1:
            return report(NAME, False, "%d app starts observed (expected <= 1)"
                          % starts)
        if healthy > 1:
            return report(NAME, False, "%d healthy marks (expected <= 1)"
                          % healthy)
        if state != "valid" or info.boot_attempts != 0:
            return report(NAME, False,
                          "post-run state %s attempts %d (expected valid/0)"
                          % (state, info.boot_attempts))
        return report(NAME, True,
                      "no spurious reset in %.0f min (%d starts, %d healthy "
                      "marks, timestamps monotonic)" % (minutes, starts,
                                                        healthy))
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
