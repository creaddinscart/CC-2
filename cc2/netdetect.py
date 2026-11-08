# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import ipaddress
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, asdict

_WAN_CACHE: dict = {"value": None, "at": 0.0}

VPN_V4_NETS = ("26.0.0.0/8", "5.0.0.0/8", "25.0.0.0/8", "100.64.0.0/10")
VPN_IFACE_HINTS = ("radmin", "hamachi", "zerotier", "tailscale", "wireguard", "tun", "tap", "vpn", "ppp")

PRIORITY = {"ipv6": 0, "ipv4_public": 1, "vpn": 2, "lan": 3, "localhost": 4}


@dataclass
class AddressOption:
    ip: str
    kind: str
    label: str
    note: str
    score: int
    family: int

    def as_dict(self) -> dict:
        return asdict(self)


def _classify(ip: str) -> tuple[str, str, str] | None:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return None
    if addr.is_loopback:
        return "localhost", "Loopback", "Only this computer can join."
    if addr.is_unspecified:
        return None
    if addr.version == 6:
        a6 = ipaddress.IPv6Address(ip.split("%")[0])
        if a6.is_global and not a6.is_link_local and not a6.is_private:
            return "ipv6", "IPv6 Global", "RECOMMENDED - usually reachable without port forwarding."
        if a6.is_link_local:
            return "lan", "IPv6 Link-local", "Same network segment only; add %interface if needed."
        if a6.is_private:
            return "vpn", "IPv6 ULA / VPN", "Private IPv6 range, typical for VPN adapters."
        return "lan", "IPv6", "Local IPv6 address."

    v4 = ipaddress.IPv4Address(ip)
    for cidr in VPN_V4_NETS:
        if v4 in ipaddress.ip_network(cidr):
            if cidr == "26.0.0.0/8":
                return "vpn", "Radmin VPN", "Radmin VPN virtual adapter - peers must join the same network."
            return "vpn", "VPN / CGNAT", "Virtual adapter or carrier-grade NAT range."
    if v4.is_link_local:
        return "lan", "Link-local", "APIPA address, usually not usable."
    if v4.is_private:
        return "lan", "LAN (private IPv4)", "Same Wi-Fi / LAN only, unless you forward this port."
    return "ipv4_public", "Public IPv4", "Directly reachable if no firewall/NAT blocks the port."


def _outbound_ip(family: int) -> str | None:
    target = ("2001:4860:4860::8888", 9) if family == socket.AF_INET6 else ("8.8.8.8", 9)
    sock = None
    try:
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(0.4)
        sock.connect(target)
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        if sock:
            sock.close()


def _guarded(fn, timeout: float, default):
    box: queue.Queue = queue.Queue()

    def run() -> None:
        try:
            box.put(fn())
        except Exception:
            box.put(default)

    threading.Thread(target=run, daemon=True, name="cc2-netdetect").start()
    try:
        return box.get(timeout=timeout)
    except queue.Empty:
        return default


def _hostname_addresses() -> list[str]:
    out: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, 0, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    return out


def _system_addresses() -> list[str]:
    out: list[str] = []
    commands: list[list[str]] = []
    import sys

    if sys.platform == "win32":
        commands = [["ipconfig"]]
    elif sys.platform == "darwin":
        commands = [["ifconfig", "-a"]]
    else:
        commands = [["hostname", "-I"], ["ip", "-o", "addr", "show"]]
    pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
    for cmd in commands:
        try:
            text = subprocess.run(
                cmd, capture_output=True, text=True, timeout=1.5, check=False
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for token in pattern.findall(text):
            if token not in out:
                out.append(token)
    return out


def public_ipv4(timeout: float = 2.0, use_cache: bool = True) -> str | None:
    if use_cache and time.time() - _WAN_CACHE["at"] < 60:
        return _WAN_CACHE["value"]

    def fetch(url: str) -> str | None:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                value = resp.read(64).decode("ascii", "ignore").strip()
            if value and ipaddress.ip_address(value).version == 4:
                return value
        except Exception:
            pass
        return None

    urls = ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")
    found: queue.Queue[str] = queue.Queue()

    def worker(url: str) -> None:
        result = fetch(url)
        if result:
            found.put(result)

    for url in urls:
        threading.Thread(target=worker, args=(url,), daemon=True).start()
    try:
        value = found.get(timeout=timeout + 0.3)
    except queue.Empty:
        value = None
    _WAN_CACHE.update({"value": value, "at": time.time()})
    return value


def local_addresses(include_wan: bool = True) -> list[AddressOption]:
    raw: list[str] = []
    for candidate in (
        _guarded(lambda: _outbound_ip(socket.AF_INET6), 1.0, None),
        _guarded(lambda: _outbound_ip(socket.AF_INET), 1.0, None),
    ):
        if candidate and candidate not in raw:
            raw.append(candidate)
    discovered = (_guarded(_hostname_addresses, 1.5, []) or []) + (_guarded(_system_addresses, 2.0, []) or [])
    for candidate in discovered:
        if candidate and candidate not in raw:
            raw.append(candidate)
    for loopback in ("127.0.0.1", "::1"):
        if loopback not in raw:
            raw.append(loopback)

    options: dict[str, AddressOption] = {}
    for ip in raw:
        info = _classify(ip)
        if not info:
            continue
        kind, label, note = info
        family = 6 if ":" in ip else 4
        score = PRIORITY.get(kind, 9) * 10 + (0 if family == 6 else 1)
        options[ip] = AddressOption(ip, kind, label, note, score, family)

    if include_wan:
        wan = public_ipv4()
        if wan and wan not in options:
            options[wan] = AddressOption(
                wan,
                "ipv4_public",
                "WAN IPv4 (NAT)",
                "Your public IP - requires router port forwarding to this computer.",
                PRIORITY["ipv4_public"] * 10 + 2,
                4,
            )
    return sorted(options.values(), key=lambda o: (o.score, o.ip))


def recommended(options: list[AddressOption]) -> AddressOption | None:
    for kind in ("ipv6", "ipv4_public", "vpn", "lan", "localhost"):
        for opt in options:
            if opt.kind == kind:
                return opt
    return options[0] if options else None


def transport_note(options: list[AddressOption]) -> str:
    best = recommended(options)
    if not best:
        return "No addresses detected - enter an IP manually."
    if best.kind == "ipv6":
        return "IPv6 global address found - selected as the preferred transport."
    if best.kind == "ipv4_public":
        return "No global IPv6 - falling back to public IPv4."
    if best.kind == "vpn":
        return "No global IPv6 / public IPv4 - falling back to VPN (e.g. Radmin VPN)."
    if best.kind == "lan":
        return "No public address - using LAN. Peers must be on the same network or VPN."
    return "Only loopback is available - use LAN IP or a VPN to chat with others."


def bind_address_for(ip: str) -> str:
    if ":" in ip:
        return "::"
    if ip.startswith("127."):
        return "127.0.0.1"
    return "0.0.0.0"


def format_endpoint(ip: str, port: int) -> str:
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"


def vpn_interface_hint() -> str:
    return "Radmin VPN peers use the 26.x.x.x address shown inside the Radmin VPN client."
