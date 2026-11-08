# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path.home() / ".cc2"
CONFIG_FILE = CONFIG_DIR / "config.json"
DOWNLOAD_DIR = Path.home() / "Downloads" / "CC-2.0"

DEFAULTS = {
    "username": "",
    "last_host": "",
    "last_port": 9001,
    "last_room_name": "",
    "default_max_users": 8,
    "download_dir": str(DOWNLOAD_DIR),
    "preferred_kind": "auto",
    "frp_enabled": False,
    "frp_endpoint": "",
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        if CONFIG_FILE.exists():
            data.update(json.loads(CONFIG_FILE.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = dict(DEFAULTS)
        payload.update(data)
        fd, tmp = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix="cfg-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)
    except OSError:
        pass


def get_username() -> str:
    return str(load().get("username", "") or "")


def set_username(name: str) -> None:
    data = load()
    data["username"] = name.strip()
    save(data)


def downloads() -> Path:
    data = load()
    path = Path(str(data.get("download_dir") or DOWNLOAD_DIR)).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir())
    return path


def safe_filename(name: str) -> Path:
    base = os.path.basename(name.replace("\\", "/")).strip() or "file.bin"
    base = "".join(c for c in base if c not in "\x00\r\n")
    folder = downloads()
    target = folder / base
    if not target.exists():
        return target
    stem, suffix = os.path.splitext(base)
    for i in range(1, 1000):
        candidate = folder / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}-{os.getpid()}{suffix}"
