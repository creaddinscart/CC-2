# CC-2.0 / ChatClient - Terminal Edition

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
