"""xmcup - XMC 2Go custom bootloader host-side updater library.

Pure-stdlib by default: the serial layer falls back to a ctypes/Win32 COM
backend when pyserial is not installed (see serial_win32.py).
"""
from .crc import crc16_ccitt, crc32_ieee
from .framing import (SOF, CMD_PING, CMD_INFO, CMD_ERASE_SLOT, CMD_WRITE_CHUNK,
                      CMD_VERIFY_SLOT, CMD_SET_ACTIVE_SLOT, CMD_BOOT,
                      CMD_ROLLBACK, encode_frame, FrameParser, Frame)
from .image import (ImageHeader, build_image, parse_image_header,
                    check_image, IMAGE_MAGIC, IMAGE_HEADER_SIZE)
from .metadata import (MetaRecord, meta_boot_decision, SLOT_STATE_INVALID,
                       SLOT_STATE_VALID, SLOT_STATE_TRIAL, SLOT_STATE_BAD)

__all__ = [
    "crc16_ccitt", "crc32_ieee",
    "SOF", "CMD_PING", "CMD_INFO", "CMD_ERASE_SLOT", "CMD_WRITE_CHUNK",
    "CMD_VERIFY_SLOT", "CMD_SET_ACTIVE_SLOT", "CMD_BOOT", "CMD_ROLLBACK",
    "encode_frame", "FrameParser", "Frame",
    "ImageHeader", "build_image", "parse_image_header", "check_image",
    "IMAGE_MAGIC", "IMAGE_HEADER_SIZE",
    "MetaRecord", "meta_boot_decision", "SLOT_STATE_INVALID",
    "SLOT_STATE_VALID", "SLOT_STATE_TRIAL", "SLOT_STATE_BAD",
]
