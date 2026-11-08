# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import base64
import os
import queue
import threading
import time
import uuid

from . import config as cfg
from . import crypto, protocol as P


class ClientError(Exception):
    pass


class ChatClient:
    def __init__(self):
        self.sock = None
        self.key: bytes | None = None
        self.room: dict = {}
        self.you = ""
        self.is_host = False
        self.members: list[str] = []
        self.max_users = 0
        self.connected = False
        self._events: queue.Queue[dict] = queue.Queue()
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._incoming: dict[str, dict] = {}
        self._typing_state = False
        self._typing_sent_at = 0.0
        self._admin_token = ""
        self.common: list[str] = ["v1"]

    @staticmethod
    def probe(host: str, port: int, timeout: float = 4.0) -> dict | None:
        return P.probe_room(host, port, timeout)

    def connect(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        admin_token: str = "",
        timeout: float = 8.0,
    ) -> dict:
        try:
            sock = P.connect_socket(host, port, timeout)
        except (ConnectionError, OSError) as exc:
            raise ClientError(f"Cannot reach {host}:{port} - {exc}") from exc
        self.sock = sock
        self._admin_token = admin_token
        try:
            sock.settimeout(timeout)
            if not P.send_obj(sock, {"t": P.PROBE, "magic": P.MAGIC, "ts": P.now()}):
                raise ClientError("The peer did not answer the room probe")
            info = P.recv_obj(sock)
            if not info or info.get("t") != P.ROOM_INFO:
                raise ClientError("No CC-2.0 room is running at that address")
            self.room = info
            salt = bytes.fromhex(info.get("salt", ""))
            self.key = crypto.derive_key(password, salt)
            payload = {
                "t": P.JOIN,
                "user": user.strip()[:24],
                "auth": crypto.auth_token(password, salt),
                "admin": admin_token,
                "caps": ["v2", "v1"] if crypto.has_aes_gcm() else ["v1"],
                "ts": P.now(),
            }
            if not P.send_obj(sock, payload):
                raise ClientError("Failed to send the join request")
            reply = P.recv_obj(sock)
            if not reply:
                raise ClientError("The room closed the connection during the handshake")
            if reply.get("t") == P.ERROR:
                raise ClientError(reply.get("message", "Join refused"))
            if reply.get("t") != P.WELCOME:
                raise ClientError("Unexpected handshake reply")
        except (OSError, ValueError, ConnectionError) as exc:
            self._close_socket()
            if isinstance(exc, ClientError):
                raise
            raise ClientError(f"Handshake failed: {exc}") from exc

        self.you = reply.get("you", user)
        self.is_host = bool(reply.get("is_host"))
        state = reply.get("room", {})
        self.members = list(state.get("members", []))
        self.max_users = int(state.get("max_users", 0))
        self.common = list(state.get("common") or ["v1"])
        self.connected = True
        sock.settimeout(None)
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="cc2-client-reader")
        self._reader.start()
        self._emit({"t": "connected", "room": state, "motd": reply.get("motd", ""), "is_host": self.is_host})
        for old in reply.get("history", []):
            self._dispatch(old, history=True)
        return state

    def connect_first(self, hosts: list[str], port: int, user: str, password: str,
                      admin_token: str = "") -> dict:
        last: ClientError | None = None
        for host in hosts:
            try:
                return self.connect(host, port, user, password, admin_token)
            except ClientError as exc:
                last = exc
                continue
        raise last or ClientError("no address reachable")

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            obj = P.recv_obj(self.sock)
            if obj is None:
                break
            self._dispatch(obj)
        was_connected = self.connected
        self.connected = False
        if was_connected and not self._stop.is_set():
            self._emit({"t": "disconnected", "reason": "Connection to the room was lost"})

    def leave(self) -> None:
        self._stop.set()
        if self.connected and self.sock:
            with self._send_lock:
                P.send_obj(self.sock, {"t": P.BYE})
        self._close_socket()
        self.connected = False

    def _close_socket(self) -> None:
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.shutdown(2)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _emit(self, event: dict) -> None:
        event.setdefault("ts", P.now())
        self._events.put(event)

    def poll(self, timeout: float = 0.0) -> dict | None:
        try:
            return self._events.get(timeout=timeout) if timeout > 0 else self._events.get_nowait()
        except queue.Empty:
            return None

    def events(self):
        while True:
            try:
                yield self._events.get_nowait()
            except queue.Empty:
                return

    def _raw(self, obj: dict) -> bool:
        if not self.connected or not self.sock:
            return False
        with self._send_lock:
            return P.send_obj(self.sock, obj)

    def _seal(self, inner: dict, kind: str = "msg") -> bool:
        if self.key is None:
            return False
        prefer_aes = crypto.has_aes_gcm() and "v2" in self.common
        token = crypto.seal_json(self.key, inner, prefer_aes=prefer_aes)
        return self._raw({"t": P.ENC, "d": token, "k": kind, "ts": P.now()})

    def send_text(self, text: str) -> None:
        text = text.rstrip("\n")
        if not text.strip():
            return
        self.send_typing(False)
        self._seal({"t": P.I_MSG, "text": text, "id": uuid.uuid4().hex[:8]}, "msg")
        self._emit({"t": "message", "from": self.you, "text": text, "own": True})

    def send_typing(self, on: bool) -> None:
        now = time.time()
        if on == self._typing_state and now - self._typing_sent_at < 2.0:
            return
        if not on and not self._typing_state:
            return
        self._typing_state = on
        self._typing_sent_at = now
        self._seal({"t": P.I_TYPING, "on": on}, "typing")

    def send_file(self, path: str, progress_cb=None) -> None:
        if not os.path.isfile(path):
            self._emit({"t": "error", "message": f"File not found: {path}"})
            return
        size = os.path.getsize(path)
        fid = uuid.uuid4().hex[:10]
        name = os.path.basename(path)

        def worker() -> None:
            self._emit({"t": "file_started", "name": name, "size": size, "id": fid})
            try:
                self._seal({"t": P.I_FILE_OFFER, "id": fid, "name": name, "size": size}, "file")
                sent = 0
                seq = 0
                with open(path, "rb") as fh:
                    while not self._stop.is_set():
                        chunk = fh.read(P.CHUNK_SIZE)
                        if not chunk:
                            break
                        self._seal(
                            {
                                "t": P.I_FILE_CHUNK,
                                "id": fid,
                                "seq": seq,
                                "b64": base64.b64encode(chunk).decode("ascii"),
                            },
                            "file",
                        )
                        seq += 1
                        sent += len(chunk)
                        pct = (sent / size * 100) if size else 100.0
                        self._emit({"t": "file_progress", "id": fid, "name": name, "pct": pct, "sent": sent, "size": size})
                        if progress_cb:
                            progress_cb(pct)
                self._seal({"t": P.I_FILE_END, "id": fid}, "file")
                self._emit({"t": "file_sent", "id": fid, "name": name, "size": size})
            except OSError as exc:
                self._seal({"t": P.I_FILE_CANCEL, "id": fid}, "file")
                self._emit({"t": "error", "message": f"File send failed: {exc}"})

        threading.Thread(target=worker, daemon=True, name="cc2-file-send").start()

    def set_max_users(self, value: int) -> None:
        if not self.is_host:
            self._emit({"t": "error", "message": "Only the host can change the member cap"})
            return
        self._raw({"t": P.ADMIN, "action": "set_max", "value": int(value), "token": self._admin_token})

    def kick(self, user: str) -> None:
        if self.is_host:
            self._raw({"t": P.ADMIN, "action": "kick", "user": user, "token": self._admin_token})

    def close_room(self) -> None:
        if self.is_host:
            self._raw({"t": P.ADMIN, "action": "close", "token": self._admin_token})

    def _dispatch(self, obj: dict, history: bool = False) -> None:
        kind = obj.get("t")
        if kind == P.ENC:
            self._on_ciphertext(obj, history)
        elif kind == P.ROOM:
            self.max_users = int(obj.get("max_users", self.max_users))
            self.members = list(obj.get("members", []))
            if obj.get("common"):
                self.common = list(obj["common"])
            self._emit({"t": "room", "max_users": self.max_users, "members": self.members, "users": obj.get("users")})
        elif kind == P.SYS:
            self._emit({"t": "sys", "text": obj.get("text", ""), "history": history})
        elif kind == P.ERROR:
            if obj.get("code") in ("kicked", "full", "password"):
                self.connected = False
            self._emit({"t": "error", "message": obj.get("message", "Server error"), "code": obj.get("code")})
        elif kind == P.ROOM_INFO:
            self.room = obj
        elif kind == P.PEERS:
            self.members = list(obj.get("members", []))
            self._emit({"t": "room", "max_users": self.max_users, "members": self.members})

    def _on_ciphertext(self, frame: dict, history: bool) -> None:
        if self.key is None:
            return
        sender = frame.get("from", "?")
        try:
            inner = crypto.open_json(self.key, frame["d"])
        except crypto.CryptoError as exc:
            if not history:
                self._emit({"t": "error", "message": f"Could not decrypt a message: {exc}"})
            return
        kind = inner.get("t")
        if kind == P.I_MSG:
            self._emit(
                {
                    "t": "message",
                    "from": sender,
                    "text": inner.get("text", ""),
                    "own": False,
                    "history": history,
                    "ts": frame.get("ts", P.now()),
                }
            )
        elif kind == P.I_TYPING:
            self._emit({"t": "typing", "from": sender, "on": bool(inner.get("on"))})
        elif kind == P.I_FILE_OFFER:
            self._on_file_offer(sender, inner, history)
        elif kind == P.I_FILE_CHUNK:
            self._on_file_chunk(inner, history)
        elif kind == P.I_FILE_END:
            self._on_file_end(inner, history)
        elif kind == P.I_FILE_CANCEL:
            self._cancel_incoming(inner.get("id", ""))

    def _on_file_offer(self, sender: str, inner: dict, history: bool) -> None:
        fid = str(inner.get("id", ""))
        name = os.path.basename(str(inner.get("name", "file.bin")).replace("\\", "/"))
        size = int(inner.get("size", 0) or 0)
        if not fid:
            return
        target = cfg.safe_filename(name)
        try:
            handle = open(target, "wb")
        except OSError as exc:
            self._emit({"t": "error", "message": f"Cannot save {name}: {exc}"})
            return
        self._incoming[fid] = {"name": name, "size": size, "path": str(target), "fh": handle, "got": 0, "from": sender, "seq": 0}
        self._emit({"t": "file_incoming", "id": fid, "name": name, "size": size, "from": sender, "history": history})

    def _on_file_chunk(self, inner: dict, history: bool) -> None:
        rec = self._incoming.get(str(inner.get("id", "")))
        if not rec:
            return
        try:
            data = base64.b64decode(inner.get("b64", ""))
        except (ValueError, TypeError):
            return
        rec["fh"].write(data)
        rec["got"] += len(data)
        rec["seq"] += 1
        pct = (rec["got"] / rec["size"] * 100) if rec["size"] else 100.0
        if rec["seq"] % 4 == 0 or pct >= 100:
            self._emit({"t": "file_progress", "id": inner.get("id"), "name": rec["name"], "pct": pct, "receiving": True})

    def _on_file_end(self, inner: dict, history: bool) -> None:
        fid = str(inner.get("id", ""))
        rec = self._incoming.pop(fid, None)
        if not rec:
            return
        try:
            rec["fh"].flush()
            rec["fh"].close()
        except OSError:
            pass
        self._emit(
            {
                "t": "file_saved",
                "id": fid,
                "name": rec["name"],
                "path": rec["path"],
                "size": rec["got"],
                "from": rec["from"],
                "history": history,
            }
        )

    def _cancel_incoming(self, fid: str) -> None:
        rec = self._incoming.pop(fid, None)
        if rec:
            try:
                rec["fh"].close()
                os.remove(rec["path"])
            except OSError:
                pass
            self._emit({"t": "error", "message": f"Transfer of {rec['name']} was cancelled"})
