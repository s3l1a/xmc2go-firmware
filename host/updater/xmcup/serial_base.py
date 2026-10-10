"""Serial backend interface. All backends expose the same small API."""

TIMEOUT_DEFAULT = 2.0


class SerialError(Exception):
    pass


class SerialBase(object):
    """Minimal serial port interface used by the protocol client."""

    def __init__(self):
        self.port = None
        self.baudrate = 115200
        self.timeout = TIMEOUT_DEFAULT

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def read(self, size, timeout=None):
        """Return up to `size` bytes (may return fewer on timeout)."""
        raise NotImplementedError

    def write(self, data):
        """Write all bytes; return count written."""
        raise NotImplementedError

    def flush(self):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def format_port_name(port):
    if port.startswith("\\\\.\\") or port.startswith("\\\\.\\"):
        return port
    return "\\\\.\\" + port
