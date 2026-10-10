"""Shared helpers for the hardware-in-the-loop tests.

These tests require a real XMC 2Go board on a COM port. They report
PASS/FAIL with a reason and exit 0/1.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "host", "updater"))

from xmcup.transport import open_serial, list_ports
from xmcup.protocol import Client, ProtocolError, DeviceStatus
from xmcup.update import run_update, pick_target_slot, slot_start
from xmcup.image import parse_image_header, check_image, ImageError

STATE_NAMES = {0: "invalid", 1: "valid", 2: "trial", 3: "bad"}

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "dist")


class HilFailure(Exception):
    pass


def find_port(preferred=None):
    if preferred:
        return preferred
    ports = list_ports()
    if not ports:
        raise HilFailure("no COM ports found (is the board connected?)")
    for p in ports:
        desc = (p.get("description") or "").lower()
        if any(k in desc for k in ("j-link", "xmc", "cdc", "segger")):
            return p["port"]
    return ports[0]["port"]


def report(name, ok, reason):
    print("%s: %s - %s" % (name, "PASS" if ok else "FAIL", reason))
    return 0 if ok else 1


class Bootlink(object):
    """Connection that can 'catch' the bootloader's post-reset window."""

    def __init__(self, port, baud=115200):
        self.port = port
        self.ser = open_serial(port, baudrate=baud, timeout=0.2)
        self.ser.open()
        self.client = Client(self.ser, timeout=0.4, retries=1, op_timeout=8.0)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def ping_quiet(self):
        try:
            return self.client.ping()
        except Exception:
            return None

    def try_reset_via_app(self):
        """app_traffic answers 'X' with a reset into the bootloader window."""
        try:
            self.ser.write(b"X")
            time.sleep(0.05)
        except Exception:
            pass

    def catch_bootloader(self, timeout=30.0, allow_app_reset=True):
        """Hammer PING until the bootloader answers (1-2 s window after each
        reset). Returns the PING response dict or raises HilFailure."""
        deadline = time.monotonic() + timeout
        sent_reset = False
        while time.monotonic() < deadline:
            r = self.ping_quiet()
            if r is not None:
                return r
            if allow_app_reset and not sent_reset and time.monotonic() > deadline - timeout + 2.0:
                self.try_reset_via_app()
                sent_reset = True
            time.sleep(0.05)
        raise HilFailure("no bootloader response within %.0f s "
                         "(press the board RESET button while the test is "
                         "running, then re-run)" % timeout)

    def info(self):
        return self.client.info()

    def info_str(self, info):
        return ("active=%s A=%s v%d.%d.%d b%d  B=%s v%d.%d.%d b%d  attempts=%d"
                % ("AB"[info.active_slot],
                   STATE_NAMES.get(info.slot_a_state), info.slot_a_version[0],
                   info.slot_a_version[1], info.slot_a_version[2],
                   info.slot_a_version[3],
                   STATE_NAMES.get(info.slot_b_state), info.slot_b_version[0],
                   info.slot_b_version[1], info.slot_b_version[2],
                   info.slot_b_version[3], info.boot_attempts))

    def update(self, img_path, boot=True):
        with open(img_path, "rb") as f:
            image = f.read()
        hdr = parse_image_header(image)
        slot = hdr.slot_id
        check_image(image, slot_start(slot), 0x2000, slot)
        run_update(self.client, image, slot, boot=boot,
                   progress=lambda f, m: print("   [%3d%%] %s"
                                               % (int(f * 100), m)))
        return hdr

    def wait_state(self, predicate, timeout=30.0, poll=0.2):
        """Poll INFO through bootloader windows until predicate(info) or
        timeout. Returns (info, ok)."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                self.catch_bootloader(timeout=min(3.0, deadline - time.monotonic()),
                                      allow_app_reset=False)
                info = self.info()
                last = info
                if predicate(info):
                    return info, True
            except (HilFailure, ProtocolError, DeviceStatus):
                pass
            time.sleep(poll)
        return last, False


def prompt(msg):
    print(msg)
    try:
        input("Press Enter when ready (Ctrl-C to abort)...")
    except KeyboardInterrupt:
        raise HilFailure("aborted by user")
