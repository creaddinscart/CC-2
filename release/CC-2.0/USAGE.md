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

If no address is reachable from the Internet, click **FRP Exit** on this form to publish the room
through a public FRP server. See [scenario F](#f-public-access-through-an-frp-exit). The address
shown to peers then becomes the FRP server plus its remote port, not your local port.

---

## 4. Join a room (peer)

1. Choose **Join Room**.
2. Enter the host's **IP** (IPv6 may be pasted with or without brackets) and the **port**. For an
   FRP room use the **FRP server address** and its **remote port** - never the host's local port.
3. Click **Check Room**. The app probes the address for a live CC-2.0 room:
   - Found: room name, host, current members, cap and an `FRP exit` tag are displayed.
   - Not found: check the IP, port, firewall, port forwarding and VPN membership.
4. Enter the **room password**.
5. Optionally enter the **Admin token** when you are the host of a headless FRP room. The headless
   server prints it at startup. Leave it empty for a normal guest.
6. Click **Join Room** to enter the chat.

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

<a id="f-public-access-through-an-frp-exit"></a>
### F. Public access through an FRP exit

Use this when the host has **no reachable public address** (CGNAT, mobile hotspot, restrictive
router) but has a public FRP server. Set it up **exactly like a Minecraft server**: download a
third-party FRP client (`frpc`) yourself, add a `tcp` proxy that maps a public port to the room's
local port, and start it. CC-2.0 does not install, configure or run `frpc`; it only needs the
public `host:port` that peers should connect to.

```
guest terminal --> frps:25565 --> frpc --> 127.0.0.1:9001 (room server)
```

**Step 1 - Configure the tunnel in your own FRP client.** Example `frpc.toml` (older clients use
`frpc.ini`; GUI FRP clients have the same fields):

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

This is the same mapping you would use for a Minecraft server on `25565`. `localPort` must equal
the CC-2.0 room port. `remotePort` is the port you hand to other people; the two can be different.
`serverAddr`, `serverPort`, any auth token and the proxy name are your FRP client's business - you
never enter them into CC-2.0. Start `frpc` and keep it running.

**Step 2 - Tell CC-2.0 the public exit.** Terminal UI: main menu / **FRP Exit** (or the **FRP
Exit** button on the Create Room form). Enter a single address:

```
frp.example.com:25565
```

Click `FRP: OFF` to switch it to `FRP: ENABLED`, click **Save**, then **Back**. The dialog shows
which `localPort` and `remotePort` your `frpc` should use. **Check Exit** optionally verifies that
the tunnel is up. Create the room afterwards.

Headless server, one flag:

```bash
python3 cc2_server.py --name "Night Shift" --port 9001 --password 'long-password' --frp frp.example.com:25565
```

It prints `localPort = 9001` and `remotePort = 25565` as a reminder of what to set in `frpc`.
`--frp-host` plus `--frp-port` is an equivalent split form; `--frp-check` probes the exit on startup.

**Step 3 - Guests join normally.** Enter `frp.example.com` + port `25565`, click **Check Room**,
then enter the room password. Guests need no FRP software, no token and no knowledge of the host's
local port. The room probe itself reports the public endpoint.

**Host rights.** Tunneled connections appear to the room server as coming from loopback, so FRP
rooms never grant host rights by username alone. A host who created the room in the terminal UI is
already host. For a headless FRP room, paste the printed `Host admin token` into the **Admin token**
field on the Join Room form.

**Important details**

- Local and remote ports are independent. `9001` locally and `25565` publicly is normal.
- Keep `frpc` running the whole time; if it exits, guests lose the room but the room stays alive
  locally.
- Do **not** enable `proxy_protocol_version` for this proxy. CC-2.0 expects raw TCP bytes and the
  PROXY protocol header would break the framing.
- Open `remotePort` on the FRP server firewall. A failed **Check Exit** / `--frp-check` can also be
  a router hairpin limitation; guests may still connect.
- The FRP server sees ciphertext, usernames and timing only. It cannot read messages or files.

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
python3 cc2_server.py --name X --port 9001 --password pw --frp frp.example.com:25565
python3 cc2_server.py --name X --port 9001 --password pw --frp frp.example.com:25565 --frp-check
python3 cc2_server.py --name X --port 9001 --password pw --frp-host frp.example.com --frp-port 25565

python3 tests/selftest.py
python3 tests/tui_smoke.py
python3 build_release.py
```

Profile: `~/.cc2/config.json` (username, last IP / port / room name, download directory, FRP
enabled flag and the single FRP exit string). No FRP credentials are stored by CC-2.0 - those stay
in your own `frpc` config. Received files go to `~/Downloads/CC-2.0/`; change `download_dir` to
move it.

Useful `cc2_server.py` FRP flags: `--frp HOST:PORT`, `--frp-host` / `--frp-port`, `--frp-check`.
`frpc` itself is installed and configured separately.

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
| FRP exit answers nobody | Start `frpc` after the room, open `remotePort` on `frps`, match `localPort` to the room port |
| `--frp-check` fails but guests work | Router hairpin blocking; verify from an outside network instead |
| FRP room probe is malformed | Disable the FRP PROXY protocol; use a plain `tcp` proxy |
| Headless FRP host is not host | Paste the printed `Host admin token` into the Join Room admin field |

---

## 9. Security and licensing

- The room password is the **only key source**. Use a long one and never expose an unprotected port
  to the public Internet.
- The server only forwards ciphertext plus minimal control data (usernames, room name, member
  count, typing state). It never stores plaintext chat.
- The zero-dependency fallback is not a standardized AEAD. Install `cryptography` to use
  AES-256-GCM in serious deployments.
- An FRP server is an extra relay operator: it sees ciphertext, the room name, usernames and
  traffic timing, but never the password, the key or any plaintext. Use a server you trust and
  share the room password over a separate channel.
- FRP rooms require the admin token for host rights; a tunneled guest cannot become host by
  reusing the host's display name.
- Licensed under **MPL-2.0**: commercial use, modification and distribution are allowed, but
  **modified MPL-covered source files must stay under MPL-2.0 and remain available in source form**,
  and copyright / license notices must be preserved. Stricter than MIT, without the viral effect of
  the GPL. Full terms: [LICENSE](LICENSE).

---

*CC-2.0 | ChatClient - Terminal Edition - Jointly built by Creaddinscart Teams & CC Team*
