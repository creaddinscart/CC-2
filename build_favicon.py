#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent

GREEN = (42, 174, 103, 255)
BACK = (138, 219, 187, 255)
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)
SUPERSAMPLE = 4

SVG = """<!-- This Source Code Form is subject to the terms of the Mozilla Public
   - License, v. 2.0. If a copy of the MPL was not distributed with this
   - file, You can obtain one at https://mozilla.org/MPL/2.0/.
   -
   - Copyright (c) 2026 Creaddinscart Teams & CC Team
   - SPDX-License-Identifier: MPL-2.0 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="#2aae67"/>
  <rect x="4" y="4" width="20" height="16" rx="3.5" fill="#8adbbb"/>
  <path d="M11 19 6.4 24.4 6.4 19Z" fill="#8adbbb"/>
  <rect x="11.5" y="9" width="16.5" height="10.5" rx="3.5" fill="#ffffff"/>
  <path d="M20 19v4.5L14 19Z" fill="#ffffff"/>
  <path d="m16.6 11.8 2.6 2.4-2.6 2.4" fill="none" stroke="#2aae67" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M20.4 16.6h3" fill="none" stroke="#2aae67" stroke-width="1.4" stroke-linecap="round"/>
</svg>
"""


def render(size: int, detail: bool = True, opaque: bool = False) -> Image.Image:
    side = size * SUPERSAMPLE
    unit = side / 32.0
    image = Image.new("RGBA", (side, side), GREEN if opaque else TRANSPARENT)
    draw = ImageDraw.Draw(image)

    if not opaque:
        draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=7 * unit, fill=GREEN)

    draw.rounded_rectangle((4 * unit, 4 * unit, 24 * unit, 20 * unit), radius=3.5 * unit, fill=BACK)
    draw.polygon([(11 * unit, 19 * unit), (6.4 * unit, 24.4 * unit), (6.4 * unit, 19 * unit)], fill=BACK)
    draw.rounded_rectangle((11.5 * unit, 9 * unit, 28 * unit, 19.5 * unit), radius=3.5 * unit, fill=WHITE)
    draw.polygon([(20 * unit, 19 * unit), (20 * unit, 23.5 * unit), (14 * unit, 19 * unit)], fill=WHITE)

    if detail:
        width = max(1, round(1.4 * unit))
        draw.line(
            [(16.6 * unit, 11.8 * unit), (19.2 * unit, 14.2 * unit), (16.6 * unit, 16.6 * unit)],
            fill=GREEN,
            width=width,
            joint="curve",
        )
        draw.line([(20.4 * unit, 16.6 * unit), (23.4 * unit, 16.6 * unit)], fill=GREEN, width=width)

    return image.resize((size, size), Image.LANCZOS)


def write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    blobs = [(size, (ROOT / f"favicon-{size}.png").read_bytes()) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for size, data in blobs:
        entries += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(data for _, data in blobs))


def main() -> None:
    (ROOT / "favicon.svg").write_text(SVG, encoding="utf-8")
    for size in (16, 32, 48):
        render(size, detail=size >= 32).save(ROOT / f"favicon-{size}.png")
    render(180, detail=True, opaque=True).convert("RGB").save(ROOT / "apple-touch-icon.png")
    write_ico(ROOT / "favicon.ico", (16, 32, 48))
    names = ("favicon.svg", "favicon-16.png", "favicon-32.png", "favicon-48.png", "apple-touch-icon.png", "favicon.ico")
    for name in names:
        print(f"{name:24s} {(ROOT / name).stat().st_size:6d} B")


if __name__ == "__main__":
    main()
