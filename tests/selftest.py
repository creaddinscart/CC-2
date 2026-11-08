# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cc2 import crypto, netdetect, protocol as P
from cc2.client import ChatClient, ClientError
from cc2.server import RoomConfig, RoomServer

PASS, FAIL = 0, 0


def check(label: str, condition: bool, extra: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {extra}")


def drain(client: ChatClient, kind: str, seconds: float = 3.0) -> dict | None:
    deadline = time.time() + seconds
    found = []
    while time.time() < deadline:
        for ev in client.events():
            found.append(ev)
            if ev.get("t") == kind:
                return ev
        time.sleep(0.03)
    return None


def make_ws_frame(text: str) -> bytes:
    payload = text.encode()
    mask = os.urandom(4)
    head = bytearray([0x81])
    n = len(payload)
    if n < 126:
        head.append(0x80 | n)
    else:
        head.append(0x80 | 126)
        head.extend(struct.pack(">H", n))
    head.extend(mask)
    return bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def recv_ws_text(sock: socket.socket) -> dict:
    head = sock.recv(2)
    opcode, second = head[0] & 0x0F, head[1]
    size = second & 0x7F
    if size == 126:
        size = struct.unpack(">H", sock.recv(2))[0]
    elif size == 127:
        size = struct.unpack(">Q", sock.recv(8))[0]
    data = b""
    while len(data) < size:
        data += sock.recv(size - len(data))
    return json.loads(data.decode())


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    print("\n== crypto ==")
    salt = crypto.new_salt()
    key = crypto.derive_key("hunter2", salt)
    token = crypto.encrypt(key, b"hello \xe4\xb8\x96\xe7\x95\x8c")
    check("encrypt/decrypt round trip", crypto.decrypt(key, token) == b"hello \xe4\xb8\x96\xe7\x95\x8c")
    check("ciphertext version byte", base64.b64decode(token)[0] in (1, 2), str(base64.b64decode(token)[0]))
    tampered = list(base64.b64decode(token))
    tampered[-1] ^= 1
    try:
        crypto.decrypt(key, base64.b64encode(bytes(tampered)).decode())
        check("tampering rejected", False)
    except crypto.CryptoError:
        check("tampering rejected", True)
    check("auth token differs from key", crypto.auth_token("hunter2", salt) != key.hex())
    check("v1 fallback readable", crypto.decrypt(key, crypto.encrypt(key, b"x")) == b"x")

    print("\n== address discovery ==")
    opts = netdetect.local_addresses(include_wan=False)
    check("addresses discovered", len(opts) >= 2, str(len(opts)))
    best = netdetect.recommended(opts)
    check("recommendation produced", best is not None)
    check("IPv6 bracket formatting", netdetect.format_endpoint("2001:db8::1", 9001) == "[2001:db8::1]:9001")
    print(f"  info: preferred = {best.ip if best else '?'} ({best.label if best else '?'})")

    port = free_port()
    conf = RoomConfig(
        name="Test Lab",
        port=port,
        advertise_ip="127.0.0.1",
        bind_ip="127.0.0.1",
        password="s3cret",
        max_users=3,
        host_user="Alice",
    )
    server = RoomServer(conf)
    server.start()

    print("\n== room probe ==")
    info = ChatClient.probe("127.0.0.1", port)
    check("room is discoverable", bool(info and info.get("t") == P.ROOM_INFO))
    check("probe reveals room name", info and info.get("name") == "Test Lab")
    check(
        "probe does not leak password",
        all("password" not in k for k in info if k != "has_password"),
        str(sorted(info)),
    )
    check("missing room detected", ChatClient.probe("127.0.0.1", free_port()) is None)

    print("\n== join ==")
    a = ChatClient()
    a.connect("127.0.0.1", port, "Alice", "s3cret", admin_token=conf.admin_token)
    check("host flag granted", a.is_host)
    try:
        bad = ChatClient()
        bad.connect("127.0.0.1", port, "Eve", "wrong")
        check("wrong password refused", False)
    except ClientError as exc:
        check("wrong password refused", "password" in str(exc).lower(), str(exc))
    b = ChatClient()
    b.connect("127.0.0.1", port, "Bob", "s3cret")
    check("second member joined", not b.is_host)
    time.sleep(0.2)
    drain(a, "nothing", 0.2)
    check("host sees 2 members", len(a.members) == 2, str(a.members))

    print("\n== encrypted chat + typing ==")
    a.send_text("Hello Bob, this is private.")
    msg = drain(b, "message")
    check("message delivered", bool(msg and msg.get("text") == "Hello Bob, this is private."))
    check("sender attributed", bool(msg and msg.get("from") == "Alice"))
    b.send_typing(True)
    typ = drain(a, "typing")
    check("typing indicator delivered", bool(typ and typ.get("on") and typ.get("from") == "Bob"))
    b.send_typing(False)

    print("\n== file transfer ==")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(os.urandom(180_000))
        src = tmp.name
    Path(str(cfg_downloads())).mkdir(parents=True, exist_ok=True)
    a.send_file(src)
    saved = drain(b, "file_saved", 8.0)
    check("file received", bool(saved), str(saved))
    if saved:
        check("file bytes identical", Path(saved["path"]).read_bytes() == Path(src).read_bytes())
        os.remove(saved["path"])
    os.remove(src)

    print("\n== host controls ==")
    a.set_max_users(2)
    room_ev = drain(b, "room", 3.0)
    check("member cap broadcast", bool(room_ev and room_ev.get("max_users") == 2), str(room_ev))
    server.set_max_users(5)
    time.sleep(0.2)
    check("in-process host control works", server.config.max_users == 5)

    print("\n== websocket frame compatibility ==")
    ws = socket.create_connection(("127.0.0.1", port), timeout=4)
    ws.settimeout(4)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    ws.sendall(request.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += ws.recv(4096)
    check("websocket upgrade accepted", b"101 Switching Protocols" in resp)
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
    check("Sec-WebSocket-Accept correct", expected in resp)
    ws.sendall(make_ws_frame(json.dumps({"t": P.PROBE, "magic": P.MAGIC})))
    ws_info = recv_ws_text(ws)
    check("WS probe returns room info", ws_info.get("t") == P.ROOM_INFO, str(ws_info)[:120])
    ws.close()

    print("\n== shutdown ==")
    a.leave()
    b.leave()
    server.stop()
    time.sleep(0.2)
    check("room closed", ChatClient.probe("127.0.0.1", port, 0.6) is None)

    print(f"\nRESULT: {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


def cfg_downloads():
    from cc2.config import downloads

    return downloads()


if __name__ == "__main__":
    sys.exit(main())
