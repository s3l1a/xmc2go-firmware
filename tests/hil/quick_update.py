import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "host", "updater"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from hil_common import Bootlink, find_port, report, HilFailure, DIST

NAME = "quick_update"


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    img = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        DIST, "app_traffic_A.img")
    link = Bootlink(port)
    try:
        print("%s: port %s, image %s" % (NAME, port, os.path.basename(img)))
        link.catch_bootloader(timeout=30.0)
        info = link.info()
        print("  before: " + link.info_str(info))
        hdr = link.update(img, boot=True)
        print("  installed v%d.%d.%d in slot %d"
              % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch, hdr.slot_id))
        time.sleep(4.0)
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 6.0:
            d = link.ser.read(256, timeout=0.3)
            if d:
                buf += d
        print("  app output:\n" + buf.decode("ascii", "replace"))
        return report(NAME, True, "update + boot OK")
    except (HilFailure, Exception) as exc:
        return report(NAME, False, str(exc))
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
