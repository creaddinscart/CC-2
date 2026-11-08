#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "release"
PKG = OUT / "CC-2.0"

FILES = (
    "README.md",
    "USAGE.md",
    "LICENSE",
    "NOTICE",
    "requirements.txt",
    "launch.py",
    "cc2_cli.py",
    "cc2_server.py",
    "CC-2.0.command",
    "CC-2.0.sh",
    "CC-2.0.bat",
)
DIRS = ("cc2",)

START_HERE = """# CC-2.0 / ChatClient - Terminal Edition

Ready-to-run release package. Terminal only: no graphical desktop client and no web client.

Requirements: Python 3.9 or newer. Only the standard library is needed.

## Start

| Platform | Action |
| --- | --- |
| macOS | Double-click `CC-2.0.command` |
| Linux | `./CC-2.0.sh` |
| Windows | Double-click `CC-2.0.bat` |
| Any system | `python3 launch.py` |

Pick a mode: 1 Terminal UI, 2 Headless room server, 3 Self-tests.
You can also run `python3 cc2_cli.py` or `python3 cc2_server.py` directly.

## First session

1. Choose a username.
2. Host: **Create Room** with name, port, transport IP, password and member cap.
3. Peer: **Join Room** with IP + port, click **Check Room**, then enter the password.

Buttons, input fields, the transport list, the file browser and the member list
are all clickable with the mouse inside the terminal. TAB, arrows, ENTER and ESC
work as well. IPv6 global addresses are preferred; public IPv4, VPN / Radmin VPN
and LAN are selectable. All traffic is end-to-end encrypted.

## Optional

`python3 -m pip install -r requirements.txt` enables AES-256-GCM and, on Windows,
the mouse-driven terminal UI (windows-curses). The application works without it.

## Documentation

- `USAGE.md` - full step-by-step guide
- `README.md` - overview, architecture, tests, troubleshooting
- `LICENSE` - Mozilla Public License 2.0
- `NOTICE` - copyright and third-party notices

Jointly built by Creaddinscart Teams & CC Team.
"""


def build() -> None:
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)

    for name in FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, PKG / name)

    for name in DIRS:
        shutil.copytree(
            ROOT / name,
            PKG / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

    (PKG / "START-HERE.md").write_text(START_HERE, encoding="utf-8")

    archive = OUT / "CC-2.0.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(PKG.rglob("*")):
            if item.is_file() and "__pycache__" not in item.parts and item.suffix not in (".pyc", ".pyo"):
                bundle.write(item, item.relative_to(OUT))

    count = sum(1 for p in PKG.rglob("*") if p.is_file())
    print(f"Release folder : {PKG}")
    print(f"Release archive: {archive}")
    print(f"Files packaged : {count}")
    print(f"Archive size   : {archive.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build()
