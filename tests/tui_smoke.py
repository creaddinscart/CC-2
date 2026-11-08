# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def click(x: int, y: int) -> bytes:
    press = b"\x1b[M" + bytes([32, 33 + x, 33 + y])
    release = b"\x1b[M" + bytes([35, 33 + x, 33 + y])
    return press + release


def main() -> int:
    if sys.platform == "win32":
        print("pty test is Unix-only; run cc2_cli.py manually on Windows.")
        return 0
    home = tempfile.mkdtemp(prefix="cc2-tui-smoke-")
    env = os.environ.copy()
    env.update(HOME=home, TERM="xterm-256color", LANG="en_US.UTF-8")
    master, slave = pty.openpty()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "cc2_cli.py")],
        stdin=slave, stdout=slave, stderr=slave, env=env, cwd=str(ROOT), close_fds=True,
    )
    os.close(slave)
    chunks: list[bytes] = []

    def drain(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    chunks.append(os.read(master, 65536))
                except OSError:
                    return

    def seen(text: str) -> bool:
        return text in b"".join(chunks).decode("utf-8", "ignore")

    passed = failed = 0

    def check(label: str, ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  [ok]   {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    try:
        drain(0.8)
        check("first-run screen renders", seen("CC-2.0") and seen("username"))
        os.write(master, b"Alice\r")
        drain(1.2)
        check("username -> main menu", seen("Main menu"))
        os.write(master, click(10, 11))
        drain(1.2)
        check("mouse click opens create-room form", seen("Create a room"))
        os.write(master, b"\x1b")
        drain(2.0)
        check("ESC returns to menu", seen("Main menu"))
        os.write(master, click(42, 11))
        drain(1.2)
        check("mouse click opens FRP exit dialog", seen("FRP exit / public address"))
        os.write(master, b"\x1b")
        drain(2.0)
        os.write(master, click(26, 11))
        drain(1.2)
        check("mouse click opens join-room form", seen("Join a room"))
        os.write(master, b"\x1b")
        drain(2.0)
        os.write(master, b"\x1b")
        drain(2.0)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        text = b"".join(chunks).decode("utf-8", "ignore")
        check("clean exit", proc.returncode == 0, )
        check("no traceback", "Traceback" not in text)
        check("credits visible", "Creaddinscart Teams" in text)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)

    print(f"\nRESULT: {passed} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
