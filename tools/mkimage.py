#!/usr/bin/env python3
"""mkimage.py - prepend the 32-byte image header to a raw application .bin.

Usage:
  python tools/mkimage.py --slot 0 --bin build/app_traffic_A.bin \
      --out dist/app_traffic_A.img --ver 1.0.0 --build 42

The raw .bin must be linked at (slot_start + 0x20); the entry point is read
from its vector table word 1. The resulting .img is what the updater sends.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "host", "updater"))
from xmcup.image import build_image, check_image, ImageError  # noqa: E402

SLOT_STARTS = {0: 0x10003000, 1: 0x10005000}
SLOT_SIZE = 0x2000


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slot", type=int, required=True, choices=(0, 1))
    ap.add_argument("--bin", required=True, help="raw application .bin")
    ap.add_argument("--out", required=True, help="output .img")
    ap.add_argument("--ver", default="0.0.0", help="major.minor.patch")
    ap.add_argument("--build", type=int, default=0)
    args = ap.parse_args()

    ver = tuple(int(x) for x in args.ver.split("."))
    if len(ver) != 3:
        ap.error("--ver must be major.minor.patch")
    ver = ver + (0,)

    with open(args.bin, "rb") as f:
        raw = f.read()

    start = SLOT_STARTS[args.slot]
    try:
        image = build_image(raw, start, SLOT_SIZE, args.slot, ver=ver,
                            build_number=args.build)
        check_image(image, start, SLOT_SIZE, args.slot)
    except ImageError as exc:
        print("mkimage FAILED: %s" % exc, file=sys.stderr)
        return 1

    with open(args.out, "wb") as f:
        f.write(image)
    print("mkimage %s -> %s (%d bytes, v%d.%d.%d build %d)"
          % (args.bin, args.out, len(image), ver[0], ver[1], ver[2],
             args.build))
    return 0


if __name__ == "__main__":
    sys.exit(main())
