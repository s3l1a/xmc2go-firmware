"""Stdlib-only Windows serial backend (ctypes against the Win32 COM API).

Implements CreateFileW / SetCommState / GetCommState / SetCommTimeouts /
ReadFile / WriteFile / CloseHandle and enumerates ports through the registry
key HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM. Used when pyserial is not installed.
"""
import ctypes
import time
from ctypes import wintypes

from .serial_base import SerialBase, SerialError

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
MAXDWORD = 0xFFFFFFFF

NOPARITY = 0
ONESTOPBIT = 0
DTR_CONTROL_ENABLE = 1
RTS_CONTROL_ENABLE = 1

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

# Handles are pointer-sized: type every handle-taking API or ctypes truncates
# them to 32 bits (breaks with handles above 4 GB).
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                  wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
for _fn, _sig in (
        ("CloseHandle", [wintypes.HANDLE]),
        ("ReadFile", [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]),
        ("WriteFile", [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                       ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]),
        ("GetCommState", [wintypes.HANDLE, ctypes.c_void_p]),
        ("SetCommState", [wintypes.HANDLE, ctypes.c_void_p]),
        ("SetCommTimeouts", [wintypes.HANDLE, ctypes.c_void_p]),
        ("PurgeComm", [wintypes.HANDLE, wintypes.DWORD]),
        ("FlushFileBuffers", [wintypes.HANDLE])):
    _f = getattr(_kernel32, _fn)
    _f.argtypes = _sig
    _f.restype = wintypes.BOOL

INVALID_HANDLE = wintypes.HANDLE(-1).value


class DCB(ctypes.Structure):
    _fields_ = [
        ("DCBlength", wintypes.DWORD),
        ("BaudRate", wintypes.DWORD),
        ("Flags", wintypes.DWORD),  # packed bitfield (see _set_flags)
        ("wReserved", wintypes.WORD),
        ("XonLim", wintypes.WORD),
        ("XoffLim", wintypes.WORD),
        ("ByteSize", ctypes.c_ubyte),
        ("Parity", ctypes.c_ubyte),
        ("StopBits", ctypes.c_ubyte),
        ("XonChar", ctypes.c_char),
        ("XoffChar", ctypes.c_char),
        ("ErrorChar", ctypes.c_char),
        ("EofChar", ctypes.c_char),
        ("EvtChar", ctypes.c_char),
        ("wReserved1", wintypes.WORD),
    ]


class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [
        ("ReadIntervalTimeout", wintypes.DWORD),
        ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
        ("ReadTotalTimeoutConstant", wintypes.DWORD),
        ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
        ("WriteTotalTimeoutConstant", wintypes.DWORD),
    ]


class COMSTAT(ctypes.Structure):
    _fields_ = [
        ("fCtsHold", wintypes.DWORD, 1),
        ("fDsrHold", wintypes.DWORD, 1),
        ("fRlsdHold", wintypes.DWORD, 1),
        ("fXoffHold", wintypes.DWORD, 1),
        ("fXoffSent", wintypes.DWORD, 1),
        ("fEof", wintypes.DWORD, 1),
        ("fTxim", wintypes.DWORD, 1),
        ("fReserved", wintypes.DWORD, 25),
        ("cbInQue", wintypes.DWORD),
        ("cbOutQue", wintypes.DWORD),
    ]


def _set_flags(dcb, binary=1, parity=0, outx=0, inx=0, dtr=0, rts=0):
    """Pack the DCB bitfield DWORD (layout documented in winbase.h)."""
    flags = 0
    flags |= (binary & 1) << 0
    flags |= (parity & 1) << 1
    flags |= (dtr & 3) << 4
    flags |= (1) << 6          # fDsrSensitivity = 1 (standard for VCP)
    flags |= (1) << 7          # fTXContinueOnXoff = 1
    flags |= (outx & 1) << 8
    flags |= (inx & 1) << 9
    flags |= (rts & 3) << 12
    dcb.Flags = flags


def _err(name):
    raise SerialError("%s failed: %s" % (name, ctypes.FormatError(ctypes.get_last_error())))


def list_ports():
    """Enumerate COM ports via HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM.

    Returns a list of dicts: {"port": "COM3", "description": "..."}; the
    description is best-effort from the USB enum keys (may be empty).
    """
    import winreg
    ports = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DEVICEMAP\SERIALCOMM")
    except OSError:
        return ports
    try:
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if isinstance(value, str) and value.upper().startswith("COM"):
                ports.append({"port": value, "description": ""})
    finally:
        winreg.CloseKey(key)

    descs = _usb_descriptions()
    for p in ports:
        p["description"] = descs.get(p["port"].upper(), "")
    return ports


def _usb_descriptions():
    """Best-effort map of COM name -> USB device description."""
    import winreg
    descs = {}
    base = r"SYSTEM\CurrentControlSet\Enum\USB"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return descs
    try:
        i = 0
        while True:
            try:
                dev = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                dkey = winreg.OpenKey(root, dev)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    inst = winreg.EnumKey(dkey, j)
                except OSError:
                    break
                j += 1
                port = ""
                desc = ""
                try:
                    ik = winreg.OpenKey(dkey, inst)
                    try:
                        desc, _ = winreg.QueryValueEx(ik, "DeviceDesc")
                    except OSError:
                        desc = ""
                    try:
                        pk = winreg.OpenKey(ik, r"Device Parameters")
                        try:
                            port, _ = winreg.QueryValueEx(pk, "PortName")
                        finally:
                            winreg.CloseKey(pk)
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(ik)
                except OSError:
                    continue
                if port:
                    descs[port.upper()] = desc or dev
            winreg.CloseKey(dkey)
    finally:
        winreg.CloseKey(root)
    return descs


class Win32Serial(SerialBase):
    def __init__(self, port, baudrate=115200, timeout=2.0, write_timeout=2.0):
        super(Win32Serial, self).__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._handle = None

    def open(self):
        name = self.port
        if not name.startswith("\\\\.\\"):
            name = "\\\\.\\" + name
        handle = _kernel32.CreateFileW(
            name, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
        if not handle or handle == INVALID_HANDLE:
            _err("CreateFileW(%s)" % self.port)
        self._handle = handle

        dcb = DCB()
        dcb.DCBlength = ctypes.sizeof(DCB)
        if not _kernel32.GetCommState(handle, ctypes.byref(dcb)):
            self.close()
            _err("GetCommState")
        dcb.BaudRate = int(self.baudrate)
        dcb.ByteSize = 8
        dcb.Parity = NOPARITY
        dcb.StopBits = ONESTOPBIT
        _set_flags(dcb, binary=1, parity=0, outx=0, inx=0,
                   dtr=DTR_CONTROL_ENABLE, rts=RTS_CONTROL_ENABLE)
        if not _kernel32.SetCommState(handle, ctypes.byref(dcb)):
            self.close()
            _err("SetCommState")

        timeouts = COMMTIMEOUTS()
        # Return from ReadFile as soon as data is available or the constant
        # timeout expires (MAXDWORD/0/constant pattern).
        timeouts.ReadIntervalTimeout = MAXDWORD
        timeouts.ReadTotalTimeoutMultiplier = 0
        timeouts.ReadTotalTimeoutConstant = int(max(self.timeout, 0.001) * 1000)
        timeouts.WriteTotalTimeoutMultiplier = 0
        timeouts.WriteTotalTimeoutConstant = int(max(self.write_timeout, 0.001) * 1000)
        if not _kernel32.SetCommTimeouts(handle, ctypes.byref(timeouts)):
            self.close()
            _err("SetCommTimeouts")
        _kernel32.PurgeComm(handle, 0x0004 | 0x0008)  # PURGE_RXCLEAR|PURGE_TXCLEAR

    def close(self):
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def read(self, size, timeout=None):
        if self._handle is None:
            raise SerialError("port not open")
        if timeout is not None and abs(timeout - self.timeout) > 1e-9:
            timeouts = COMMTIMEOUTS()
            timeouts.ReadIntervalTimeout = MAXDWORD
            timeouts.ReadTotalTimeoutMultiplier = 0
            timeouts.ReadTotalTimeoutConstant = int(max(timeout, 0.001) * 1000)
            timeouts.WriteTotalTimeoutMultiplier = 0
            timeouts.WriteTotalTimeoutConstant = int(max(self.write_timeout, 0.001) * 1000)
            _kernel32.SetCommTimeouts(self._handle, ctypes.byref(timeouts))
            self.timeout = timeout
        buf = ctypes.create_string_buffer(int(size))
        read = wintypes.DWORD(0)
        ok = _kernel32.ReadFile(self._handle, buf, int(size),
                                ctypes.byref(read), None)
        if not ok:
            _err("ReadFile")
        return buf.raw[:read.value]

    def write(self, data):
        if self._handle is None:
            raise SerialError("port not open")
        data = bytes(data)
        written = wintypes.DWORD(0)
        total = 0
        view = data
        while total < len(view):
            ok = _kernel32.WriteFile(self._handle, view[total:],
                                     len(view) - total, ctypes.byref(written), None)
            if not ok:
                _err("WriteFile")
            if written.value == 0:
                raise SerialError("WriteFile wrote 0 bytes (timeout?)")
            total += written.value
        return total

    def flush(self):
        if self._handle is not None:
            _kernel32.FlushFileBuffers(self._handle)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False
