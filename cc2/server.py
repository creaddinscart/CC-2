# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import base64
import hashlib
import hmac
import os
import select
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

from . import crypto, protocol as P
from .brand import APP_NAME, PROTOCOL
from .frp import FRPConfig

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class RoomError(Exception):
    pass


@dataclass
class RoomConfig:
    name: str
    port: int
    advertise_ip: str
    bind_ip: str
    password: str
    max_users: int = 8
    host_user: str = "host"
    salt: bytes = field(default_factory=crypto.new_salt)
    admin_token: str = field(default_factory=lambda: os.urandom(16).hex())
    created_at: float = field(default_factory=time.time)
    frp: FRPConfig | None = None

    @property
    def auth(self) -> str:
        return crypto.auth_token(self.password, self.salt)

    @property
    def frp_enabled(self) -> bool:
        return self.frp is not None

    @property
    def endpoint(self) -> str:
        from .netdetect import format_endpoint

        if self.frp is not None:
            return self.frp.endpoint
        return format_endpoint(self.advertise_ip, self.port)

    @property
    def local_endpoint(self) -> str:
        from .netdetect import format_endpoint

        return format_endpoint(self.advertise_ip, self.port)

    @property
    def join_port(self) -> int:
        return self.frp.remote_port if self.frp is not None else self.port

    def public_info(self) -> dict:
        return {
            "frp": self.frp is not None,
            "frp_endpoint": self.frp.endpoint if self.frp is not None else "",
            "frp_remote_port": self.frp.remote_port if self.frp is not None else 0,
            "frp_local_port": self.frp.local_port if self.frp is not None else 0,
            "public_endpoint": self.endpoint,
            "local_endpoint": self.local_endpoint,
            "join_port": self.join_port,
        }


class Peer:

    def __init__(self, sock: socket.socket, address, stop: threading.Event):
        self.sock = sock
        self.address = address
        self.ws = False
        self.stop = stop
        self.alive = True
        self.user = ""
        self.joined = False
        self.is_host = False
        self.caps: list[str] = ["v1"]
        self._rx = bytearray()
        self._tx_lock = threading.Lock()
        self._frag = bytearray()
        self._frag_opcode = 0
        self.id = id(self)

    def _fill(self) -> bool:
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            return False
        except (OSError, ConnectionError):
            self.alive = False
            return False
        if not chunk:
            self.alive = False
            return False
        self._rx.extend(chunk)
        return True

    def _take(self, size: int) -> bytes | None:
        while len(self._rx) < size:
            if self.stop.is_set():
                return None
            if not self._fill():
                if not self.alive:
                    return None
                if self.stop.is_set():
                    return None
        data = bytes(self._rx[:size])
        del self._rx[:size]
        return data

    def sniff(self) -> bool:
        while not self._rx and self.alive and not self.stop.is_set():
            if not self._fill() and not self.alive:
                return False
        if bytes(self._rx[:3]) == b"GET":
            self.ws = True
        return self.alive

    def handshake(self) -> bool:
        header = b""
        deadline = time.time() + 5
        while b"\r\n\r\n" not in header and time.time() < deadline:
            if self._rx:
                header += bytes(self._rx)
                self._rx.clear()
            if b"\r\n\r\n" in header:
                break
            if not self._fill():
                if not self.alive:
                    return False
        head, _, rest = header.partition(b"\r\n\r\n")
        self._rx.extend(rest)
        key = b""
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"sec-websocket-key:"):
                key = line.split(b":", 1)[1].strip()
        if not key:
            self.alive = False
            return False
        accept = base64.b64encode(hashlib.sha1(key + WS_GUID.encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            f"Server: {APP_NAME}\r\n\r\n"
        ).encode("ascii")
        try:
            self.sock.sendall(response)
        except OSError:
            self.alive = False
            return False
        return True

    @staticmethod
    def _ws_frame(payload: bytes, opcode: int = 1) -> bytes:
        head = bytearray([0x80 | opcode])
        size = len(payload)
        if size < 126:
            head.append(size)
        elif size < 65536:
            head.append(126)
            head.extend(struct.pack(">H", size))
        else:
            head.append(127)
            head.extend(struct.pack(">Q", size))
        return bytes(head) + payload

    def send(self, obj: dict) -> bool:
        if not self.alive:
            return False
        try:
            data = P.dumps(obj)
            frame = self._ws_frame(data) if self.ws else struct.pack(">I", len(data)) + data
            with self._tx_lock:
                self.sock.sendall(frame)
            return True
        except (OSError, ValueError):
            self.alive = False
            return False

    def recv(self) -> dict | None:
        if self.ws:
            header = self._take(2)
            if header is None:
                return None
            first, second = header[0], header[1]
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            size = second & 0x7F
            if size == 126:
                ext = self._take(2)
                if ext is None:
                    return None
                size = struct.unpack(">H", ext)[0]
            elif size == 127:
                ext = self._take(8)
                if ext is None:
                    return None
                size = struct.unpack(">Q", ext)[0]
            if size > P.MAX_FRAME:
                self.alive = False
                return None
            mask = self._take(4) if masked else b""
            if mask is None:
                return None
            payload = self._take(size) if size else b""
            if payload is None:
                return None
            if masked:
                mask_bytes = mask
                payload = bytes(b ^ mask_bytes[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                try:
                    with self._tx_lock:
                        self.sock.sendall(self._ws_frame(payload, 0x8))
                except OSError:
                    pass
                self.alive = False
                return None
            if opcode == 0x9:
                self.send_raw_ws(self._ws_frame(payload, 0xA))
                return {}
            if opcode == 0xA:
                return {}
            if opcode == 0x0:
                self._frag.extend(payload)
                if not fin:
                    return {}
                payload = bytes(self._frag)
                self._frag.clear()
                opcode = self._frag_opcode
            elif not fin:
                self._frag = bytearray(payload)
                self._frag_opcode = opcode
                return {}
            if opcode not in (0x1, 0x2):
                return {}
            try:
                return P.loads(payload)
            except (ValueError, UnicodeDecodeError):
                return {}

        head = self._take(4)
        if head is None:
            return None
        (size,) = struct.unpack(">I", head)
        if size == 0 or size > P.MAX_FRAME:
            self.alive = False
            return None
        body = self._take(size)
        if body is None:
            return None
        try:
            return P.loads(body)
        except (ValueError, UnicodeDecodeError):
            return {}

    def send_raw_ws(self, frame: bytes) -> None:
        try:
            with self._tx_lock:
                self.sock.sendall(frame)
        except OSError:
            self.alive = False

    def close(self) -> None:
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class RoomServer:
    def __init__(self, config: RoomConfig):
        self.config = config
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._peers: dict[int, Peer] = {}
        self.history: list[dict] = []
        self.frames = 0
        self.bytes_relayed = 0
        self._seq = 0

    def start(self) -> None:
        bind = self.config.bind_ip
        family = socket.AF_INET6 if ":" in bind else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            try:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except (AttributeError, OSError):
                pass
        try:
            listener.bind((bind, self.config.port))
            listener.listen(32)
        except OSError as exc:
            listener.close()
            raise RoomError(f"cannot bind {bind}:{self.config.port} - {exc}") from exc
        listener.settimeout(0.3)
        self._listener = listener
        self._stop.clear()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="cc2-accept")
        self._thread.start()

    def _accept_loop(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([listener], [], [], 0.25)
                if not ready:
                    continue
                conn, addr = listener.accept()
            except OSError:
                break
            conn.settimeout(1.0)
            peer = Peer(conn, addr, self._stop)
            with self._lock:
                self._peers[peer.id] = peer
            threading.Thread(
                target=self._handle, args=(peer,), daemon=True, name=f"cc2-peer-{peer.id}"
            ).start()
        try:
            listener.close()
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            peers = list(self._peers.values())
        for peer in peers:
            peer.close()
        listener = self._listener
        if listener:
            try:
                listener.close()
            except OSError:
                pass
        self._listener = None

    def serve_forever(self) -> None:
        if self._thread is None:
            self.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.4)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _handle(self, peer: Peer) -> None:
        try:
            if not peer.sniff():
                return
            if peer.ws and not peer.handshake():
                return
            while peer.alive and not self._stop.is_set():
                obj = peer.recv()
                if obj is None:
                    break
                if obj:
                    self._dispatch(peer, obj)
        finally:
            was_joined = peer.joined
            with self._lock:
                self._peers.pop(peer.id, None)
            peer.close()
            if was_joined:
                self._system(f"{peer.user} left the room")
                self._broadcast_room()

    def _send(self, peer: Peer, obj: dict) -> None:
        peer.send(obj)

    def _error(self, peer: Peer, message: str, code: str = "error") -> None:
        peer.send({"t": P.ERROR, "code": code, "message": message, "ts": P.now()})

    def _broadcast(self, obj: dict, exclude: Peer | None = None) -> None:
        with self._lock:
            peers = list(self._peers.values())
        for peer in peers:
            if peer is not exclude and peer.joined:
                peer.send(obj)

    def _broadcast_room(self) -> None:
        self._broadcast({"t": P.ROOM, **self._room_state()})

    def _system(self, text: str) -> None:
        self._broadcast({"t": P.SYS, "text": text, "ts": P.now()})

    def _room_state(self) -> dict:
        with self._lock:
            joined = [p for p in self._peers.values() if p.joined]
            members = sorted(p.user for p in joined)
            common = set(joined[0].caps) if joined else {"v1"}
            for peer in joined[1:]:
                common &= set(peer.caps)
            if not common:
                common = {"v1"}
        return {
            "name": self.config.name,
            "endpoint": self.config.endpoint,
            "max_users": self.config.max_users,
            "users": len(members),
            "members": members,
            "common": sorted(common),
            "host": self.config.host_user,
            "ts": P.now(),
        }

    def _room_info(self) -> dict:
        state = self._room_state()
        return {
            "t": P.ROOM_INFO,
            "magic": P.MAGIC,
            "protocol": PROTOCOL,
            "app": APP_NAME,
            "name": self.config.name,
            "salt": self.config.salt.hex(),
            "has_password": True,
            "users": state["users"],
            "max_users": state["max_users"],
            "members": state["members"],
            "host": self.config.host_user,
            "created_at": self.config.created_at,
            "endpoint": self.config.endpoint,
            "full": state["users"] >= self.config.max_users,
            "ts": P.now(),
            **self.config.public_info(),
        }

    def _dispatch(self, peer: Peer, obj: dict) -> None:
        kind = obj.get("t")
        if kind == P.PROBE:
            peer.send(self._room_info())
            return
        if kind == P.PING:
            peer.send({"t": P.PONG, "ts": P.now()})
            return
        if kind == P.BYE:
            peer.alive = False
            return
        if kind == P.JOIN:
            self._do_join(peer, obj)
            return
        if kind == P.ENC:
            self._do_enc(peer, obj)
            return
        if kind == P.ADMIN:
            self._do_admin(peer, obj)
            return

    def _do_join(self, peer: Peer, obj: dict) -> None:
        if peer.joined:
            return
        user = str(obj.get("user", "")).strip().replace("\n", " ")[:24]
        if not user:
            self._error(peer, "A username is required.", "bad_user")
            return
        with self._lock:
            members = [p.user for p in self._peers.values() if p.joined]
        if len(members) >= self.config.max_users:
            self._error(peer, "This room is full. Ask the host to raise the member cap.", "full")
            return
        if user in members:
            self._error(peer, "That username is already taken in this room.", "duplicate")
            return
        supplied = str(obj.get("auth", ""))
        if not hmac.compare_digest(supplied, self.config.auth):
            self._error(peer, "Incorrect room password.", "password")
            return
        token = str(obj.get("admin", ""))
        loopback = str(peer.address[0]) in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
        caps = obj.get("caps")
        if isinstance(caps, list) and all(isinstance(c, str) for c in caps):
            peer.caps = [c for c in caps if c in ("v1", "v2")] or ["v1"]
        peer.user = user
        peer.joined = True
        peer.is_host = bool(token and hmac.compare_digest(token, self.config.admin_token)) or (
            loopback and user == self.config.host_user and self.config.frp is None
        )
        with self._lock:
            history = list(self.history)
        peer.send(
            {
                "t": P.WELCOME,
                "you": user,
                "is_host": peer.is_host,
                "room": self._room_state(),
                "salt": self.config.salt.hex(),
                "history": history,
                "protocol": PROTOCOL,
                "motd": f"Welcome to {self.config.name}. Messages and files are end-to-end encrypted.",
                "ts": P.now(),
            }
        )
        self._system(f"{user} joined the room")
        self._broadcast_room()

    def _do_enc(self, peer: Peer, obj: dict) -> None:
        if not peer.joined:
            self._error(peer, "Join the room first.", "not_joined")
            return
        token = obj.get("d")
        if not isinstance(token, str) or len(token) > P.MAX_FRAME:
            self._error(peer, "Invalid payload.", "bad_frame")
            return
        with self._lock:
            self._seq += 1
            seq = self._seq
            self.frames += 1
            self.bytes_relayed += len(token)
        frame = {
            "t": P.ENC,
            "from": peer.user,
            "d": token,
            "k": str(obj.get("k", "msg")),
            "seq": seq,
            "ts": P.now(),
        }
        self._broadcast(frame, exclude=peer)
        if frame["k"] in ("msg", "file"):
            with self._lock:
                self.history.append(frame)
                if len(self.history) > P.HISTORY_LIMIT:
                    del self.history[: len(self.history) - P.HISTORY_LIMIT]

    def _do_admin(self, peer: Peer, obj: dict) -> None:
        if not peer.is_host:
            self._error(peer, "Only the room host can do that.", "forbidden")
            return
        action = obj.get("action")
        if action == "set_max":
            try:
                value = max(1, min(256, int(obj.get("value"))))
            except (TypeError, ValueError):
                self._error(peer, "Invalid member cap.", "bad_value")
                return
            self.config.max_users = value
            self._system(f"Host set the member cap to {value}")
            self._broadcast_room()
        elif action == "kick":
            target = str(obj.get("user", ""))
            with self._lock:
                victim = next(
                    (p for p in self._peers.values() if p.joined and p.user == target), None
                )
            if victim:
                victim.send({"t": P.ERROR, "code": "kicked", "message": "You were removed by the host."})
                victim.close()
                self._system(f"{target} was removed by the host")
                self._broadcast_room()
        elif action == "close":
            self._broadcast({"t": P.SYS, "text": "The host closed this room.", "ts": P.now()})
            threading.Timer(0.3, self.stop).start()
        elif action == "info":
            peer.send({"t": P.SYS, "text": f"Room stats: {self.stats()}", "ts": P.now()})

    def set_max_users(self, value: int) -> int:
        self.config.max_users = max(1, min(256, int(value)))
        self._system(f"Host set the member cap to {self.config.max_users}")
        self._broadcast_room()
        return self.config.max_users

    def kick(self, user: str) -> None:
        with self._lock:
            victim = next((p for p in self._peers.values() if p.joined and p.user == user), None)
        if victim:
            victim.send({"t": P.ERROR, "code": "kicked", "message": "You were removed by the host."})
            victim.close()

    def stats(self) -> dict:
        state = self._room_state()
        state.update(
            {
                "port": self.config.port,
                "advertise_ip": self.config.advertise_ip,
                "uptime": round(time.time() - self.config.created_at, 1),
                "frames_relayed": self.frames,
                "ciphertext_bytes": self.bytes_relayed,
                "running": not self._stop.is_set(),
                **self.config.public_info(),
            }
        )
        return state
