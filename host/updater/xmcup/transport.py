"""Transport selection: pyserial if available, else the stdlib Win32 backend."""
from .serial_base import SerialBase, SerialError, TIMEOUT_DEFAULT  # noqa: F401
from .serial_pyserial import have_pyserial, PySerialPort


def open_serial(port, baudrate=115200, timeout=TIMEOUT_DEFAULT):
    """Open `port` with the best available backend (pyserial preferred)."""
    if have_pyserial():
        return PySerialPort(port, baudrate=baudrate, timeout=timeout)
    from .serial_win32 import Win32Serial
    return Win32Serial(port, baudrate=baudrate, timeout=timeout)


def list_ports():
    """List ports with best-effort descriptions (works with either backend)."""
    if have_pyserial():
        try:
            from serial.tools import list_ports as _lp
            out = []
            for p in _lp.comports():
                out.append({"port": p.device, "description": p.description or ""})
            return out
        except Exception:
            pass
    from .serial_win32 import list_ports as _win_list
    return _win_list()
