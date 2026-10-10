"""Application image header (32 bytes, little-endian) - mirror of common/image.h."""
import struct
from .crc import crc32_ieee

IMAGE_MAGIC = 0x314D4358  # 'X','M','C','1' as little-endian word
IMAGE_FORMAT_VERSION = 1
IMAGE_HEADER_SIZE = 32
IMAGE_VTABLE_OFFSET = 32

_HDR_STRUCT = struct.Struct("<IHHBBBBIIIII")  # 32 bytes

IMG_OK = 0
IMG_ERR_MAGIC = 1
IMG_ERR_FORMAT = 2
IMG_ERR_HEADER_CRC = 3
IMG_ERR_LENGTH = 4
IMG_ERR_PAYLOAD_CRC = 5
IMG_ERR_SLOT_ID = 6
IMG_ERR_ENTRY = 7

_ERROR_NAMES = {
    IMG_OK: "OK",
    IMG_ERR_MAGIC: "bad magic",
    IMG_ERR_FORMAT: "unsupported format version",
    IMG_ERR_HEADER_CRC: "header CRC mismatch",
    IMG_ERR_LENGTH: "payload length out of range",
    IMG_ERR_PAYLOAD_CRC: "payload CRC mismatch",
    IMG_ERR_SLOT_ID: "wrong slot id",
    IMG_ERR_ENTRY: "entry point out of range",
}


class ImageError(Exception):
    def __init__(self, code, detail=""):
        self.code = code
        super(ImageError, self).__init__(
            _ERROR_NAMES.get(code, "error %d" % code) +
            (": " + detail if detail else ""))


class ImageHeader(object):
    __slots__ = ("magic", "format_version", "slot_id", "ver_major", "ver_minor",
                 "ver_patch", "reserved", "build_number", "payload_length",
                 "payload_crc32", "entry_point", "header_crc32")

    def __init__(self, magic=IMAGE_MAGIC, format_version=IMAGE_FORMAT_VERSION,
                 slot_id=0, ver_major=0, ver_minor=0, ver_patch=0, reserved=0,
                 build_number=0, payload_length=0, payload_crc32=0,
                 entry_point=0, header_crc32=0):
        self.magic = magic
        self.format_version = format_version
        self.slot_id = slot_id
        self.ver_major = ver_major
        self.ver_minor = ver_minor
        self.ver_patch = ver_patch
        self.reserved = reserved
        self.build_number = build_number
        self.payload_length = payload_length
        self.payload_crc32 = payload_crc32
        self.entry_point = entry_point
        self.header_crc32 = header_crc32

    @property
    def version_tuple(self):
        return (self.ver_major, self.ver_minor, self.ver_patch, self.build_number)

    def pack(self, with_crc=True):
        raw = _HDR_STRUCT.pack(
            self.magic, self.format_version, self.slot_id,
            self.ver_major, self.ver_minor, self.ver_patch, self.reserved,
            self.build_number, self.payload_length, self.payload_crc32,
            self.entry_point, self.header_crc32)
        if with_crc:
            crc = crc32_ieee(raw[:IMAGE_HEADER_SIZE - 4])
            raw = raw[:IMAGE_HEADER_SIZE - 4] + struct.pack("<I", crc)
            self.header_crc32 = crc
        return raw

    @classmethod
    def unpack(cls, raw):
        if len(raw) < IMAGE_HEADER_SIZE:
            raise ImageError(IMG_ERR_HEADER_CRC, "header truncated")
        fields = _HDR_STRUCT.unpack(bytes(raw[:IMAGE_HEADER_SIZE]))
        return cls(*fields)

    def __repr__(self):
        return ("ImageHeader(slot=%d, v=%d.%d.%d+%d, len=%d, entry=0x%08X)"
                % (self.slot_id, self.ver_major, self.ver_minor, self.ver_patch,
                   self.build_number, self.payload_length, self.entry_point))


def parse_image_header(raw):
    return ImageHeader.unpack(raw)


def check_header(hdr, slot_start, slot_size, slot_id):
    """Mirror of image_header_check() in common/image.h. Raises ImageError."""
    if hdr.magic != IMAGE_MAGIC:
        raise ImageError(IMG_ERR_MAGIC)
    if hdr.format_version != IMAGE_FORMAT_VERSION:
        raise ImageError(IMG_ERR_FORMAT)
    if crc32_ieee(hdr.pack(with_crc=False)[:IMAGE_HEADER_SIZE - 4]) != hdr.header_crc32:
        raise ImageError(IMG_ERR_HEADER_CRC)
    if hdr.slot_id != slot_id:
        raise ImageError(IMG_ERR_SLOT_ID, "header says slot %d" % hdr.slot_id)
    if hdr.payload_length < 24 or hdr.payload_length > slot_size - IMAGE_HEADER_SIZE:
        raise ImageError(IMG_ERR_LENGTH, "len=%d slot_size=%d"
                         % (hdr.payload_length, slot_size))
    if (hdr.entry_point < slot_start + IMAGE_VTABLE_OFFSET
            or hdr.entry_point >= slot_start + IMAGE_HEADER_SIZE + hdr.payload_length
            or (hdr.entry_point & 1) == 0):
        raise ImageError(IMG_ERR_ENTRY, "entry=0x%08X" % hdr.entry_point)


def check_image(image, slot_start, slot_size, slot_id):
    """Validate header + payload CRC of a complete image (header+payload)."""
    hdr = parse_image_header(image)
    check_header(hdr, slot_start, slot_size, slot_id)
    payload = bytes(image[IMAGE_HEADER_SIZE:IMAGE_HEADER_SIZE + hdr.payload_length])
    if len(payload) != hdr.payload_length:
        raise ImageError(IMG_ERR_LENGTH, "image shorter than payload_length")
    initial_sp, reset = struct.unpack("<II", payload[:8])
    if initial_sp < 0x20000000 or initial_sp > 0x20004000 or initial_sp % 8:
        raise ImageError(IMG_ERR_ENTRY, "initial_sp=0x%08X" % initial_sp)
    if reset != hdr.entry_point:
        raise ImageError(IMG_ERR_ENTRY, "reset vector does not match header")
    if crc32_ieee(payload) != hdr.payload_crc32:
        raise ImageError(IMG_ERR_PAYLOAD_CRC)
    return hdr


def build_image(raw_bin, slot_start, slot_size, slot_id,
                ver=(0, 0, 0, 0), build_number=0):
    """Build a complete image (header + payload) from a raw application .bin.

    raw_bin is linked at (slot_start + IMAGE_VTABLE_OFFSET); the entry point is
    taken from its vector table word 1 (reset handler).
    """
    raw_bin = bytes(raw_bin)
    if len(raw_bin) == 0:
        raise ImageError(IMG_ERR_LENGTH, "empty binary")
    if len(raw_bin) < 24:
        raise ImageError(IMG_ERR_ENTRY, "binary too small for XMC vector table")
    if len(raw_bin) > slot_size - IMAGE_HEADER_SIZE:
        raise ImageError(IMG_ERR_LENGTH, "binary %d B does not fit slot %d B"
                         % (len(raw_bin), slot_size))
    entry_point = struct.unpack("<I", raw_bin[4:8])[0]
    hdr = ImageHeader(
        slot_id=slot_id,
        ver_major=ver[0] & 0xFF, ver_minor=ver[1] & 0xFF, ver_patch=ver[2] & 0xFF,
        reserved=0, build_number=build_number,
        payload_length=len(raw_bin),
        payload_crc32=crc32_ieee(raw_bin),
        entry_point=entry_point)
    hdr.pack(with_crc=True)
    return hdr.pack() + raw_bin
