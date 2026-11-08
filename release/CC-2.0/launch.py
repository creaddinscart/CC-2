#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

MODES = {
    "1": ("Terminal UI  (mouse-clickable, file picker)", "cc2_cli.py"),
    "2": ("Headless room server (no UI)", "cc2_server.py"),
    "3": ("Run self-tests", None),
}


def banner() -> None:
    print()
    print("   ____ ____     ___    ____   ____")
    print("  / ___/ ___|   / _ \\  |___ \\ |___ \\")
    print(" | |  | |      | | | |   __) |  __) |")
    print(" | |__| |___   | |_| |  / __/  / __/")
    print("  \\____\\____|   \\___/  |_____||_____|")
    print()
    print("   CC-2.0  /  ChatClient")
    print("   Terminal Edition")
    print("   Jointly built by Creaddinscart Teams & CC Team")
    print("   Private rooms - direct connections - end-to-end encrypted")
    print()


def tests() -> int:
    if not (ROOT / "tests" / "selftest.py").is_file():
        print("Self-tests are not included in this release package.")
        print("Download the source distribution to run the test suite.")
        return 0
    ok = True
    for script in ("tests/selftest.py", "tests/tui_smoke.py"):
        print(f"\n--- {script} ---")
        result = subprocess.call([PY, str(ROOT / script)], cwd=str(ROOT))
        ok = ok and result == 0
    print("\nAll tests passed." if ok else "\nSome tests failed.")
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    shortcut = {"--cli": "1", "--server": "2", "--test": "3"}
    choice = shortcut.get(args[0]) if args else None
    if args and choice is None and args[0] in MODES:
        choice = args[0]
    if choice == "3":
        return tests()
    if choice:
        label, script = MODES[choice]
        print(f"Starting: {label}\n")
        try:
            return subprocess.call([PY, str(ROOT / script)] + args[1:], cwd=str(ROOT))
        except KeyboardInterrupt:
            return 0

    banner()
    print("  Select a mode:\n")
    for key, (label, _) in MODES.items():
        print(f"    [{key}]  {label}")
    print("    [q]  Quit\n")
    while True:
        try:
            pick = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if pick in ("q", "quit", "exit", ""):
            return 0
        if pick == "3":
            tests()
            continue
        if pick in MODES:
            label, script = MODES[pick]
            print(f"\nStarting: {label}\n")
            try:
                return subprocess.call([PY, str(ROOT / script)], cwd=str(ROOT))
            except KeyboardInterrupt:
                return 0
        print("  Please enter 1-3 or q")


if __name__ == "__main__":
    sys.exit(main())
