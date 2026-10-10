#!/usr/bin/env python3
"""xmc2go updater CLI - command-line equivalent of the GUI.

Commands:
  list                      list COM ports
  info                      device status
  update <file> [--slot N]  install an image (.img) or raw app (.bin)
  verify [--slot N]         verify a slot's image CRC
  rollback                  switch back to the other slot and reboot
  reboot                    boot the active slot

Options:
  --port COMx     serial port (default: first available)
  --baud N        baud rate (default 115200)
  --slot {0,1}    target slot for update/verify
  --ver X.Y.Z     version to embed when the file is a raw .bin
  --build N       build number for raw .bin
  --no-boot       do not reboot after update
  --hex           log full frame hex dumps
"""
import argparse
import os
import sys
import struct

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "updater"))

from xmcup.transport import open_serial, list_ports
from xmcup.protocol import Client, ProtocolError, DeviceStatus
from xmcup.update import run_update, pick_target_slot, UpdateError, slot_start
from xmcup.image import (build_image, parse_image_header, check_image,
                         ImageError, IMAGE_HEADER_SIZE)
from xmcup.framing import STATUS_NAMES, Frame

STATE_NAMES = {0: "invalid", 1: "valid", 2: "trial", 3: "bad"}


def log(msg):
    print(msg)


def hexdump(data):
    return " ".join("%02X" % b for b in data)


def make_client(args, cancel=None):
    on_log = None
    if args.hex:
        def on_log(m):
            print("  [link] " + m)
    ser = open_serial(args.port, baudrate=args.baud, timeout=2.0)
    ser.open()
    return Client(ser, timeout=2.0, on_log=on_log, cancel=cancel), ser


def cmd_list(args):
    ports = list_ports()
    if not ports:
        print("no COM ports found")
        return 1
    for p in ports:
        mark = ""
        desc = (p.get("description") or "").lower()
        if any(k in desc for k in ("j-link", "xmc", "cdc", "segger")):
            mark = "  <- likely XMC 2Go / J-Link VCP"
        print("%-8s %s%s" % (p["port"], p.get("description") or "(no desc)",
                             mark))
    return 0


def cmd_info(args):
    client, ser = make_client(args)
    try:
        ping = client.ping()
        info = client.info()
        print("bootloader %d.%d.%d  proto v%d" % (info.bl_version + (ping["proto_version"],)))
        print("active slot : %s" % "AB"[info.active_slot])
        print("slot A      : %s  v%d.%d.%d build %d"
              % (STATE_NAMES.get(info.slot_a_state), info.slot_a_version[0],
                 info.slot_a_version[1], info.slot_a_version[2],
                 info.slot_a_version[3]))
        print("slot B      : %s  v%d.%d.%d build %d"
              % (STATE_NAMES.get(info.slot_b_state), info.slot_b_version[0],
                 info.slot_b_version[1], info.slot_b_version[2],
                 info.slot_b_version[3]))
        print("attempts    : %d" % info.boot_attempts)
        print("reset cause : 0x%02X" % info.reset_cause)
        return 0
    except (ProtocolError, DeviceStatus) as exc:
        print("ERROR: %s" % exc)
        return 1
    finally:
        ser.close()


def load_image(args, slot):
    """Return a complete image (header+payload) for `slot`."""
    with open(args.file, "rb") as f:
        data = f.read()
    if args.file.lower().endswith(".img") or (
            len(data) >= 4 and data[:4] == b"XCM1"):
        hdr = parse_image_header(data)
        check_image(data, slot_start(slot), 0x2000, slot)
        print("image OK: v%d.%d.%d build %d, %d bytes"
              % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch,
                 hdr.build_number, len(data)))
        return data, hdr
    ver = tuple(int(x) for x in (args.ver or "0.0.0").split("."))
    ver = (ver + (0, 0, 0))[:3]
    image = build_image(data, slot_start(slot), 0x2000, slot, ver=ver + (0,),
                        build_number=args.build)
    check_image(image, slot_start(slot), 0x2000, slot)
    print("built image from raw bin: v%d.%d.%d build %d, %d bytes"
          % (ver[0], ver[1], ver[2], args.build, len(image)))
    return image, parse_image_header(image)


def cmd_update(args):
    client, ser = make_client(args)
    try:
        info = client.info()
        # Prefer the slot the image is linked for (its header says so).
        probe = open(args.file, "rb").read(4)
        if args.slot is not None:
            slot = args.slot
            print("target slot: %s (chosen)" % "AB"[slot])
        elif probe == b"XCM1":
            hdr = parse_image_header(open(args.file, "rb").read())
            slot = hdr.slot_id
            if slot == info.active_slot:
                print("ERROR: image is for the ACTIVE slot %s; refusing to "
                      "overwrite it (build an image for the other slot)"
                      % "AB"[slot])
                return 1
            print("target slot: %s (from image header)" % "AB"[slot])
        else:
            slot, reason = pick_target_slot(info)
            print("target slot: %s (%s)" % ("AB"[slot], reason))
        image, hdr = load_image(args, slot)

        def progress(frac, msg):
            print("[%3d%%] %s" % (int(frac * 100), msg))

        run_update(client, image, slot, progress=progress,
                   boot=not args.no_boot)
        print("SUCCESS: v%d.%d.%d installed in slot %s (trial)"
              % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch, "AB"[slot]))
        return 0
    except (UpdateError, ProtocolError, DeviceStatus, ImageError) as exc:
        print("ERROR: %s" % exc)
        print("device state unchanged (old slot still active)")
        return 1
    finally:
        ser.close()


def cmd_verify(args):
    client, ser = make_client(args)
    try:
        info = client.info()
        slot = args.slot if args.slot is not None else info.active_slot
        client.verify_slot(slot)
        print("slot %s verified: image CRC OK" % "AB"[slot])
        return 0
    except (ProtocolError, DeviceStatus) as exc:
        print("ERROR: %s" % exc)
        return 1
    finally:
        ser.close()


def cmd_rollback(args):
    client, ser = make_client(args)
    try:
        client.rollback()
        print("rollback requested; device rebooting to the other slot")
        return 0
    except (ProtocolError, DeviceStatus) as exc:
        print("ERROR: %s" % exc)
        return 1
    finally:
        ser.close()


def cmd_reboot(args):
    client, ser = make_client(args)
    try:
        client.boot()
        print("reboot requested")
        return 0
    except (ProtocolError, DeviceStatus) as exc:
        print("ERROR: %s" % exc)
        return 1
    finally:
        ser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("list", "info", "update", "verify",
                                        "rollback", "reboot"))
    ap.add_argument("file", nargs="?", help="image file for 'update'")
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--slot", type=int, choices=(0, 1))
    ap.add_argument("--ver", default=None)
    ap.add_argument("--build", type=int, default=0)
    ap.add_argument("--no-boot", action="store_true")
    ap.add_argument("--hex", action="store_true")
    args = ap.parse_args()

    if args.command == "list":
        return cmd_list(args)
    if not args.port:
        ports = list_ports()
        if not ports:
            print("no COM ports found; use --port")
            return 1
        args.port = ports[0]["port"]
        print("using port %s" % args.port)
    if args.command == "info":
        return cmd_info(args)
    if args.command == "update":
        if not args.file:
            ap.error("update requires a file")
        return cmd_update(args)
    if args.command == "verify":
        return cmd_verify(args)
    if args.command == "rollback":
        return cmd_rollback(args)
    if args.command == "reboot":
        return cmd_reboot(args)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted (device state unchanged)")
        sys.exit(130)
