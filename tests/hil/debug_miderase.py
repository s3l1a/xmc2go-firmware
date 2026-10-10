import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "host", "updater"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from hil_common import Bootlink, find_port

JLINK = r"C:\Program Files\SEGGER\JLink_V984\JLink.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "build", "midpeek.jlink")


def peek(label):
    with open(SCRIPT, "w") as f:
        f.write("si 1\nspeed 4000\ndevice XMC1100-Q024x0032\nconnect\nhalt\n"
                "regs\nmem 0x40050000 4\nmem 0x40050004 4\ng\nexit\n")
    r = subprocess.run([JLINK, "-NoGui", "1", "-ExitOnError", "1",
                        "-CommandFile", SCRIPT],
                       capture_output=True, text=True, timeout=90)
    print("== %s ==" % label)
    pc = ""
    for line in r.stdout.splitlines():
        if line.startswith("PC ="):
            pc = line.strip()
        if " = " in line and line[:8].strip().isalnum() and ":" not in line[:10] and "CONTROL" not in line:
            print("   ", pc, "|", line.strip())


port = sys.argv[1] if len(sys.argv) > 1 else find_port()
link = Bootlink(port)
try:
    link.catch_bootloader(timeout=30.0)
    t = threading.Thread(target=lambda: link.client.erase_slot(1),
                         daemon=True)
    t.start()
    time.sleep(0.15)
    peek("mid-erase")
    t.join()
    print("erase returned")
finally:
    link.close()
