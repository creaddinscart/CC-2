#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import http.server
import io
import json
import zipfile
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "docs" / "page.html"
OUTPUT = ROOT / "index.html"
RELEASE_ZIP = ROOT / "release" / "CC-2.0.zip"
RELEASE_DIR = ROOT / "release" / "CC-2.0"

EXCLUDE_DIRS = {
    ".git",
    ".workbuddy",
    ".venv",
    "__pycache__",
    "docs",
    "node_modules",
}
EXCLUDE_FILES = {".DS_Store", ".gitignore", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}

ROOT_ORDER = (
    "README.md",
    "USAGE.md",
    "LICENSE",
    "NOTICE",
    "requirements.txt",
    "launch.py",
    "cc2_cli.py",
    "cc2_server.py",
    "build_release.py",
    "build_docs.py",
    "CC-2.0.command",
    "CC-2.0.sh",
    "CC-2.0.bat",
    "index.html",
)

NOTES = {
    "README.md": "Project overview and architecture",
    "USAGE.md": "Full step-by-step user guide",
    "LICENSE": "Mozilla Public License 2.0 full text",
    "NOTICE": "Copyright and third-party notices",
    "requirements.txt": "Optional dependencies",
    "launch.py": "Unified three-mode launcher",
    "cc2_cli.py": "Mouse-clickable curses terminal client",
    "cc2_server.py": "Headless room server entry point",
    "build_release.py": "Rebuild the release folder and ZIP",
    "build_docs.py": "Generate this page and serve the download root",
    "CC-2.0.command": "macOS double-click launcher",
    "CC-2.0.sh": "Linux launcher",
    "CC-2.0.bat": "Windows launcher",
    "index.html": "This documentation and download page",
    "cc2/__init__.py": "Public package exports",
    "cc2/brand.py": "Application name, version and credits",
    "cc2/crypto.py": "Key derivation and authenticated encryption",
    "cc2/protocol.py": "Framing, constants and room probe",
    "cc2/netdetect.py": "IPv6, IPv4, VPN and LAN discovery",
    "cc2/config.py": "Local username and preferences",
    "cc2/server.py": "Temporary room server and ciphertext relay",
    "cc2/client.py": "Client network layer and file transfer",
    "tests/selftest.py": "27 core protocol and encryption checks",
    "tests/tui_smoke.py": "8 pseudo-terminal mouse interaction checks",
    "release/CC-2.0.zip": "Ready-to-run Terminal Edition archive",
    "release/CC-2.0/START-HERE.md": "Quick start inside the release package",
    "release/CC-2.0/README.md": "Release overview",
    "release/CC-2.0/USAGE.md": "Release user guide",
    "release/CC-2.0/cc2_cli.py": "Release terminal client",
    "release/CC-2.0/cc2_server.py": "Release headless server",
    "release/CC-2.0/launch.py": "Release launcher",
}

RELEASE_LAUNCHERS = {
    "CC-2.0.command": "macOS launcher",
    "CC-2.0.sh": "Linux launcher",
    "CC-2.0.bat": "Windows launcher",
}


def human(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def note_for(rel: str) -> str:
    if rel in NOTES:
        return NOTES[rel]
    if rel.startswith("release/CC-2.0/"):
        name = rel.rsplit("/", 1)[-1]
        if name in RELEASE_LAUNCHERS:
            return RELEASE_LAUNCHERS[name]
        if rel.startswith("release/CC-2.0/cc2/"):
            return "Release package core module"
        return "Release package file"
    return "Project source file"


def sort_key(item: dict) -> tuple:
    rel = item["path"]
    parts = rel.split("/")
    if len(parts) == 1:
        rank = ROOT_ORDER.index(rel) if rel in ROOT_ORDER else len(ROOT_ORDER) + 1
        return (0, rank, rel)
    if parts[0] == "cc2":
        return (1, 0, rel)
    if parts[0] == "tests":
        return (2, 0, rel)
    if rel == "release/CC-2.0.zip":
        return (3, 0, rel)
    if parts[0] == "release":
        return (4, 0, rel)
    return (5, 0, rel)


def collect() -> list[dict]:
    items: list[dict] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts[:-1]):
            continue
        if rel.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES:
            continue
        size = path.stat().st_size
        items.append(
            {
                "path": rel.as_posix(),
                "size": human(size),
                "bytes": size,
                "note": note_for(rel.as_posix()),
                "hi": rel.as_posix() == "release/CC-2.0.zip",
            }
        )
    return sorted(items, key=sort_key)


def build() -> list[dict]:
    items = collect()
    release_count = sum(1 for item in items if item["path"].startswith("release/CC-2.0/"))
    total = sum(item["bytes"] for item in items)
    values = {
        "{{MANIFEST}}": json.dumps(items, ensure_ascii=True, separators=(",", ":")),
        "{{FILE_COUNT}}": str(len(items)),
        "{{RELEASE_COUNT}}": str(release_count),
        "{{RELEASE_SIZE}}": human(RELEASE_ZIP.stat().st_size) if RELEASE_ZIP.is_file() else "0 B",
        "{{TOTAL_SIZE}}": human(total),
        "{{GENERATED}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{ROOT_NAME}}": ROOT.name,
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        html = html.replace(key, value)
    if "{{" in html:
        raise RuntimeError("unresolved template placeholder")
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Page          : {OUTPUT}")
    print(f"Root          : {ROOT}")
    print(f"Files listed  : {len(items)}")
    print(f"Release files : {release_count}")
    print(f"Release ZIP   : {values['{{RELEASE_SIZE}}']}")
    print(f"Page size     : {human(OUTPUT.stat().st_size)}")
    return items


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        return

    def translate_path(self, path: str) -> str:
        full = Path(super().translate_path(path)).resolve()
        if full != ROOT and ROOT in full.parents:
            parts = full.relative_to(ROOT).parts
            if any(part in EXCLUDE_DIRS for part in parts[:-1]) or full.name in EXCLUDE_FILES:
                return str(ROOT / "__blocked__")
        return str(full)

    def _safe(self, rel: str) -> Path | None:
        try:
            target = (ROOT / rel).resolve()
        except (OSError, ValueError):
            return None
        if target == ROOT or ROOT not in target.parents or not target.is_file():
            return None
        parts = target.relative_to(ROOT).parts
        if any(part in EXCLUDE_DIRS for part in parts[:-1]) or target.name in EXCLUDE_FILES:
            return None
        return target

    def _send(self, payload: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/__download_all.zip":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
                for item in collect():
                    bundle.write(ROOT / item["path"], f"{ROOT.name}/{item['path']}")
            self._send(buffer.getvalue(), f"{ROOT.name}-all.zip")
            return
        if parsed.path.startswith("/__download/"):
            rel = unquote(parsed.path[len("/__download/") :])
            target = self._safe(rel)
            if target is None:
                self.send_error(404, "file not available")
                return
            self._send(target.read_bytes(), target.name)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        super().do_HEAD()


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str, port: int) -> None:
    httpd = Server((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"Serving       : http://{shown}:{port}/")
    print(f"Download root : {ROOT}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the CC-2.0 documentation page and optional download server.")
    parser.add_argument("--serve", action="store_true", help="serve this folder as the download root")
    parser.add_argument("--host", default="127.0.0.1", help="bind address, use 0.0.0.0 to share on the LAN")
    parser.add_argument("--port", type=int, default=8787, help="local server port")
    args = parser.parse_args()
    build()
    if args.serve:
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
