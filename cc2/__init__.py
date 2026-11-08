# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from .brand import APP_NAME, APP_VERSION, SITE_NAME, BUILDERS, CREDIT, FOOTER, TITLE
from .frp import FRPConfig, FRPError, parse_address, split_address

__version__ = APP_VERSION
__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "SITE_NAME",
    "BUILDERS",
    "CREDIT",
    "FOOTER",
    "TITLE",
    "FRPConfig",
    "FRPError",
    "parse_address",
    "split_address",
]
