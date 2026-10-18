"""Linux V4L2 / UVC XU transport using the published kernel ioctl ABI."""
from .i18n import tr as _t
import ctypes as C
from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import secrets
import stat
import struct
import threading
import time
from . import protocol as P

VID, PID = "3564", "fef8"
XU_GUID = bytes.fromhex("91721e9a436883466d9239bc7906ee49")
libc = C.CDLL(None, use_errno=True)
libc.ioctl.argtypes = [C.c_int, C.c_ulong, C.c_void_p]
libc.ioctl.restype = C.c_int


class XU(C.Structure):
    _fields_ = [("unit", C.c_uint8), ("selector", C.c_uint8), ("query", C.c_uint8),
                ("size", C.c_uint16), ("data", C.POINTER(C.c_uint8))]


def ioc(direction, typ, number, size):
    return direction << 30 | size << 16 | ord(typ) << 8 | number


XU_QUERY = ioc(3, "u", 0x21, C.sizeof(XU))
QUERYCAP = ioc(2, "V", 0, 104)
QUERYCTRL = ioc(3, "V", 36, 68)
GET_CTRL = ioc(3, "V", 27, 8)
SET_CTRL = ioc(3, "V", 28, 8)
CONTROLS = {
    "zoom": 0x009A090D, "focus_auto": 0x009A090C, "focus": 0x009A090A,
    "brightness": 0x00980900, "contrast": 0x00980901, "saturation": 0x00980902,
    "sharpness": 0x0098091B, "white_balance_auto": 0x0098090C,
    "white_balance": 0x0098091A,
}


@dataclass(frozen=True)
class Candidate:
    path: str
    usb_path: str
    unit: int
    present: bool


def extension_unit(descriptors: bytes) -> int:
    offset = 0
    # Parse within a VideoControl interface, avoiding audio descriptors of same subtype.
    video_control = False
    while offset + 2 <= len(descriptors):
        size, kind = descriptors[offset:offset + 2]
        if size < 2 or offset + size > len(descriptors):
            break
        row = descriptors[offset:offset + size]
        if kind == 4 and size >= 9:
            video_control = row[5:7] == bytes([14, 1])
        if video_control and kind == 0x24 and size >= 20 and row[2] == 6 and row[4:20] == XU_GUID:
            return row[3]
        offset += size
    raise ValueError(_t('Passende OBSBOT-Erweiterung fehlt im USB-Deskriptor'))


def discover(sys_root=Path("/sys/class/video4linux"), dev_root=Path("/dev")):
    found = []
    for node in sorted(sys_root.glob("video*")):
        for parent in node.resolve().parents:
            try:
                if (parent / "idVendor").read_text().strip() != VID:
                    continue
                if (parent / "idProduct").read_text().strip() != PID:
                    continue
                unit = extension_unit((parent / "descriptors").read_bytes())
                path = dev_root / node.name
                found.append(Candidate(str(path), str(parent), unit, path.exists()))
                break
            except (OSError, ValueError):
                continue
    return found


class Camera:
    def __init__(self, candidate: Candidate, *, writable=True):
        # Revalidate identity at open time; paths may have changed after replugging.
        current = next((x for x in discover() if x.path == candidate.path and x.usb_path == candidate.usb_path), None)
        if current is None:
            raise OSError(_t('Die Kamera wurde getrennt oder die Gerätezuordnung hat sich geändert'))
        self.candidate = current
        self.writable = writable
        self.lock = threading.RLock()
        self.seq = secrets.randbelow(65536)
        self.fd = -1
        fd = os.open(current.path, (os.O_RDWR if writable else os.O_RDONLY) | os.O_CLOEXEC | os.O_NONBLOCK)
        self.fd = fd
        try:
            if not stat.S_ISCHR(os.fstat(fd).st_mode):
                raise OSError(_t('Das Ziel ist kein Kameragerät'))
            caps = bytearray(104); fcntl.ioctl(fd, QUERYCAP, caps, True)
            capabilities, device_caps = struct.unpack_from("<II", caps, 84)
            effective = device_caps if capabilities & 0x80000000 else capabilities
            if not effective & (1 | 0x1000):
                raise OSError(_t('Dieser Geräteknoten enthält nur Metadaten'))
            for selector in (2, 6):
                size = struct.unpack("<H", self.query(selector, 0x85, size=2))[0]
                info = self.query(selector, 0x86, size=1)[0]
                if size != 60 or info & 3 != 3:
                    raise OSError(_t('Unerwartete Kameraschnittstelle (Kanal {v0})', v0=selector))
        except BaseException:
            self.close()
            raise

    def close(self):
        with self.lock:
            if self.fd >= 0:
                os.close(self.fd); self.fd = -1

    def query(self, selector, request, data=None, size=60):
        with self.lock:
            if request == 1 and not self.writable:
                raise PermissionError(_t('Kamera wurde nur zum Lesen geöffnet'))
            if self.fd < 0:
                raise OSError(errno.ENODEV, _t('Kamera ist nicht verbunden'))
            if data is not None:
                if len(data) != size:
                    raise ValueError(_t('Falsche USB-Nachrichtenlänge'))
                buffer = (C.c_uint8 * size).from_buffer_copy(data)
            else:
                buffer = (C.c_uint8 * size)()
            query = XU(self.candidate.unit, selector, request, size, buffer)
            if libc.ioctl(self.fd, XU_QUERY, C.byref(query)) < 0:
                error = C.get_errno()
                raise OSError(error, os.strerror(error))
            return bytes(buffer)

    def send(self, command, receiver, payload=b"", *, read=False, timeout=0.7):
        with self.lock:
            seq = self.seq; self.seq = (self.seq + 1) & 0xFFFF
            packet = P.frame(seq, command, receiver, payload, query=read)
            self.query(2, 1, packet)
            if not read:
                return None  # USB accepted the write; this is not an acknowledgement.
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                time.sleep(0.04)
                raw = self.query(2, 0x81)
                # Ignore stale mailboxes, but surface a matching error/corrupt response.
                if raw[0] != 0xAA or struct.unpack_from("<H", raw, 2)[0] != seq or struct.unpack_from("<H", raw, 10)[0] != command:
                    continue
                reply = P.parse_reply(raw)
                if reply.sender != receiver or reply.receiver != 10:
                    continue
                return reply.payload
            raise TimeoutError(_t('Keine passende Antwort der Kamera'))

    def raw_write(self, tag, values):
        return self.query(6, 1, P.ext(tag, values))

    def status(self):
        return P.status(self.query(6, 0x81))

    def control_info(self, key):
        with self.lock:
            buffer = bytearray(68); struct.pack_into("<I", buffer, 0, CONTROLS[key])
            fcntl.ioctl(self.fd, QUERYCTRL, buffer, True)
            minimum, maximum, step, default, flags = struct.unpack_from("<iiiiI", buffer, 40)
            if flags & 1:
                raise OSError(_t('Einstellung wird nicht unterstützt'))
            return dict(min=minimum, max=maximum, step=max(step, 1), default=default,
                        writable=not bool(flags & (4 | 8 | 16)), flags=flags)

    def get_control(self, key):
        with self.lock:
            buffer = bytearray(struct.pack("<Ii", CONTROLS[key], 0))
            fcntl.ioctl(self.fd, GET_CTRL, buffer, True)
            return struct.unpack_from("<i", buffer, 4)[0]

    def set_control(self, key, value):
        with self.lock:
            if not self.writable:
                raise PermissionError(_t('Kamera wurde nur zum Lesen geöffnet'))
            info = self.control_info(key)
            if not info["writable"]:
                raise ValueError(_t('Einstellung ist momentan nicht veränderbar'))
            value = P.finite_range(value, info["min"], info["max"], key)
            rounded = info["min"] + round((value - info["min"]) / info["step"]) * info["step"]
            rounded = min(info["max"], max(info["min"], rounded))
            buffer = bytearray(struct.pack("<Ii", CONTROLS[key], int(rounded)))
            fcntl.ioctl(self.fd, SET_CTRL, buffer, True)
            return self.get_control(key)


def connect(path=None, *, writable=True):
    candidates = discover()
    errors = []
    for candidate in candidates:
        if path and candidate.path != path:
            continue
        try:
            return Camera(candidate, writable=writable)
        except OSError as error:
            errors.append(f"{candidate.path}: {error}")
    if candidates and not any(c.present for c in candidates):
        raise OSError(_t('Tiny 2 erkannt, aber die Kamerageräte sind in dieser Umgebung nicht zugänglich.'))
    raise OSError("; ".join(errors) if errors else _t('Keine OBSBOT Tiny 2 gefunden. USB-Verbindung prüfen.'))
