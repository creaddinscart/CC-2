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
from cc2.server import RoomConfig, RoomError, RoomServer


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} / {SITE_NAME} headless room server")
    parser.add_argument("--name", default="CC-2.0 Room")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--ip", help="advertised IP (default: auto-detected preferred address)")
    parser.add_argument("--password", help="room password; prompted if omitted")
    parser.add_argument("--max-users", type=int, default=8)
    parser.add_argument("--user", default="Host", help="host display name")
    parser.add_argument("--list-addresses", action="store_true", help="show detected addresses and exit")
    args = parser.parse_args()

    opts = netdetect.local_addresses(include_wan=True)
    if args.list_addresses:
        print(f"\n{APP_NAME} / {SITE_NAME} - detected addresses (priority order)\n")
        for o in opts:
            print(f"  {o.kind:<12} {o.ip:<40} {o.label:<22} {o.note}")
        print(f"\n  {netdetect.transport_note(opts)}\n")
        return 0

    ip = args.ip.strip().strip("[]") if args.ip else (netdetect.recommended(opts).ip if netdetect.recommended(opts) else "127.0.0.1")
    password = args.password or getpass.getpass("Room password (derives the encryption key): ")
    if not password:
        print("A password is required.")
        return 1
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.")
        return 1

    conf = RoomConfig(
        name=args.name,
        port=args.port,
        advertise_ip=ip,
        bind_ip=netdetect.bind_address_for(ip),
        password=password,
        max_users=max(1, min(256, args.max_users)),
        host_user=args.user,
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
    print(f"  Endpoint  : {conf.endpoint}")
    print(f"  Transport : {ip}  ({netdetect.recommended(opts).label if netdetect.recommended(opts) else 'custom'})")
    print(f"  Bind      : {conf.bind_ip}:{conf.port}")
    print(f"  Cap       : {conf.max_users} members")
    print(f"  Cipher    : {'AES-256-GCM' if has_aes_gcm() else 'HMAC-SHA256-CTR + HMAC'}")
    print(f"  Host      : {conf.host_user}")
    print(f"\n  Host admin token (keep private): {conf.admin_token}")
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
