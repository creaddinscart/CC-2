#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import getpass
import sys

from cc2 import netdetect
from cc2.brand import APP_NAME, CREDIT, SITE_NAME
from cc2.crypto import has_aes_gcm
from cc2.frp import FRPConfig, FRPError, split_address
from cc2.server import RoomConfig, RoomError, RoomServer


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} / {SITE_NAME} headless room server")
    parser.add_argument("--name", default="CC-2.0 Room")
    parser.add_argument("--port", type=int, default=9001, help="local listening port; use it as localPort in frpc")
    parser.add_argument("--ip", help="advertised local IP (default: auto-detected preferred address)")
    parser.add_argument("--bind", help="local bind address override (default: derived from --ip)")
    parser.add_argument("--password", help="room password; prompted if omitted")
    parser.add_argument("--max-users", type=int, default=8)
    parser.add_argument("--user", default="Host", help="host display name")
    parser.add_argument("--list-addresses", action="store_true", help="show detected addresses and exit")
    parser.add_argument("--frp", metavar="HOST:PORT", help="public FRP exit peers connect to, e.g. frp.example.com:25565")
    parser.add_argument("--frp-host", help="alternative to --frp: public FRP server address")
    parser.add_argument("--frp-port", type=int, default=0, help="alternative to --frp: remote port opened on frps")
    parser.add_argument("--frp-check", action="store_true", help="probe the FRP exit after the room starts")
    args = parser.parse_args()

    opts = netdetect.local_addresses(include_wan=True)
    best = netdetect.recommended(opts)
    if args.list_addresses:
        print(f"\n{APP_NAME} / {SITE_NAME} - detected addresses (priority order)\n")
        for o in opts:
            print(f"  {o.kind:<12} {o.ip:<40} {o.label:<22} {o.note}")
        print(f"\n  {netdetect.transport_note(opts)}\n")
        return 0

    ip = args.ip.strip().strip("[]") if args.ip else (best.ip if best else "127.0.0.1")
    password = args.password or getpass.getpass("Room password (derives the encryption key): ")
    if not password:
        print("A password is required.")
        return 1
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.")
        return 1

    if args.frp_port and not (args.frp or args.frp_host):
        print("--frp-port needs --frp or --frp-host.")
        return 1

    frp = None
    try:
        if args.frp:
            frp = FRPConfig.from_endpoint(args.frp, args.port)
        elif args.frp_host:
            host, embedded = split_address(args.frp_host)
            remote = args.frp_port or embedded
            if not remote:
                raise FRPError("A remote port is required: use --frp HOST:PORT or --frp-port")
            frp = FRPConfig(server_addr=host, remote_port=remote, local_port=args.port)
    except FRPError as exc:
        print(f"Invalid FRP exit: {exc}")
        return 1

    bind = args.bind.strip() if args.bind else ("0.0.0.0" if frp else netdetect.bind_address_for(ip))
    conf = RoomConfig(
        name=args.name,
        port=args.port,
        advertise_ip=ip,
        bind_ip=bind,
        password=password,
        max_users=max(1, min(256, args.max_users)),
        host_user=args.user,
        frp=frp,
    )
    server = RoomServer(conf)
    try:
        server.start()
    except RoomError as exc:
        print(f"Cannot start room: {exc}")
        return 1

    print(f"\n  {APP_NAME} / {SITE_NAME}")
    print(f"  {CREDIT}\n")
    print(f"  Room      : {conf.name}")
    print(f"  Local     : {conf.bind_ip}:{conf.port}")
    print(f"  Transport : {ip}  ({'custom' if args.ip else (best.label if best else 'custom')})")
    if frp:
        print(f"  FRP exit  : {frp.endpoint}   <-- give THIS to peers")
        print(f"  Tunnel    : {frp.describe()}")
        print(f"  Join as   : host {frp.server_addr} / port {frp.remote_port}")
    else:
        print(f"  Endpoint  : {conf.endpoint}")
    print(f"  Cap       : {conf.max_users} members")
    print(f"  Cipher    : {'AES-256-GCM' if has_aes_gcm() else 'HMAC-SHA256-CTR + HMAC'}")
    print(f"  Host      : {conf.host_user}")
    print(f"\n  Host admin token (keep private): {conf.admin_token}")

    if frp:
        print("\n  Configure the tunnel in YOUR OWN frpc client, the same way as a Minecraft server:")
        print(f"    localPort  = {conf.port}")
        print(f"    remotePort = {frp.remote_port}")
        print("  Use a plain tcp proxy and keep frpc running while the room is open.")

    if frp and args.frp_check:
        info = frp.probe_exit(4.0)
        if info:
            print(f"\n  FRP exit is live: {info.get('name')} ({info.get('users')}/{info.get('max_users')} members)")
        else:
            print("\n  FRP exit did not answer. Check frpc, the remote port on frps and the firewall.")
            print("  Some routers block hairpin connections, so this check can fail even when peers can join.")

    if frp:
        print(f"\n  Peers: enter {frp.server_addr} + port {frp.remote_port}, check the room, then enter the password.")
        print("  The FRP server only relays ciphertext. In FRP mode host rights need the admin token.")
    else:
        print("  Peers: enter the IP + port, check the room, then enter the password.")
        print("  A client joining from 127.0.0.1 with the host username is host automatically.")
    print("\n  Press Ctrl+C to close the room.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Room closed.")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
