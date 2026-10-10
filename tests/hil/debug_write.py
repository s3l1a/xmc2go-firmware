import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "host", "updater"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from hil_common import Bootlink, find_port, HilFailure
from xmcup.protocol import DeviceStatus

port = sys.argv[1] if len(sys.argv) > 1 else find_port()
link = Bootlink(port)
try:
    link.catch_bootloader(timeout=30.0)
    print("erasing slot 1 ...")
    link.client.erase_slot(1)
    print("erase OK")
    print("writing chunk 0 ...")
    data = b"\xAA" * 112
    link.client.write_chunk(1, 0, data)
    print("chunk 0 OK")
    print("writing chunk 1 ...")
    link.client.write_chunk(1, 112, b"\xBB" * 112)
    print("chunk 1 OK")
except DeviceStatus as exc:
    print("DEVICE STATUS ERROR:", exc)
except Exception as exc:
    print("ERROR:", exc)
finally:
    link.close()
