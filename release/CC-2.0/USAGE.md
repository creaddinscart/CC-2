# CC-2.0 / ChatClient User Guide - Terminal Edition

> Jointly built by Creaddinscart Teams & CC Team
> License: **Mozilla Public License 2.0 (MPL-2.0)**, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
> This is the complete operational guide. For the project overview see [README.md](README.md).

---

## 0. Quick start in one minute

```bash
cd CC-2
python3 launch.py
```

| Press | Starts | Best for |
| --- | --- | --- |
| `1` | Terminal UI | Chatting, creating or joining rooms; every button is clickable |
| `2` | Headless room server | Keeping a room online without an interactive session |
| `3` | Self-tests | Verify the installation |

On first launch you **create a username**. It is stored in `~/.cc2/config.json` and you will not be
asked again.

Smallest possible setup, two machines on the same Wi-Fi:

```bash
python3 cc2_cli.py
```

On machine A choose **Create Room** and fill in the form. On machine B run the same command, choose
**Join Room**, enter A's IP and port, click **Check Room**, then enter the password.

---

## 1. Requirements

Required: Python 3.9 or newer. All core functionality uses the standard library.
A terminal at least **72 columns x 22 rows** with mouse reporting is recommended.

```bash
python3 --version
```

Optional, recommended:

```bash
python3 -m pip install -r requirements.txt
```

With `cryptography` installed the room uses standard **AES-256-GCM**. Without it, every client
automatically uses the built-in HMAC-SHA256-CTR + HMAC authenticated format, which is fully
functional and needs no packages.

On **Windows**, `windows-curses` from that command is required for the terminal UI. macOS and
Linux ship `curses` with Python.

| Platform | Launcher | Notes |
| --- | --- | --- |
| macOS | Double-click `CC-2.0.command` | Allow Terminal to run it; get Python from python.org |
| Linux | `./CC-2.0.sh` | No desktop or X server needed |
| Windows | Double-click `CC-2.0.bat` | During Python setup enable "Add Python to PATH" |

The launchers simply call `launch.py`. You can also start either program directly:

```bash
python3 cc2_cli.py
python3 cc2_server.py --name "Night Shift" --port 9001 --password mypass
```

---

## 2. Core concepts

- **A room is a temporary server.** The creator's machine listens on a port and peers connect
  directly. Close the room and the chat is gone; nothing is stored on a central server.
- **Transport address**: chosen by the creator. All local addresses are listed and ranked as
  **global IPv6 > public IPv4 > VPN (including Radmin VPN) > LAN > loopback**. The first usable
  global IPv6 address is preselected.
- **The password is the key**: it derives a 256-bit encryption key locally on every client. The
  server only relays ciphertext and cannot read messages or files.
- **Member cap**: set at creation time and adjustable by the host at any moment (1-256).

---

## 3. Create a room (host)

Choose **Create Room** and fill in:

| Field | Meaning | Example |
| --- | --- | --- |
| Room name | Shown to peers during the probe | `Night Shift` |
| Port | Listening port, must be free | `9001` |
| Transport / IP | Pick from the Network Interfaces screen | IPv6 `2409:8a28::...` preferred |
| Password | Derives the encryption key, make it long | `correct-horse-battery` |
| Max users | Member cap, adjustable later | `8` |

After creation the app shows the **endpoint to share**, for example:

```
[2001:db8::1]:9001
192.168.1.23:9001
26.12.34.56:9001
```

When using a public IPv4 or WAN address behind a router, forward that port to this machine's
private IP. With Radmin VPN, everyone must join the same Radmin network first and you must use
the `26.x.x.x` address shown by the Radmin client.

Firewall: macOS and Windows will ask whether Python may accept incoming connections - allow it.
On Linux check `ufw` or `firewalld`.

---

## 4. Join a room (peer)

1. Choose **Join Room**.
2. Enter the host's **IP** (IPv6 may be pasted with or without brackets) and the **port**.
3. Click **Check Room**. The app probes the address for a live CC-2.0 room:
   - Found: room name, host, current members and cap are displayed.
   - Not found: check the IP, port, firewall, port forwarding and VPN membership.
4. Enter the **room password**.
5. Click **Join Room** to enter the chat.

Wrong passwords, a full room and duplicate usernames are rejected with clear messages.

---

## 5. Inside the chat

| Action | How |
| --- | --- |
| Send text | Type in the input box, press ENTER or click **Send** |
| Typing indicator | Other clients show `Bob is typing...`; it disappears 2.5s after they stop |
| Send a file | Click **Attach File** to open the built-in terminal file browser |
| Receive a file | Saved automatically to `~/Downloads/CC-2.0/` |
| Members | Live list on the right; `*` marks yourself |
| Host cap control | `Max -` / `Max +` applies instantly to everyone |
| Kick / close | Double-click a member to kick (host only), or click **Close Room** |
| Leave | Click **Leave Room** or press ESC; the host's local server shuts down too |

### Mouse and keyboard

Buttons, input fields, the transport list, the file browser and the member list are all clickable:

| Input | Effect |
| --- | --- |
| Click a button or field | Run the action / focus the field |
| Click Transport | Open the address picker; click an entry to select it |
| File browser | Click to select, double-click a folder to enter, `..` goes up, **Send selected** sends |
| Click / scroll the message area | Scroll back through history |
| Double-click a member | Host kicks that member |
| `TAB`, arrow up/down | Move between form fields |
| `ENTER` | Submit the form / send a message |
| `ESC` | Go back; in the chat it leaves the room |

Unicode messages (including CJK text) input and display correctly.

---

## 6. Typical scenarios

### A. Same Wi-Fi / LAN

The host picks `LAN (private IPv4)`, for example `192.168.1.23`. The peer enters
`192.168.1.23:9001`. No public IP and no VPN required.

### B. Over the Internet with IPv6 (recommended)

Keep the default **IPv6 Global** address and send the displayed address and port to the peer.
Usually no port mapping is needed. If it fails, check firewalls on both sides and whether the ISP
blocks inbound IPv6.

### C. No IPv6, public IPv4 instead

Pick `Public IPv4` or `WAN IPv4 (NAT)`. Behind a router, forward the port to the machine's private
IP. The peer uses `public-ip:port`; **Check Room** instantly verifies the forwarding.

### D. Radmin VPN or another VPN

1. Everyone installs Radmin VPN and joins the **same network**.
2. The host selects the `26.x.x.x` **Radmin VPN** address, or enters a custom IP.
3. Peers connect to that `26.x.x.x:port`.
4. ZeroTier, Tailscale, WireGuard and Hamachi work the same way: pick that adapter's IP.

### E. A permanent room on a server

```bash
python3 cc2_server.py --name "Ops Room" --port 9001 --password 'long-password' --max-users 12 --user Host
python3 cc2_server.py --list-addresses
```

It prints the endpoint and the host admin token; press `Ctrl+C` to close the room.
Everyone else joins that IP and port from the terminal client.

---

## 7. Command reference

```bash
python3 launch.py
python3 launch.py --cli
python3 launch.py --server --name X --port 9001 --password pw
python3 launch.py --test

python3 cc2_cli.py
python3 cc2_server.py --list-addresses
python3 cc2_server.py --name X --port 9001 --ip 192.168.1.23 --password pw --max-users 8

python3 tests/selftest.py
python3 tests/tui_smoke.py
python3 build_release.py
```

Profile: `~/.cc2/config.json` (username, last IP / port / room name, download directory).
Received files go to `~/Downloads/CC-2.0/`; change `download_dir` in the profile to move it.

---

## 8. Troubleshooting

| Symptom | What to check |
| --- | --- |
| Check Room fails | Wrong IP/port, room not running, firewall, VPNs not on the same network |
| IPv6 fails | Both sides need IPv6; strip a `%interface` suffix; try public IPv4 or a VPN |
| Public IPv4 fails | Router port forwarding, bridged modem, carrier-grade NAT (use a VPN in that case) |
| Radmin VPN fails | Same Radmin network for everyone, and use `26.x.x.x` rather than the LAN IP |
| Port already in use | Choose another port, e.g. 9101 |
| Password accepted but messages cannot be decrypted | All peers must run the same version; recreate the room after changing its password |
| Windows reports missing curses | `python -m pip install windows-curses` |
| Screen shows a resize hint | Enlarge the terminal to at least 72x22 |
| Mouse clicks do nothing | Use a terminal with mouse reporting, or fall back to TAB / ENTER / ESC |

---

## 9. Security and licensing

- The room password is the **only key source**. Use a long one and never expose an unprotected port
  to the public Internet.
- The server only forwards ciphertext plus minimal control data (usernames, room name, member
  count, typing state). It never stores plaintext chat.
- The zero-dependency fallback is not a standardized AEAD. Install `cryptography` to use
  AES-256-GCM in serious deployments.
- Licensed under **MPL-2.0**: commercial use, modification and distribution are allowed, but
  **modified MPL-covered source files must stay under MPL-2.0 and remain available in source form**,
  and copyright / license notices must be preserved. Stricter than MIT, without the viral effect of
  the GPL. Full terms: [LICENSE](LICENSE).

---

*CC-2.0 | ChatClient - Terminal Edition - Jointly built by Creaddinscart Teams & CC Team*
