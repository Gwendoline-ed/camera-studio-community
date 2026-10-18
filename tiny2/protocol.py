"""Small, bounded subset of the Tiny 2 protocol. No USB access in this module.

Frame layout and commands were checked against the supplied libdev.dll in
Ghidra. Status offsets / Tiny2-specific tracking behavior are documented in
SOURCES.txt. Float resolution must not be confused with mechanical accuracy.
"""
from .i18n import tr as _t
from dataclasses import dataclass
import math
import struct

FRAME_SIZE = 60
MODES = {
    "Aus": (0, 0), "Normal": (2, 0), "Oberkörper": (2, 1),
    "Nahansicht": (2, 2), "Ohne Kopf": (2, 3), "Unterkörper": (2, 4),
    "Gruppe": (1, 0), "Hand": (3, 0), "Whiteboard": (4, 0), "Tisch": (5, 0),
}


class ProtocolError(ValueError):
    pass


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc ^ 0xFFFF


def frame(seq: int, command: int, receiver: int, payload=b"", *, query=False) -> bytes:
    if not (0 <= seq <= 65535 and 0 <= command <= 65535 and 0 <= receiver < 64):
        raise ProtocolError(_t('Ungültiger Nachrichtenkopf'))
    if len(payload) > 44 or (query and payload):
        raise ProtocolError(_t('Ungültige Nutzdatenlänge'))
    flags = (1 if query else 5) | (0x20 if payload else 0)
    packet = bytearray(FRAME_SIZE)
    struct.pack_into("<BBHHHBBH", packet, 0, 0xAA, flags, seq, 12, 0, 10, receiver, command)
    struct.pack_into("<H", packet, 6, crc16(packet[:12]))
    if payload:
        struct.pack_into("<HH", packet, 12, len(payload), 0)
        packet[16:16 + len(payload)] = payload
        struct.pack_into("<H", packet, 14, crc16(packet[12:16 + len(payload)]))
    return bytes(packet)


@dataclass(frozen=True)
class Reply:
    seq: int
    command: int
    sender: int
    receiver: int
    flags: int
    payload: bytes


def parse_reply(data: bytes) -> Reply:
    if len(data) != FRAME_SIZE or data[0] != 0xAA or data[1] & 3 != 1:
        raise ProtocolError(_t('Keine gültige V3-Antwort'))
    _, flags, seq, length, checksum, sender, receiver, command = struct.unpack_from("<BBHHHBBH", data)
    if length != 12:
        raise ProtocolError(_t('Unerwartete Kopflänge'))
    header = bytearray(data[:length]); header[6:8] = b"\0\0"
    if crc16(header) != checksum:
        raise ProtocolError(_t('Kopf-Prüfsumme stimmt nicht'))
    payload = b""
    if flags & 0x60:
        if flags & 0x60 != 0x20:
            raise ProtocolError(_t('Segmentierte Antworten werden nicht unterstützt'))
        size, checksum = struct.unpack_from("<HH", data, length)
        if size > 44:
            raise ProtocolError(_t('Antwort ist zu groß'))
        segment = bytearray(data[length:length + 4 + size]); segment[2:4] = b"\0\0"
        if crc16(segment) != checksum:
            raise ProtocolError(_t('Nutzdaten-Prüfsumme stimmt nicht'))
        payload = data[length + 4:length + 4 + size]
    # Reply kind is bits 2..4; bit 7 marks the error response seen in firmware.
    if flags & 0x80:
        raise ProtocolError(_t('Kamera meldet einen Befehlsfehler'))
    if flags & 0x1C != 8:
        raise ProtocolError(_t('Nachricht ist keine Antwort'))
    return Reply(seq, command, sender, receiver, flags, payload)


def ext(tag: int, values: bytes) -> bytes:
    if not 0 <= tag <= 255 or not 1 <= len(values) <= 58:
        raise ProtocolError(_t('Ungültige Erweiterungsdaten'))
    return bytes([tag, len(values)]) + values + bytes(58 - len(values))


def finite_range(value, minimum, maximum, label):
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(_t('{v0}: erlaubt sind {v1} bis {v2}', v0=label, v1=minimum, v2=maximum))
    return value


def angle_payload(pan, tilt):
    pan = finite_range(pan, -130, 130, _t('Schwenken'))
    tilt = finite_range(tilt, -90, 90, _t('Neigen'))
    # Wire order: roll, pitch (down positive), yaw (camera-left positive).
    return struct.pack("<fff", 0, -tilt, pan)


def status(data: bytes) -> dict:
    if len(data) != 60 or data[2] not in (0, 1):
        raise ProtocolError(_t('Ungültige Statusantwort'))
    mode = (data[0x18], data[0x1C])
    return {
        "awake": data[2] == 0,
        "mode": next((name for name, pair in MODES.items() if pair == mode), "Wechsel / unbekannt"),
        "mode_raw": mode,
        "hdr": data[6] != 0,
        "fov": {0: "Weit", 1: "Mittel", 2: "Eng", 3: "Individuell"}.get(data[0x11], "Unbekannt"),
        "speed": {0: "Standard", 2: "Sport"}.get(data[0x24], "Unbekannt"),
        "zoom_percent": data[4] if data[4] <= 100 else None,
    }
