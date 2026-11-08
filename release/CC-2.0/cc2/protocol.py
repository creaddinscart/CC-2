# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import json
import socket
import struct
import time

MAX_FRAME = 16 * 1024 * 1024
MAGIC = "cc2"

PROBE = "probe"
JOIN = "join"
ENC = "enc"
ADMIN = "admin"
PING = "ping"
BYE = "bye"

ROOM_INFO = "room_info"
WELCOME = "welcome"
ERROR = "error"
PONG = "pong"
SYS = "sys"
ROOM = "room"
PEERS = "peers"

I_MSG = "msg"
I_TYPING = "typing"
I_FILE_OFFER = "file_offer"
I_FILE_CHUNK = "file_chunk"
I_FILE_END = "file_end"
I_FILE_CANCEL = "file_cancel"

CHUNK_SIZE = 48 * 1024
HISTORY_LIMIT = 200


def now() -> float:
    return time.time()


def dumps(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def loads(data: bytes) -> dict:
    obj = json.loads(data.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("frame is not an object")
    return obj


def pack(obj: dict) -> bytes:
    payload = dumps(obj)
    if len(payload) > MAX_FRAME:
        raise ValueError("frame too large")
    return struct.pack(">I", len(payload)) + payload


def recv_exact(sock: socket.socket, size: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < size:
        try:
            part = sock.recv(min(65536, size - len(buf)))
        except (ConnectionError, OSError, socket.timeout):
            return None
        if not part:
            return None
        buf.extend(part)
    return bytes(buf)


def recv_obj(sock: socket.socket) -> dict | None:
    header = recv_exact(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    if length == 0 or length > MAX_FRAME:
        return None
    body = recv_exact(sock, length)
    if body is None:
        return None
    try:
        return loads(body)
    except (ValueError, UnicodeDecodeError):
        return None


def send_obj(sock: socket.socket, obj: dict) -> bool:
    try:
        sock.sendall(pack(obj))
        return True
    except (OSError, ValueError):
        return False


def connect_socket(host: str, port: int, timeout: float = 5.0) -> socket.socket:
    clean = host.strip()
    if clean.startswith("[") and clean.endswith("]"):
        clean = clean[1:-1]
    infos = socket.getaddrinfo(clean, port, 0, socket.SOCK_STREAM)
    last: Exception | None = None
    for family, socktype, proto, _, addr in infos:
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(addr)
            return sock
        except OSError as exc:
            last = exc
            try:
                sock.close()
            except Exception:
                pass
    raise ConnectionError(f"cannot connect to {host}:{port}: {last}")


def probe_room(host: str, port: int, timeout: float = 4.0) -> dict | None:
    sock = None
    try:
        sock = connect_socket(host, port, timeout)
        sock.settimeout(timeout)
        if not send_obj(sock, {"t": PROBE, "magic": MAGIC, "ts": now()}):
            return None
        reply = recv_obj(sock)
        if reply and reply.get("t") == ROOM_INFO:
            reply["_reachable"] = True
            return reply
        return reply
    except (OSError, ValueError, ConnectionError):
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
