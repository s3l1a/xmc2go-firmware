import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "host", "updater"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from hil_common import Bootlink, find_port

JLINK = r"C:\Program Files\SEGGER\JLink_V984\JLink.exe"


def jlink_mem(addr, n):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "build", "peek.jlink")
    with open(script, "w") as f:
        f.write("si 1\nspeed 4000\ndevice XMC1100-Q024x0032\nconnect\n"
                "halt\nmem 0x%X %d\ng\nexit\n" % (addr, n))
    r = subprocess.run([JLINK, "-NoGui", "1", "-ExitOnError", "1",
                        "-CommandFile", script],
                       capture_output=True, text=True, timeout=90)
    for line in r.stdout.splitlines():
        if " = " in line and line[:8].strip().isalnum() and ":" not in line[:10] and "CONTROL" not in line:
            return line.split("=", 1)[1].strip()
    return "(no data)"


def jlink_multi(addrs):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "build", "peek.jlink")
    with open(script, "w") as f:
        f.write("si 1\nspeed 4000\ndevice XMC1100-Q024x0032\nconnect\nhalt\n")
        for a, n in addrs:
            f.write("mem 0x%X %d\n" % (a, n))
        f.write("g\nexit\n")
    r = subprocess.run([JLINK, "-NoGui", "1", "-ExitOnError", "1",
                        "-CommandFile", script],
                       capture_output=True, text=True, timeout=90)
    out = []
    for line in r.stdout.splitlines():
        if " = " in line and line[:8].strip().isalnum() and ":" not in line[:10] and "CONTROL" not in line:
            out.append(line.strip())
    return out


port = sys.argv[1] if len(sys.argv) > 1 else find_port()
link = Bootlink(port)
try:
    link.catch_bootloader(timeout=30.0)
    print("before erase:", jlink_mem(0x10005000, 16))
    print("erasing slot 1 ...")
    link.client.erase_slot(1)
    print("erase cmd OK")
    for line in jlink_multi([(0x10005000, 16), (0x10005100, 16),
                             (0x40050000, 4), (0x40050004, 4),
                             (0x40050008, 4)]):
        print("   ", line)
finally:
    link.close()
