"""Fake serial backend for unit tests: pairs with a scripted device model."""
from .serial_base import SerialBase, SerialError


class FakeSerial(SerialBase):
    """In-memory duplex pipe. `device_write` is what the 'device' sends to us;
    `pending` collects what we send to the device."""

    def __init__(self, timeout=1.0):
        super(FakeSerial, self).__init__()
        self.port = "FAKE"
        self.timeout = timeout
        self.rx = bytearray()      # bytes waiting to be read by the host
        self.tx = bytearray()      # bytes the host wrote (device input)
        self.opened = False
        self.fail_after = None     # raise SerialError after N reads (stall test)
        self._reads = 0
        self.on_tx = None          # optional callback(data) -> device reacts

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def device_send(self, data):
        self.rx.extend(data)

    def read(self, size, timeout=None):
        if not self.opened:
            raise SerialError("port not open")
        self._reads += 1
        if self.fail_after is not None and self._reads > self.fail_after:
            raise SerialError("simulated link failure")
        out = bytes(self.rx[:size])
        del self.rx[:len(out)]
        return out

    def write(self, data):
        if not self.opened:
            raise SerialError("port not open")
        data = bytes(data)
        self.tx.extend(data)
        if self.on_tx is not None:
            self.on_tx(data)
        return len(data)

    def pending(self):
        return bytes(self.tx)
