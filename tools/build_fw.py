#!/usr/bin/env python3
"""build_fw.py - build the bootloader and app images with arm-none-eabi-gcc.

This mirrors the Makefile exactly and exists for environments without GNU make.
It is the build driver that was actually run during development (see
docs/TEST_REPORT.md). Requirements: arm-none-eabi-gcc on PATH or in ..\\toolchain
(also searched: C:\\xmc2go\\toolchain).

Usage:  python tools/build_fw.py [all|bootloader|apps|images|clean]
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")

CPU = ["-mcpu=cortex-m0", "-mthumb"]
CFLAGS = CPU + ["-std=c11", "-Os", "-g3", "-Wall", "-Wextra",
                "-ffunction-sections", "-fdata-sections",
                "-fno-strict-aliasing", "-Icommon", "-Iboard"]
ASFLAGS = CPU + ["-x", "assembler-with-cpp", "-Icommon", "-Iboard"]
LDFLAGS = CPU + ["-nostartfiles", "-Wl,--gc-sections",
                 "-Wl,--print-memory-usage"]

BOARD_C = ["board/system.c", "board/uart.c", "board/led.c", "board/wdt.c",
           "board/flash.c", "board/meta.c", "board/delay.c"]
BOARD_S = ["board/startup.S"]
COMMON_C = ["common/crc16.c", "common/crc32.c"]
APP_C = ["board/timer.c", "board/app_api.c"]

TARGETS = {
    "bootloader": {
        "src": ["bootloader/main.c", "bootloader/proto.c"] + BOARD_C + BOARD_S + COMMON_C,
        "ld": "board/link_bootloader.ld",
        "with_app": False,
    },
    "app_traffic": {
        "src": ["app_traffic/main.c", "app_traffic/traffic_fsm.c"] + APP_C + BOARD_C + BOARD_S + COMMON_C,
        "ld": None,  # A/B variants
        "with_app": True,
    },
    "app_bad": {
        "src": ["app_bad/main.c"] + APP_C + BOARD_C + BOARD_S + COMMON_C,
        "ld": None,
        "with_app": True,
    },
    "app_crash": {
        "src": ["app_crash/main.c"] + APP_C + BOARD_C + BOARD_S + COMMON_C,
        "ld": None,
        "with_app": True,
    },
}

IMAGE_VERSIONS = {
    "app_traffic": ("1.0.0", 1),
    "app_bad": ("0.0.1", 1),
    "app_crash": ("0.0.2", 1),
}


def find_toolchain():
    candidates = [
        os.environ.get("ARM_GNU", ""),
        os.path.join(ROOT, "toolchain", "bin"),
        r"C:\xmc2go\toolchain\bin",
        "",
    ]
    for c in candidates:
        gcc = os.path.join(c, "arm-none-eabi-gcc.exe") if c else "arm-none-eabi-gcc"
        if c and os.path.exists(gcc):
            return c
        if not c and shutil.which("arm-none-eabi-gcc"):
            return ""
    return None


def tool(tc, name):
    exe = os.path.join(tc, name + ".exe") if tc else name
    return exe


def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        sys.exit(1)


def compile_all(tc, srcs):
    objs = []
    for s in srcs:
        obj = os.path.join(BUILD, os.path.splitext(s)[0].replace("\\", "/") + ".o")
        obj = obj.replace("\\", "/")
        os.makedirs(os.path.dirname(obj), exist_ok=True)
        need = True
        if os.path.exists(obj):
            if os.path.getmtime(obj) > os.path.getmtime(os.path.join(ROOT, s)):
                need = False
        if need:
            cc = tool(tc, "arm-none-eabi-gcc")
            flags = ASFLAGS if s.endswith(".S") else CFLAGS
            run([cc] + flags + ["-c", s, "-o", obj])
        objs.append(obj)
    return objs


def link(tc, name, objs, ld, out_base):
    cc = tool(tc, "arm-none-eabi-gcc")
    elf = out_base + ".elf"
    run([cc] + LDFLAGS + ["-T", ld] + objs + ["-o", elf,
         "-Wl,-Map=" + out_base + ".map"])
    run([tool(tc, "arm-none-eabi-objcopy"), "-O", "binary", elf, out_base + ".bin"])
    run([tool(tc, "arm-none-eabi-size"), elf])


def build_target(tc, name):
    spec = TARGETS[name]
    variants = [("A", "board/link_slotA.ld"), ("B", "board/link_slotB.ld")] \
        if spec["with_app"] else [(None, spec["ld"])]
    objs = compile_all(tc, spec["src"])
    for suffix, ld in variants:
        out = os.path.join(BUILD, name if suffix is None else "%s_%s" % (name, suffix))
        link(tc, name, objs, ld, out)


def make_images(tc):
    os.makedirs(DIST, exist_ok=True)
    for name, (ver, build) in IMAGE_VERSIONS.items():
        for suffix, slot in (("A", 0), ("B", 1)):
            run([sys.executable, os.path.join("tools", "mkimage.py"),
                 "--slot", str(slot),
                 "--bin", os.path.join("build", "%s_%s.bin" % (name, suffix)),
                 "--out", os.path.join("dist", "%s_%s.img" % (name, suffix)),
                 "--ver", ver, "--build", str(build)])


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == "clean":
        shutil.rmtree(BUILD, ignore_errors=True)
        shutil.rmtree(DIST, ignore_errors=True)
        print("cleaned")
        return 0

    tc = find_toolchain()
    if tc is None:
        print("arm-none-eabi-gcc not found. Install it (tools/setup_toolchain.md)"
              " or set ARM_GNU to its bin directory.")
        return 2
    print("toolchain:", tc or "(PATH)")

    if what in ("all", "bootloader"):
        build_target(tc, "bootloader")
        os.makedirs(DIST, exist_ok=True)
        shutil.copy2(os.path.join(BUILD, "bootloader.bin"),
                     os.path.join(DIST, "bootloader.bin"))
    if what in ("all", "apps"):
        for t in ("app_traffic", "app_bad", "app_crash"):
            build_target(tc, t)
    if what in ("all", "images"):
        make_images(tc)
    print("BUILD OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
