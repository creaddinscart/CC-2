# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import re
from dataclasses import dataclass

from . import protocol as P
from .netdetect import format_endpoint

SAFE_HOST = re.compile(r"^[A-Za-z0-9._:%\[\]-]+$")


class FRPError(Exception):
    pass


def _port(value, label: str) -> int:
    text = str(value).strip()
    if not text.isdigit():
        raise FRPError(f"{label} must be a number between 1 and 65535")
    number = int(text)
    if not 1 <= number <= 65535:
        raise FRPError(f"{label} must be between 1 and 65535")
    return number


def _host(value) -> str:
    text = str(value or "").strip()
    if not text:
        raise FRPError("An FRP server address is required")
    if not SAFE_HOST.match(text) or any(c in text for c in "\"'\\\r\n\t "):
        raise FRPError("The FRP server address contains unsupported characters")
    return text


def split_address(text: str) -> tuple[str, int | None]:
    raw = str(text or "").strip()
    if not raw:
        raise FRPError("An address is required")
    for scheme in ("frp://", "tcp://", "cc2://"):
        if raw.lower().startswith(scheme):
            raw = raw[len(scheme):]
            break
    raw = raw.rstrip("/")
    host = ""
    port_text: str | None = None
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            raise FRPError("An IPv6 address must be written as [address]:port")
        host = raw[1:end]
        rest = raw[end + 1:]
        if rest:
            if not rest.startswith(":"):
                raise FRPError("An IPv6 address must be written as [address]:port")
            port_text = rest[1:]
    elif raw.count(":") == 1:
        host, _, port_text = raw.partition(":")
    else:
        host = raw
    host = _host(host)
    if port_text in (None, ""):
        return host, None
    return host, _port(port_text, "Port")


def parse_address(text: str, default_port: int | None = None) -> tuple[str, int]:
    host, port = split_address(text)
    if port is None:
        if default_port is None:
            raise FRPError("A port is required")
        return host, _port(default_port, "Port")
    return host, port


def bind_ip_for_tunnel(ip: str = "127.0.0.1") -> str:
    return "::" if ":" in ip else "0.0.0.0"


@dataclass
class FRPConfig:
    server_addr: str
    remote_port: int
    local_port: int

    def __post_init__(self) -> None:
        self.server_addr = _host(self.server_addr)
        self.remote_port = _port(self.remote_port, "Remote port")
        self.local_port = _port(self.local_port, "Local port")

    @classmethod
    def from_endpoint(cls, endpoint: str, local_port: int) -> FRPConfig:
        host, port = parse_address(endpoint)
        return cls(server_addr=host, remote_port=port, local_port=local_port)

    @property
    def endpoint(self) -> str:
        return format_endpoint(self.server_addr, self.remote_port)

    @property
    def local_endpoint(self) -> str:
        return format_endpoint("127.0.0.1", self.local_port)

    def as_dict(self) -> dict:
        return {
            "server_addr": self.server_addr,
            "remote_port": self.remote_port,
            "local_port": self.local_port,
            "endpoint": self.endpoint,
        }

    def probe_exit(self, timeout: float = 4.0) -> dict | None:
        return P.probe_room(self.server_addr, self.remote_port, timeout)

    def describe(self) -> str:
        return f"{self.local_endpoint} -> {self.endpoint}"
