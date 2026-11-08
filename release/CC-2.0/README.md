# CC-2.0 / ChatClient - Terminal Edition

**Jointly built by Creaddinscart Teams & CC Team**

> Step-by-step guide: **[USAGE.md](USAGE.md)**
> License: **[MPL-2.0](LICENSE)**; copyright and third-party notices: [NOTICE](NOTICE)
> Ready-to-ship package: `release/CC-2.0/` and `release/CC-2.0.zip` (built with `build_release.py`)

An end-to-end encrypted private chat application for the terminal. **Creating a room starts a
temporary server on the creator's own computer** and peers connect straight to it - no central
service, no graphical desktop client, no web client. It runs on macOS, Linux and Windows as a
mouse-driven curses UI, plus a headless room server for unattended machines.

---

## 1. Quick start

Python 3.9+ is the only requirement. All core features use the standard library.

| Platform | Launch |
| --- | --- |
| macOS | Double-click `CC-2.0.command` |
| Linux | `./CC-2.0.sh` |
| Windows | Double-click `CC-2.0.bat` |
| Any system | `python3 launch.py` |

Launcher menu:

```
[1] Terminal UI (mouse-clickable)
[2] Headless room server
[3] Run self-tests
```

Direct entry points:

```bash
python3 cc2_cli.py
python3 cc2_server.py --name "Night Shift" --port 9001 --password mypass
```

Optional dependencies (recommended, enables standard AES-GCM):

```bash
python3 -m pip install -r requirements.txt
```

On Windows, `windows-curses` from that command is required for the terminal UI.

> First time here? Follow **[USAGE.md](USAGE.md)**: pick a username, then create or join a room.
> A host enters name / port / transport / password / member cap; a peer enters IP + port, checks the
> room, then enters the password.

---

## 2. Transports (chosen by the room creator)

Every local address is discovered and ranked. **A global IPv6 address is selected by default**:

| Priority | Type | Use case |
| --- | --- | --- |
| 1 | **Global IPv6** (preferred) | Usually reachable without port forwarding |
| 2 | Public IPv4 / WAN IP | Fallback; needs router port forwarding behind NAT |
| 3 | VPN / **Radmin VPN** (26.x.x.x) | Everyone joins the same virtual network |
| 4 | LAN IPv4 / IPv6 ULA | Same Wi-Fi or switch |
| 5 | 127.0.0.1 | Local testing only |

Open the transport picker to switch, or enter a custom IP for any other VPN adapter.
The app displays the exact `IP:port` to share, with IPv6 brackets added automatically.

### Publishing through an FRP exit

Behind NAT / CGNAT with no reachable public address? Do exactly what you would for a **Minecraft
server**: download a third-party FRP client (`frpc`), map a port on your public FRP server to the
room's local port, and you are done. **CC-2.0 does not generate or run `frpc`.** It only needs to
know the public address and port that peers should connect to.

```
peer  --->  frps:25565  === FRP tunnel ===>  frpc  --->  127.0.0.1:9001 (room server)
```

**1. Configure the tunnel in your own FRP client.** A plain `tcp` proxy, same as a Minecraft
server mapping. Example `frpc.toml` (yours may use `frpc.ini`):

```toml
serverAddr = "frp.example.com"
serverPort = 7000

[[proxies]]
name = "cc2"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9001
remotePort = 25565
```

`localPort` must match the room's local port. `remotePort` is the port you share with peers; the two
do not have to be equal. Start `frpc` and keep it running while the room is open.

**2. Tell CC-2.0 the public exit.** Terminal UI: **Main menu / FRP Exit** (or the **FRP Exit**
button on the Create Room form). Enter one address, switch FRP on, click **Save**:

```
frp.example.com:25565
```

Headless server, one flag:

```bash
python3 cc2_server.py --name "Night Shift" --port 9001 --password mypass --frp frp.example.com:25565
```

**3. Peers join normally**: enter `frp.example.com` + port `25565`, click **Check Room**, then
enter the password. They need no FRP software and never see your local port.

Rules worth knowing:

- The `frps` control port, auth token, proxy name and TLS settings belong to your FRP client.
  CC-2.0 never asks for them and writes no config files.
- Do **not** enable the FRP PROXY protocol for this proxy; it prepends bytes that break the CC-2.0
  framing. Plain `tcp` is what CC-2.0 expects.
- Open `remotePort` on the FRP server's firewall / security group.
- In FRP mode the room server binds to `0.0.0.0` so `frpc` can reach it. The password is still
  required for every peer. `--frp-check` optionally probes the exit after startup.
- Because tunneled connections arrive from loopback, FRP rooms **do not** grant host rights by
  loopback username. A host joining a headless FRP room must paste the printed
  `Host admin token` into the **Admin token** field on the Join Room form.

The FRP server only ever sees ciphertext: the room password and the encryption key never leave the
clients. See [USAGE.md](USAGE.md) for the full walkthrough.

---

## 3. Workflow

**First run**: choose a display name, saved in `~/.cc2/config.json`.

**Create a room** (the host fills in):

1. Room name
2. Port (default 9001)
3. Transport IP (IPv6 first; public IPv4 / Radmin VPN / LAN are selectable)
4. Room password (derives the end-to-end encryption key; never transmitted)
5. Member cap (default 8, adjustable at any time inside the room)

**Join a room** (a peer):

1. Enter the room IP + port
2. Click **Check Room** - the app probes the address and reports the room name, host, and
   current member count / cap
3. Only after the room is confirmed does it ask for the password
4. Join the main chat

Wrong passwords, full rooms and duplicate usernames are rejected with clear messages.

---

## 4. Features

- **End-to-end encryption**: the server only relays ciphertext; it never sees message text or file
  bytes. The last 200 encrypted messages are cached so late joiners see history.
- **Typing indicators**: `Bob is typing...` appears on other clients in real time.
- **File transfer**: a built-in clickable file browser inside the terminal; encrypted chunks are
  saved to `~/Downloads/CC-2.0/`.
- **Host controls**: change the member cap (1-256) live from inside the room, kick members, close
  the room.
- **Live member list** with current count and cap.
- **Fully mouse-driven terminal**: buttons, input fields, the transport list, the file browser and
  the member list are all clickable under curses. TAB / arrows / ENTER / ESC work too.
- **Headless server**: keep a room online on a machine with no interactive session.
- **FRP exit**: publish a local room through a public FRP server. Configure `frpc` yourself like a
  Minecraft server; CC-2.0 only needs the public `host:port` to show peers.

---

## 5. Encryption

- Key: `PBKDF2-HMAC-SHA256(room password, room salt, 120000)` derived **locally on each client**.
- Authentication: the client sends a separate verifier; the server stores a different derived value,
  so it cannot recover the message key from its own state.
- Payload: `0x02 | nonce(12) | AES-256-GCM(...)` or, with zero extra packages,
  `0x01 | nonce(12) | HMAC-SHA256 tag | ciphertext` (HMAC-SHA256 counter-mode keystream,
  Encrypt-then-MAC).
- **Capability negotiation**: each client advertises the formats it supports; the server intersects
  them. If any peer lacks `cryptography`, the whole room falls back to the standard-library format,
  so nobody ever receives an unreadable message.

> Honest note: the zero-dependency fallback is a sound authenticated-encryption construction but is
> **not a standardized AEAD**. Install `cryptography` for AES-256-GCM in serious deployments.
> The room password is the only key source: use a long one, and never expose an unprotected port
> to the public Internet.

---

## 6. Project layout

```
USAGE.md                      Complete step-by-step guide (start here)
LICENSE                       MPL-2.0 full text
NOTICE                        Copyright and third-party notices
CC-2.0.command / .sh / .bat   Double-click launchers for the three platforms
launch.py                     Unified launcher (includes the test entry)
cc2_cli.py                    curses terminal UI with mouse support
cc2_server.py                 Headless room server
build_release.py              Rebuilds the release/ package
cc2/
  brand.py                    Brand constants (CC-2.0 / ChatClient / credits)
  crypto.py                   End-to-end encryption and key derivation
  protocol.py                 Length-prefixed JSON protocol / room probe
  netdetect.py                IPv6 / IPv4 / VPN / LAN discovery and ranking
  frp.py                      FRP public exit parsing and endpoint handling
  server.py                   Temporary room server
  client.py                   Client networking, chunked files, event queue
  config.py                   Local profile and download directory
tests/                        selftest.py / tui_smoke.py
release/                      Ready-to-ship CC-2.0 folder + CC-2.0.zip
```

---

## 7. Release package

`release/CC-2.0/` is a clean, standalone copy of everything needed to run the terminal edition:
the curses client, the headless server, the `cc2` package, the three launchers, documentation and
the license. Tests, caches, graphical clients and web assets are excluded. `release/CC-2.0.zip` is
the same folder zipped for distribution. Regenerate both after editing the source:

```bash
python3 build_release.py
```

Copy the folder anywhere and run `python3 launch.py` (or double-click the platform launcher).
Python 3.9+ is still required on the target machine.

---

## 8. Tests

```bash
python3 tests/selftest.py       # 50 checks: crypto, probe, password, chat, typing, files, cap, FRP, framing
python3 tests/tui_smoke.py      # 9 checks: pty-driven terminal UI with real mouse clicks
python3 launch.py --test        # both suites
```

Running with `cryptography` installed covers the AES-GCM branch too:

```bash
python3 -m pip install -r requirements.txt
python3 tests/selftest.py
```

---

## 9. Troubleshooting

1. **Check Room fails**: wrong IP or port, room not running, firewall, or VPNs not on the same network.
2. **Firewall**: allow Python to accept incoming connections when macOS / Windows asks; check
   `ufw` / `firewalld` on Linux.
3. **IPv6**: both sides need IPv6. Strip a `%interface` suffix, or switch to public IPv4 / VPN.
4. **Public IPv4 behind a router**: forward the port, or use a VPN / Radmin VPN.
5. **Radmin VPN**: everyone must join the same Radmin network and use the `26.x.x.x` address shown
   in the Radmin client.
6. **Port already in use**: pick another one, e.g. 9101.
7. **Windows says curses is missing**: `pip install windows-curses`.
8. **Terminal looks cramped**: resize to at least 72 columns x 22 rows.
9. **Mouse clicks do nothing**: use a terminal with mouse reporting (iTerm2, Terminal.app,
   Windows Terminal, gnome-terminal, xterm) and keep the keyboard shortcuts as a fallback.
10. **FRP exit does not answer**: start `frpc` after the room is running, open `remotePort` on the
    FRP server, and confirm `localPort` matches the room port. A failed `--frp-check` can also be a
    router hairpin limitation - peers may still be able to connect.
11. **FRP guests cannot reach the room**: do not enable the FRP PROXY protocol, and make sure the
    room server is bound to `0.0.0.0` (automatic when FRP is enabled).

---

## 10. License

Licensed under the **Mozilla Public License 2.0 (MPL-2.0)**. Full text: [LICENSE](LICENSE).
Copyright and third-party notices: [NOTICE](NOTICE). Every source file carries the MPL-2.0
Exhibit A notice and `SPDX-License-Identifier: MPL-2.0`.

A deliberately stricter-than-MIT, weak-copyleft license:

- Use, modify and distribute freely, including in commercial products and alongside proprietary code.
- **Modified MPL-covered source files must remain under MPL-2.0 and stay available in source form**
  (file-level copyleft; it does not spread to the whole work).
- Keep copyright and license notices; includes an express patent grant that terminates if you
  bring a patent infringement claim.
- No warranty and no trademark rights are granted.

For a stronger copyleft use GPL-3.0 / AGPL-3.0; for a permissive license with patent and NOTICE
terms use Apache-2.0.

---

*CC-2.0 | ChatClient - Terminal Edition - Jointly built by Creaddinscart Teams & CC Team*
*Licensed under MPL-2.0 - Copyright (c) 2026 Creaddinscart Teams & CC Team*
