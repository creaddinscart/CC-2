# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import curses
import os
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field as dc_field

from cc2 import config as cfg
from cc2 import netdetect
from cc2.brand import APP_NAME, BANNER, CREDIT, FOOTER, SITE_NAME, TAGLINE
from cc2.client import ChatClient, ClientError
from cc2.crypto import has_aes_gcm
from cc2.server import RoomConfig, RoomServer, RoomError

MIN_W, MIN_H = 72, 22

M_CLICK = 0
for _name in ("BUTTON1_CLICKED", "BUTTON1_PRESSED", "BUTTON1_RELEASED", "BUTTON1_DOUBLE_CLICKED"):
    M_CLICK |= getattr(curses, _name, 0)
M_DOUBLE = getattr(curses, "BUTTON1_DOUBLE_CLICKED", 0)
M_WHEEL_UP = getattr(curses, "BUTTON4_PRESSED", 0) or 0x00080000
M_WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0) or 0x01000000


def dwidth(text: str) -> int:
    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def clip(text: str, width: int) -> str:
    out, used = [], 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + step > width:
            break
        out.append(ch)
        used += step
    return "".join(out)


def wrap(text: str, width: int) -> list[str]:
    if not text:
        return [""]
    lines, current, used = [], [], 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + step > width:
            lines.append("".join(current))
            current, used = [], 0
        current.append(ch)
        used += step
    lines.append("".join(current))
    return lines


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


@dataclass
class Field:
    label: str
    value: str = ""
    y: int = 0
    x: int = 0
    w: int = 28
    secret: bool = False
    hint: str = ""
    pos: int = 0

    def __post_init__(self):
        self.pos = len(self.value)

    @property
    def shown(self) -> str:
        text = "*" * len(self.value) if self.secret else self.value
        visible = max(1, self.w - 2)
        cursor = self.pos if not self.secret else len(text)
        start = max(0, dwidth(text[:cursor]) - visible + 1) if dwidth(text) > visible else 0
        chars, used = [], 0
        for ch in text:
            step = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used >= start:
                chars.append(ch)
            used += step
            if dwidth("".join(chars)) >= visible:
                break
        return clip("".join(chars), visible)

    def insert(self, ch: str) -> None:
        self.value = self.value[: self.pos] + ch + self.value[self.pos :]
        self.pos += len(ch)

    def backspace(self) -> None:
        if self.pos > 0:
            self.value = self.value[: self.pos - 1] + self.value[self.pos :]
            self.pos -= 1

    def delete(self) -> None:
        if self.pos < len(self.value):
            self.value = self.value[: self.pos] + self.value[self.pos + 1 :]


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.h = self.w = 0
        self.hits: list[tuple[int, int, int, int, object]] = []
        self.fields: list[Field] = []
        self.focus: Field | None = None
        self.status = ""
        self.status_ts = 0.0
        self._last_click = 0.0
        self.username = cfg.get_username()
        self.addresses = netdetect.local_addresses(include_wan=False)
        self._addr_lock = threading.Lock()
        self.selected: netdetect.AddressOption | None = None
        self.custom_ip = ""
        self.addr_scroll = 0
        self.addr_pick = False
        self.client: ChatClient | None = None
        self.server: RoomServer | None = None
        self.messages: list[tuple[str, int]] = []
        self.members: list[str] = []
        self.max_users = 8
        self.typing: dict[str, float] = {}
        self.scroll = 0
        self.is_host = False
        self.room_name = ""
        self.room_endpoint = ""
        self.probed: dict | None = None
        self.file_dir = str(cfg.downloads().parent if cfg.downloads().name == "CC-2.0" else os.path.expanduser("~"))
        self.file_selected = ""
        self.file_items: list[tuple[str, bool]] = []
        self.file_scroll = 0
        self.last_input = 0.0
        self.typing_active = False
        self.peer_typing = ""
        self.cipher_mode = ""
        self._colors: dict[str, int] = {}

    def setup(self) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.keypad(True)
        self.stdscr.timeout(120)
        try:
            curses.start_color()
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        for idx, fg in enumerate(
            (curses.COLOR_CYAN, curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_MAGENTA, curses.COLOR_WHITE, curses.COLOR_RED),
            start=1,
        ):
            try:
                curses.init_pair(idx, fg, bg)
            except curses.error:
                pass
        for key, idx in (("accent", 1), ("ok", 2), ("warn", 3), ("host", 4), ("dim", 5), ("err", 6)):
            self._colors[key] = curses.color_pair(idx)
        self._colors["btn"] = curses.color_pair(1) | curses.A_BOLD
        self._colors["field"] = curses.color_pair(5)
        try:
            mask = curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION
            actual = curses.mousemask(mask)
            if actual == 0:
                curses.mousemask(curses.ALL_MOUSE_EVENTS)
        except curses.error:
            self.status = "Mouse support unavailable in this terminal - use the keyboard."
        threading.Thread(target=self._load_wan, daemon=True).start()

    def _load_wan(self) -> None:
        try:
            opts = netdetect.local_addresses(include_wan=True)
            with self._addr_lock:
                self.addresses = opts
        except Exception:
            pass

    def opts(self) -> list[netdetect.AddressOption]:
        with self._addr_lock:
            return list(self.addresses)

    def color(self, name: str) -> int:
        return self._colors.get(name, 0)

    def draw(self, y: int, x: int, text: str, attr: int = 0) -> None:
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w - 1:
            return
        text = clip(str(text), w - x - 1)
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def frame(self, title: str = "") -> None:
        self.h, self.w = self.stdscr.getmaxyx()
        self.hits = []
        self.stdscr.erase()
        try:
            self.stdscr.border()
        except curses.error:
            pass
        self.draw(0, 3, f" {APP_NAME} - {SITE_NAME} ", self.color("accent") | curses.A_BOLD)
        if title:
            self.draw(0, self.w - len(title) - 7, f" {title} ", self.color("dim"))
        if self.h < MIN_H or self.w < MIN_W:
            self.draw(self.h // 2, 3, f"Terminal too small - please resize to at least {MIN_W}x{MIN_H}")
            self.stdscr.refresh()
            return
        self.draw(self.h - 1, 3, f" {clip(CREDIT, self.w - 8)} ", self.color("dim"))

    def button(self, y: int, x: int, label: str, action, attr: int | None = None) -> int:
        text = f"[ {label} ]"
        self.draw(y, x, text, attr if attr is not None else self.color("btn"))
        self.hits.append((x, y, x + len(text) - 1, y, action))
        return x + len(text) + 2

    def label(self, y: int, x: int, text: str, attr: int = 0) -> None:
        self.draw(y, x, text, attr)

    def field(self, f: Field, attr: int | None = None) -> None:
        focused = self.focus is f
        self.draw(f.y, f.x, f.label + ":", self.color("accent") if focused else 0)
        bx = f.x + len(f.label) + 2
        shown = f.shown.ljust(f.w - 2)
        self.draw(f.y, bx, "[" + shown + "]", (self.color("btn") if focused else self.color("field")) | (curses.A_BOLD if focused else 0))
        self.hits.append((bx, f.y, bx + f.w - 1, f.y, ("focus", f)))
        if f.hint:
            self.draw(f.y, bx + f.w + 2, clip(f.hint, self.w - bx - f.w - 4), self.color("dim"))
        if f not in self.fields:
            self.fields.append(f)

    def footer_status(self) -> None:
        if time.time() - self.status_ts < 7 and self.status:
            self.draw(self.h - 3, 3, clip("* " + self.status, self.w - 8), self.color("warn"))

    def note(self, text: str, y: int | None = None) -> None:
        row = self.h - 4 if y is None else y
        self.draw(row, 3, clip(text, self.w - 8), self.color("dim"))

    def key(self):
        try:
            if hasattr(self.stdscr, "get_wch"):
                ch = self.stdscr.get_wch()
            else:
                ch = self.stdscr.getch()
                if ch == -1:
                    return None
                ch = chr(ch) if 32 <= ch <= 126 else ch
        except curses.error:
            return None
        except (ValueError, OverflowError):
            return None
        if isinstance(ch, str) and len(ch) == 1:
            code = ord(ch)
            if code in (8, 9, 10, 13, 27, 127):
                return 9 if code == 9 else (10 if code == 13 else code)
        return ch

    def handle_base(self, ch, back=None):
        if ch is None:
            return None
        if ch == curses.KEY_RESIZE:
            try:
                curses.update_lines_cols()
            except curses.error:
                pass
            return None
        if ch == curses.KEY_MOUSE:
            return self.handle_mouse()
        if ch == 27 and back:
            return back
        if ch == 9 or ch == curses.KEY_DOWN and not self.focus:
            self.cycle_focus(1)
            return None
        if ch == curses.KEY_BTAB:
            self.cycle_focus(-1)
            return None
        if ch == curses.KEY_UP and self.fields and self.focus:
            self.cycle_focus(-1)
            return None
        if ch == curses.KEY_DOWN and self.fields and self.focus:
            self.cycle_focus(1)
            return None
        if self.focus:
            f = self.focus
            if ch in (10, 13, curses.KEY_ENTER):
                return ("enter", f)
            if ch in (curses.KEY_BACKSPACE, 127, 8, "\x7f", "\b"):
                f.backspace()
                self.on_edit(f)
            elif ch == curses.KEY_DC:
                f.delete()
                self.on_edit(f)
            elif ch == curses.KEY_LEFT:
                f.pos = max(0, f.pos - 1)
            elif ch == curses.KEY_RIGHT:
                f.pos = min(len(f.value), f.pos + 1)
            elif ch == curses.KEY_HOME:
                f.pos = 0
            elif ch == curses.KEY_END:
                f.pos = len(f.value)
            elif isinstance(ch, str) and ch.isprintable() and ch not in "\t\n\r":
                f.insert(ch)
                self.on_edit(f)
        return None

    def on_edit(self, f: Field) -> None:
        self.last_input = time.time()
        if self.client and self.client.connected and f.label.lower().startswith("message"):
            self.typing_active = True
            self.client.send_typing(True)

    def cycle_focus(self, step: int) -> None:
        if not self.fields:
            return
        try:
            idx = self.fields.index(self.focus) if self.focus in self.fields else -1
        except ValueError:
            idx = -1
        self.focus = self.fields[(idx + step) % len(self.fields)]

    def handle_mouse(self):
        try:
            _, mx, my, _, state = curses.getmouse()
        except curses.error:
            return None
        if state & (M_WHEEL_UP | M_WHEEL_DOWN):
            return ("wheel", 1 if state & M_WHEEL_UP else -1)
        if not (state & M_CLICK):
            return None
        now = time.time()
        if now - self._last_click < 0.18:
            return None
        self._last_click = now
        for x1, y1, x2, y2, action in reversed(self.hits):
            if x1 <= mx <= x2 and y1 <= my <= y2:
                if isinstance(action, tuple) and action[0] == "focus":
                    self.focus = action[1]
                    return None
                if callable(action):
                    result = action()
                    return result if isinstance(result, str) else None
                if isinstance(action, tuple) and action[0] == "click":
                    return ("click", action[1], bool(state & M_DOUBLE))
                return action if isinstance(action, str) else ("action", action)
        return None

    def start_fields(self, fields: list[Field]) -> None:
        if self.fields != fields or self.focus not in fields:
            self.fields = list(fields)
            self.focus = fields[0] if fields else None

    def go_addresses(self, pick: bool) -> str:
        self.addr_pick = pick
        return "addresses"

    def say(self, text: str) -> None:
        self.status = text
        self.status_ts = time.time()

    def screen_username(self) -> str:
        f = Field("Your username", "", 0, 0, 24)
        while True:
            self.frame("First run")
            if self.h < MIN_H or self.w < MIN_W:
                ch = self.key()
                if ch in (27, "q"):
                    return "quit"
                continue
            for i, line in enumerate([l for l in BANNER.splitlines() if l.strip()][:4]):
                self.draw(2 + i, 5, line, self.color("accent") | curses.A_BOLD)
            self.draw(6, 5, f"{APP_NAME}  /  {SITE_NAME}   -   {TAGLINE}", self.color("btn") | curses.A_BOLD)
            self.draw(8, 5, "Before entering, pick a display name. It is stored locally in ~/.cc2/config.json.")
            f.y, f.x = 10, 6
            self.start_fields([f])
            self.field(f)
            x = self.button(12, 6, "Continue", lambda: "done")
            self.button(12, x, "Quit", lambda: "quit", self.color("dim"))
            self.draw(14, 6, "Tip: click any field or button - this terminal UI is fully mouse driven.", self.color("dim"))
            self.draw(15, 6, CREDIT, self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            result = self.handle_base(self.key())
            if isinstance(result, tuple) and result[0] == "enter":
                result = "done"
            if result == "done":
                name = f.value.strip()
                if not name:
                    self.say("Please enter a username.")
                    continue
                cfg.set_username(name[:24])
                self.username = name[:24]
                return "menu"
            if result == "quit":
                return "quit"

    def screen_menu(self) -> str:
        while True:
            self.frame("Main menu")
            if self.h < MIN_H or self.w < MIN_W:
                if self.key() in (27, "q"):
                    return "quit"
                continue
            self.start_fields([])
            self.draw(3, 4, f"{APP_NAME}   ::   {SITE_NAME}", self.color("btn") | curses.A_BOLD)
            self.draw(4, 4, TAGLINE, self.color("dim"))
            self.draw(6, 4, f"Signed in as : {self.username}", self.color("ok"))
            self.draw(7, 4, f"Cipher       : {'AES-256-GCM' if self.cipher_mode == 'v2' else 'HMAC-SHA256 CTR (stdlib)'}", self.color("dim"))
            self.draw(8, 4, f"Transport    : {netdetect.transport_note(self.opts())}", self.color("dim"))
            x = 6
            y = 11
            x = self.button(y, x, "Create Room", lambda: "create")
            x = self.button(y, x, "Join Room", lambda: "join")
            x = self.button(y + 2, 6, "Network Interfaces", lambda: self.go_addresses(False))
            self.button(y + 2, 30, "Change Username", lambda: "username", self.color("dim"))
            self.button(y + 2, 52, "Quit", lambda: "quit", self.color("dim"))
            self.draw(16, 6, "A room IS a temporary server on the creator's machine. Peers connect directly", self.color("dim"))
            self.draw(17, 6, "over IPv6, public IPv4, VPN (e.g. Radmin VPN), or LAN. No central server, no logs.", self.color("dim"))
            self.draw(19, 6, CREDIT, self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            result = self.handle_base(self.key(), back="quit")
            if result in ("create", "join", "addresses", "username", "quit"):
                return result

    def screen_addresses(self, pick: bool = False) -> str:
        while True:
            self.frame("Network interfaces")
            self.start_fields([])
            self.draw(2, 4, "Available addresses (click to select). IPv6 global is preferred.", self.color("accent"))
            opts = self.opts()
            top, bottom = 4, self.h - 8
            visible = max(1, bottom - top + 1)
            self.addr_scroll = max(0, min(self.addr_scroll, max(0, len(opts) - visible)))
            for i in range(visible):
                idx = self.addr_scroll + i
                y = top + i
                if idx >= len(opts):
                    break
                o = opts[idx]
                chosen = self.selected and self.selected.ip == o.ip
                mark = ">" if chosen else " "
                text = f"{mark} {o.kind:<11} {o.ip:<40} {o.label}"
                self.draw(y, 4, clip(text, self.w - 9), self.color("ok") if chosen else (self.color("btn") if o.kind == "ipv6" else 0))
                self.hits.append((4, y, min(self.w - 5, 4 + len(text)), y, ("click", ("addr", o), False)))
                self.draw(y, min(self.w - 34, 52), clip(o.note, 30), self.color("dim"))
            y = self.h - 6
            self.button(y, 4, "Rescan", lambda: "rescan")
            self.button(y, 16, "Custom IP", lambda: "custom")
            self.button(y, 32, "Back", lambda: "create" if pick else "menu", self.color("dim"))
            if self.selected:
                self.draw(y - 2, 4, f"Selected: {self.selected.ip} ({self.selected.label})", self.color("ok"))
            self.draw(y - 1, 4, netdetect.vpn_interface_hint(), self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            ch = self.key()
            result = self.handle_base(ch, back="create" if pick else "menu")
            if ch == curses.KEY_UP:
                self.addr_scroll = max(0, self.addr_scroll - 1)
            if ch == curses.KEY_DOWN:
                self.addr_scroll += 1
            if isinstance(result, tuple) and result[0] == "wheel":
                self.addr_scroll = max(0, self.addr_scroll - result[1])
            if isinstance(result, tuple) and result[0] == "click":
                self.selected = result[1][1]
                self.say(f"Transport set to {self.selected.ip}")
                if pick:
                    return "create"
            if result in ("create", "menu", "rescan", "custom"):
                if result == "rescan":
                    threading.Thread(target=self._load_wan, daemon=True).start()
                    self.say("Rescanning network interfaces in the background...")
                    continue
                if result == "custom":
                    ip = self.prompt_custom_ip()
                    if ip:
                        self.custom_ip = ip
                        self.selected = netdetect.AddressOption(ip, "custom", "Custom", "Manually entered address.", 99, 6 if ":" in ip else 4)
                        if pick:
                            return "create"
                    continue
                return result

    def prompt_custom_ip(self) -> str:
        f = Field("IP / hostname", self.custom_ip, 0, 0, 42)
        while True:
            self.frame("Custom address")
            self.draw(3, 4, "Enter the address other peers should connect to (IPv6, IPv4, or VPN IP).")
            f.y, f.x = 5, 6
            self.start_fields([f])
            self.field(f)
            x = self.button(7, 6, "Use this address", lambda: "done")
            self.button(7, x, "Cancel", lambda: "cancel", self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            result = self.handle_base(self.key(), back="cancel")
            if isinstance(result, tuple) and result[0] == "enter":
                result = "done"
            if result == "done":
                return f.value.strip().strip("[]")
            if result == "cancel":
                return ""

    def screen_create(self) -> str:
        saved = cfg.load()
        f_name = Field("Room name", str(saved.get("last_room_name") or "My Private Room"), 0, 0, 30)
        f_port = Field("Port", str(saved.get("last_port") or 9001), 0, 0, 12)
        f_pass = Field("Password", "", 0, 0, 24, secret=True)
        f_max = Field("Max users", str(saved.get("default_max_users") or 8), 0, 0, 8)
        if self.selected is None:
            self.selected = netdetect.recommended(self.opts())
        while True:
            self.frame("Create a room = start a temporary server")
            self.start_fields([f_name, f_port, f_pass, f_max])
            self.draw(2, 4, "The room lives only on your computer. Others connect directly to the address below.", self.color("dim"))
            f_name.y, f_name.x = 4, 6
            f_port.y, f_port.x = 5, 6
            f_pass.y, f_pass.x = 6, 6
            f_max.y, f_max.x = 7, 6
            for f in self.fields:
                self.field(f)
            self.draw(9, 6, "Transport:", self.color("accent"))
            label = f"{self.selected.ip}  -  {self.selected.label}" if self.selected else "click to choose"
            self.button(9, 17, label[:44], lambda: self.go_addresses(True))
            self.draw(10, 6, clip(netdetect.transport_note(self.opts()), self.w - 10), self.color("dim"))
            self.draw(11, 6, clip(f"Note: {self.selected.note}" if self.selected else "", self.w - 10), self.color("dim"))
            x = self.button(13, 6, "Create Room", lambda: "go")
            x = self.button(13, x, "Change Transport", lambda: self.go_addresses(True), self.color("dim"))
            self.button(13, x, "Back", lambda: "menu", self.color("dim"))
            self.draw(15, 6, f"Share with peers:  {netdetect.format_endpoint(self.selected.ip if self.selected else '127.0.0.1', int(f_port.value or 0))}", self.color("ok"))
            self.draw(16, 6, "Peers enter IP + port, the app checks the room, then asks for the password.", self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            result = self.handle_base(self.key(), back="menu")
            if isinstance(result, tuple) and result[0] == "enter":
                result = "go"
            if result in ("addresses", "menu"):
                return result
            if result == "go":
                try:
                    port = int(f_port.value.strip())
                    max_users = max(1, min(256, int(f_max.value.strip())))
                except ValueError:
                    self.say("Port and max users must be numbers.")
                    continue
                if not 1 <= port <= 65535:
                    self.say("Port must be between 1 and 65535.")
                    continue
                name = f_name.value.strip() or "Untitled Room"
                password = f_pass.value
                if not password:
                    self.say("A room password is required (it derives the encryption key).")
                    continue
                ip = self.selected.ip if self.selected else "127.0.0.1"
                conf = RoomConfig(
                    name=name,
                    port=port,
                    advertise_ip=ip,
                    bind_ip=netdetect.bind_address_for(ip),
                    password=password,
                    max_users=max_users,
                    host_user=self.username,
                )
                server = RoomServer(conf)
                try:
                    server.start()
                except RoomError as exc:
                    self.say(str(exc))
                    continue
                client = ChatClient()
                try:
                    client.connect_first(
                        ["127.0.0.1", "::1"], port, self.username, password, admin_token=conf.admin_token
                    )
                except ClientError as exc:
                    server.stop()
                    self.say(f"Could not enter own room: {exc}")
                    continue
                data = cfg.load()
                data.update({"last_port": port, "last_room_name": name, "default_max_users": max_users, "last_host": ip})
                cfg.save(data)
                self.enter_room(client, server, name, conf.endpoint, password)
                return "chat"

    def screen_join(self) -> str:
        saved = cfg.load()
        f_host = Field("Room IP", str(saved.get("last_host") or ""), 0, 0, 42, hint="IPv6 / IPv4 / Radmin VPN IP")
        f_port = Field("Port", str(saved.get("last_port") or 9001), 0, 0, 12)
        f_pass = Field("Password", "", 0, 0, 24, secret=True)
        while True:
            self.frame("Join a room")
            self.start_fields([f_host, f_port, f_pass])
            self.draw(2, 4, "Enter the room IP + port, check the room, then enter the password.", self.color("dim"))
            f_host.y, f_host.x = 4, 6
            f_port.y, f_port.x = 5, 6
            f_pass.y, f_pass.x = 9, 6
            for f in self.fields:
                self.field(f)
            x = self.button(6, 6, "Check Room", lambda: "check")
            self.button(6, x, "Back", lambda: "menu", self.color("dim"))
            if self.probed:
                self.draw(8, 6, f"FOUND: {self.probed.get('name')}  |  host {self.probed.get('host')}  |  {self.probed.get('users')}/{self.probed.get('max_users')} members", self.color("ok"))
            else:
                self.draw(8, 6, "No room checked yet.", self.color("dim"))
            x = self.button(10, 6, "Join Room", lambda: "join")
            self.button(10, x, "Cancel", lambda: "menu", self.color("dim"))
            self.draw(12, 6, "The app first probes the address. Only if a live CC-2.0 room answers is the password requested.", self.color("dim"))
            self.footer_status()
            self.stdscr.refresh()
            result = self.handle_base(self.key(), back="menu")
            if isinstance(result, tuple) and result[0] == "enter":
                result = "check" if self.focus in (f_host, f_port) else "join"
            if result == "menu":
                return "menu"
            if result in ("check", "join"):
                host = f_host.value.strip().strip("[]")
                try:
                    port = int(f_port.value.strip())
                except ValueError:
                    self.say("Port must be a number.")
                    continue
                if not host:
                    self.say("Enter the room IP or hostname.")
                    continue
                if result == "check":
                    self.say("Checking for a live room...")
                    self.draw(8, 6, "Checking...".ljust(self.w - 10), self.color("warn"))
                    self.stdscr.refresh()
                    info = ChatClient.probe(host, port)
                    self.probed = info
                    if info:
                        self.say(f"Room found: {info.get('name')} ({info.get('users')}/{info.get('max_users')} members)")
                        data = cfg.load()
                        data.update({"last_host": host, "last_port": port})
                        cfg.save(data)
                    else:
                        self.say("No room found at that address - check IP, port, firewall and VPN.")
                    continue
                if not self.probed:
                    self.say("Check the room first.")
                    continue
                if not f_pass.value:
                    self.say("This room requires a password.")
                    self.focus = f_pass
                    continue
                client = ChatClient()
                try:
                    client.connect(host, port, self.username, f_pass.value)
                except ClientError as exc:
                    self.say(str(exc))
                    continue
                data = cfg.load()
                data.update({"last_host": host, "last_port": port})
                cfg.save(data)
                endpoint = netdetect.format_endpoint(host, port)
                self.enter_room(client, None, str(self.probed.get("name") or "Room"), endpoint, f_pass.value)
                self.probed = None
                return "chat"

    def enter_room(self, client: ChatClient, server: RoomServer | None, name: str, endpoint: str, password: str) -> None:
        self.client = client
        self.server = server
        self.is_host = client.is_host
        self.room_name = name
        self.room_endpoint = endpoint
        self.messages = []
        self.members = list(client.members)
        self.max_users = client.max_users
        self.typing = {}
        self.scroll = 0
        self.push_line(f"Connected to '{name}' at {endpoint}", "ok")
        self.push_line("Messages and files here are end-to-end encrypted with the room password.", "dim")
        self.cipher_mode = "v2" if has_aes_gcm() else "v1"

    def push_line(self, text: str, style: str = "dim") -> None:
        attr = self.color(style)
        width = max(20, self.w - (24 if self.w >= 84 else 4))
        for line in wrap(text, width):
            self.messages.append((line, attr))
        if len(self.messages) > 800:
            del self.messages[:200]
        if self.scroll > 0:
            self.scroll += 1

    def process_events(self) -> bool:
        if not self.client:
            return False
        for ev in self.client.events():
            kind = ev.get("t")
            if kind == "message":
                stamp = time.strftime("%H:%M", time.localtime(ev.get("ts", time.time())))
                prefix = "you" if ev.get("own") else ev.get("from", "?")
                self.push_line(f"[{stamp}] {prefix}: {ev.get('text', '')}", "ok" if ev.get("own") else "host")
                self.typing.pop(ev.get("from", ""), None)
            elif kind == "typing":
                if ev.get("on"):
                    self.typing[ev.get("from", "?")] = time.time()
                else:
                    self.typing.pop(ev.get("from", "?"), None)
            elif kind == "sys":
                self.push_line(f"-- {ev.get('text', '')}", "dim")
            elif kind == "room":
                self.members = list(ev.get("members", []))
                self.max_users = int(ev.get("max_users", self.max_users))
            elif kind == "file_incoming":
                self.push_line(f"[FILE] {ev.get('from')} is sending {ev.get('name')} ({human_size(ev.get('size', 0))})", "warn")
            elif kind == "file_saved":
                self.push_line(f"[FILE] Saved {ev.get('name')} -> {ev.get('path')}", "ok")
            elif kind == "file_sent":
                self.push_line(f"[FILE] Sent {ev.get('name')} ({human_size(ev.get('size', 0))})", "ok")
            elif kind == "error":
                self.push_line(f"! {ev.get('message')}", "err")
                if ev.get("code") == "kicked":
                    self.say("You were removed from the room.")
                    return False
            elif kind == "disconnected":
                self.push_line(f"! {ev.get('reason')}", "err")
                self.say("Disconnected from the room.")
                return False
        for user in list(self.typing):
            if time.time() - self.typing[user] > 4:
                del self.typing[user]
        return self.client.connected

    def screen_chat(self) -> str:
        f_msg = Field("Message", "", 0, 0, 40)
        while True:
            self.frame("In room")
            alive = self.process_events()
            self.start_fields([f_msg])
            header = f"Room: {self.room_name}  |  {self.room_endpoint}  |  {self.username}  |  {len(self.members)}/{self.max_users}"
            self.draw(1, 3, clip(header, self.w - 6), self.color("accent") | curses.A_BOLD)
            members_w = 20 if self.w >= 84 else 0
            msg_w = self.w - members_w - 5
            top, bottom = 3, self.h - 8
            msg_h = max(1, bottom - top + 1)
            if alive is False:
                self.draw(top, 3, "Connection closed. Press ESC or click Leave.", self.color("err"))
            lines = self.messages[-max(1, msg_h):] if self.scroll == 0 else self.messages[
                max(0, len(self.messages) - msg_h - self.scroll) : max(0, len(self.messages) - self.scroll)
            ]
            for i in range(msg_h):
                y = top + i
                if i < len(lines):
                    text, attr = lines[i]
                    self.draw(y, 3, clip(text, msg_w), attr)
            self.hits.append((3, top, 3 + msg_w, bottom, ("click", ("scroll", 0), False)))
            if members_w:
                for i in range(top, bottom + 1):
                    self.draw(i, self.w - members_w - 2, "|", self.color("dim"))
                self.draw(top, self.w - members_w, " MEMBERS", self.color("accent"))
                for i, member in enumerate(self.members[: bottom - top]):
                    mark = " *" if member == self.username else ""
                    host_mark = " (host)" if self.is_host and member == self.username else ""
                    self.draw(top + 1 + i, self.w - members_w, clip(f" {member}{mark}{host_mark}", members_w - 1), self.color("ok") if member == self.username else 0)
                    self.hits.append((self.w - members_w, top + 1 + i, self.w - 3, top + 1 + i, ("click", ("member", member), False)))
                self.draw(bottom, self.w - members_w, " double-click = kick" if self.is_host else "", self.color("dim"))
            typers = [u for u in self.typing if u != self.username]
            typing_line = f"{', '.join(typers)} is typing..." if typers else ""
            self.draw(self.h - 6, 3, clip(typing_line, self.w - 8), self.color("warn") | curses.A_BOLD)
            f_msg.y, f_msg.x = self.h - 5, 3
            f_msg.w = max(20, self.w - 32)
            self.field(f_msg)
            x = self.button(self.h - 5, self.w - 14, "Send", lambda: "send", self.color("btn") | curses.A_BOLD)
            y = self.h - 3
            x = self.button(y, 3, "Attach File", lambda: "files")
            x = self.button(y, x, "Leave Room", lambda: "leave", self.color("dim"))
            if self.is_host:
                x = self.button(y, x, "Max -", lambda: "max-")
                self.draw(y, x, f" {self.max_users} ", self.color("ok") | curses.A_BOLD)
                x += 5
                x = self.button(y, x, "Max +", lambda: "max+")
                x = self.button(y, x, "Close Room", lambda: "close", self.color("err"))
            else:
                self.draw(y, x, f" Member cap: {self.max_users} (host controls) ", self.color("dim"))
            if self.time_to_stop_typing():
                if self.client:
                    self.client.send_typing(False)
                self.typing_active = False
            self.footer_status()
            self.stdscr.refresh()
            ch = self.key()
            result = self.handle_base(ch, back="leave")
            if isinstance(result, tuple) and result[0] == "enter":
                result = "send"
            if isinstance(result, tuple) and result[0] == "wheel":
                self.scroll = max(0, min(self.scroll + result[1], max(0, len(self.messages) - msg_h)))
            if isinstance(result, tuple) and result[0] == "click":
                target, value, double = result[1][0], result[1][1], result[2]
                if target == "scroll":
                    self.scroll = min(self.scroll + 1, max(0, len(self.messages) - msg_h))
                elif target == "member" and double and self.is_host and self.client and value != self.username:
                    self.client.kick(value)
                    self.say(f"Removed {value}")
            if result == "send" and self.client and self.client.connected:
                text = f_msg.value
                if text.strip():
                    self.client.send_text(text)
                    f_msg.value, f_msg.pos = "", 0
                    self.typing_active = False
                    self.scroll = 0
            elif result in ("leave", "close"):
                if result == "close" and self.client:
                    self.client.close_room()
                self.leave_room()
                return "menu"
            elif result == "files":
                chosen = self.screen_files()
                if chosen and self.client:
                    self.client.send_file(chosen)
            elif result == "max-" and self.client:
                self.client.set_max_users(max(1, self.max_users - 1))
            elif result == "max+" and self.client:
                self.client.set_max_users(min(256, self.max_users + 1))

    def time_to_stop_typing(self) -> bool:
        return self.typing_active and time.time() - self.last_input > 2.5

    def leave_room(self) -> None:
        if self.client:
            self.client.leave()
        if self.server:
            self.server.stop()
        self.client = None
        self.server = None
        self.is_host = False
        self.typing.clear()

    def scan_files(self) -> None:
        self.file_items = []
        try:
            entries = sorted(os.scandir(self.file_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as exc:
            self.say(str(exc))
            entries = []
        self.file_items.append(("..", True))
        for entry in entries[:400]:
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            self.file_items.append((entry.name + ("/" if is_dir else ""), is_dir))

    def screen_files(self) -> str:
        self.scan_files()
        f_path = Field("Directory", self.file_dir, 0, 0, 48)
        while True:
            self.frame("Choose a file to send (click)")
            self.start_fields([f_path])
            self.draw(2, 4, "Click a file, then 'Send'. Double-click a folder to open it.", self.color("dim"))
            f_path.y, f_path.x = 3, 6
            self.field(f_path)
            x = self.button(4, 6, "Go", lambda: "go")
            self.button(4, x, "Home", lambda: "home", self.color("dim"))
            top, bottom = 6, self.h - 7
            visible = max(1, bottom - top + 1)
            self.file_scroll = max(0, min(self.file_scroll, max(0, len(self.file_items) - visible)))
            for i in range(visible):
                idx = self.file_scroll + i
                if idx >= len(self.file_items):
                    break
                name, is_dir = self.file_items[idx]
                y = top + i
                mark = ">" if name == self.file_selected else " "
                style = self.color("ok") if name == self.file_selected else (self.color("accent") if is_dir else 0)
                self.draw(y, 4, clip(f"{mark} {name}", self.w - 10), style)
                self.hits.append((4, y, min(self.w - 5, 4 + len(name) + 2), y, ("click", ("file", name), False)))
            y = self.h - 5
            x = self.button(y, 4, "Send selected", lambda: "send")
            self.button(y, x, "Cancel", lambda: "cancel", self.color("dim"))
            if self.file_selected:
                self.draw(y - 1, 4, clip(f"Selected: {self.file_selected}", self.w - 8), self.color("ok"))
            self.footer_status()
            self.stdscr.refresh()
            ch = self.key()
            result = self.handle_base(ch, back="cancel")
            if isinstance(result, tuple) and result[0] == "wheel":
                self.file_scroll = max(0, self.file_scroll - result[1])
            if ch == curses.KEY_UP:
                self.file_scroll = max(0, self.file_scroll - 1)
            if ch == curses.KEY_DOWN:
                self.file_scroll += 1
            if isinstance(result, tuple) and result[0] == "click":
                name, double = result[1][1], result[2]
                self.file_selected = name
                if name == ".." or (name.endswith("/") and double):
                    target = os.path.dirname(self.file_dir.rstrip("/")) if name == ".." else os.path.join(self.file_dir, name[:-1])
                    if os.path.isdir(target):
                        self.file_dir = target
                        f_path.value, f_path.pos = target, len(target)
                        self.file_selected = ""
                        self.file_scroll = 0
                        self.scan_files()
            if isinstance(result, tuple) and result[0] == "enter":
                result = "go"
            if result in ("go", "home"):
                target = f_path.value.strip() if result == "go" else os.path.expanduser("~")
                if os.path.isdir(target):
                    self.file_dir = target
                    self.file_scroll = 0
                    self.scan_files()
                else:
                    self.say("Not a directory.")
                continue
            if result == "send":
                if not self.file_selected or self.file_selected == ".." or self.file_selected.endswith("/"):
                    self.say("Pick a file, not a folder.")
                    continue
                return os.path.join(self.file_dir, self.file_selected)
            if result == "cancel":
                return ""

    def run(self) -> None:
        self.setup()
        self.cipher_mode = "v2" if has_aes_gcm() else "v1"
        screen = "menu" if self.username else "username"
        try:
            while screen != "quit":
                if screen == "username":
                    screen = self.screen_username()
                elif screen == "menu":
                    screen = self.screen_menu()
                elif screen == "create":
                    screen = self.screen_create()
                elif screen == "join":
                    screen = self.screen_join()
                elif screen == "addresses":
                    screen = self.screen_addresses(pick=self.addr_pick)
                elif screen == "chat":
                    screen = self.screen_chat()
                else:
                    screen = "menu"
        finally:
            self.leave_room()


def main() -> int:
    try:
        import curses as _curses
    except ImportError:
        print("curses is unavailable on this platform.")
        print("On Windows run:  python -m pip install windows-curses")
        return 1
    try:
        return _curses.wrapper(lambda stdscr: (App(stdscr).run(), 0)[1])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
