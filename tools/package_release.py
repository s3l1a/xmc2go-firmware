#!/usr/bin/env python3
"""Build the end-user release ZIP from verified files in dist/."""
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "v1.0.0"
ARCHIVE_ROOT = "xmc2go-firmware-%s" % VERSION
OUTPUT_DIR = os.path.join(ROOT, "release")
OUTPUT = os.path.join(OUTPUT_DIR, ARCHIVE_ROOT + ".zip")

DIST_FILES = [
    "bootloader.bin",
    "app_traffic_A.img", "app_traffic_B.img",
    "app_bad_A.img", "app_bad_B.img",
    "app_crash_A.img", "app_crash_B.img",
]

PROJECT_FILES = [
    "LICENSE", "README.md", "Start GUI.bat", "XMC 2Go CLI.bat",
    "docs/RELEASE_INSTALL.md", "docs/CAVEATS.md", "docs/PROTOCOL.md",
]


def add_file(zf, source, archive_name):
    zf.write(os.path.join(ROOT, source), ARCHIVE_ROOT + "/" + archive_name)


def main():
    missing = [name for name in DIST_FILES
               if not os.path.isfile(os.path.join(ROOT, "dist", name))]
    if missing:
        print("missing release files: %s" % ", ".join(missing), file=sys.stderr)
        print("run: python tools/build_fw.py all", file=sys.stderr)
        return 1

    build_boot = os.path.join(ROOT, "build", "bootloader.bin")
    dist_boot = os.path.join(ROOT, "dist", "bootloader.bin")
    if not os.path.isfile(build_boot):
        print("missing build/bootloader.bin; run the firmware build first",
              file=sys.stderr)
        return 1
    with open(build_boot, "rb") as f:
        build_hash = hashlib.sha256(f.read()).digest()
    with open(dist_boot, "rb") as f:
        dist_hash = hashlib.sha256(f.read()).digest()
    if build_hash != dist_hash:
        print("dist/bootloader.bin does not match the current build", file=sys.stderr)
        print("run: python tools/build_fw.py all", file=sys.stderr)
        return 1

    checksums = []
    for name in DIST_FILES:
        path = os.path.join(ROOT, "dist", name)
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        checksums.append("%s  dist/%s" % (digest, name))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in PROJECT_FILES:
            add_file(zf, name, name)
        for name in DIST_FILES:
            add_file(zf, "dist/" + name, "dist/" + name)
        for base, dirs, files in os.walk(os.path.join(ROOT, "host")):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    continue
                source = os.path.join(base, name)
                relative = os.path.relpath(source, ROOT).replace("\\", "/")
                zf.write(source, ARCHIVE_ROOT + "/" + relative)
        zf.writestr(ARCHIVE_ROOT + "/SHA256SUMS.txt",
                    "\n".join(checksums) + "\n")

    print(OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
