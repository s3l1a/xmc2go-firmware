"""Optional pyserial backend - used automatically when pyserial is installed."""
from .serial_base import SerialBase, SerialError, TIMEOUT_DEFAULT


def have_pyserial():
    try:
        import serial  # noqa: F401
        return True
    except ImportError:
        return False


class PySerialPort(SerialBase):
    def __init__(self, port, baudrate=115200, timeout=TIMEOUT_DEFAULT,
                 write_timeout=TIMEOUT_DEFAULT):
        super(PySerialPort, self).__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._ser = None

    def open(self):
        try:
            import serial
        except ImportError:
            raise SerialError("pyserial is not installed")
        try:
            self._ser = serial.Serial(
                port=self.port, baudrate=self.baudrate, timeout=self.timeout,
                write_timeout=self.write_timeout, bytesize=8, parity="N",
                stopbits=1, xonxoff=False, rtscts=False, dsrdtr=False)
        except Exception as exc:
            raise SerialError("open %s: %s" % (self.port, exc))

    def close(self):
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def read(self, size, timeout=None):
        if self._ser is None:
            raise SerialError("port not open")
        if timeout is not None:
            self._ser.timeout = timeout
        return self._ser.read(int(size))

    def write(self, data):
        if self._ser is None:
            raise SerialError("port not open")
        return self._ser.write(bytes(data))

    def flush(self):
        if self._ser is not None:
            self._ser.flush()
