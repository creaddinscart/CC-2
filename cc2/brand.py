# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


APP_NAME = "CC-2.0"
APP_VERSION = "1.0.0"
SITE_NAME = "ChatClient"
PROTOCOL = "cc2-e2e/1"

BUILDER_PRIMARY = "Creaddinscart Teams"
BUILDER_PARTNER = "CC Team"
BUILDERS = f"{BUILDER_PRIMARY} x {BUILDER_PARTNER}"
CREDIT = f"Jointly built by {BUILDER_PRIMARY} & {BUILDER_PARTNER}"

TITLE = f"{APP_NAME} - {SITE_NAME}"
FOOTER = f"{APP_NAME} | {SITE_NAME} | {CREDIT}"

BANNER = r"""
   ____ ____     ___    ____   ____
  / ___/ ___|   / _ \  |___ \ |___ \
 | |  | |      | | | |   __) |  __) |
 | |__| |___   | |_| |  / __/  / __/
  \____\____|   \___/  |_____||_____|
"""

TAGLINE = "Private rooms. Direct connections. End-to-end encrypted."
WEBSITE = "ChatClient"

TRANSPORTS = [
    ("ipv6", "IPv6 global address (preferred)"),
    ("ipv4_public", "Public IPv4 address / port forwarding"),
    ("vpn", "VPN / Radmin VPN virtual adapter"),
    ("lan", "Local area network (LAN)"),
    ("localhost", "This computer only (loopback)"),
    ("custom", "Custom address (enter manually)"),
]
