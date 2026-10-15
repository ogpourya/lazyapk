# lazyapk

A toolbox of practical ADB and Frida commands for Android hacking and debugging.

## Quick Start

```bash
# Install
uv tool install https://github.com/ogpourya/lazyapk.git

# Requires: adb + frida-tools on host
#   adb:   apt install adb / brew install android-platform-tools
#   frida: uv tool install frida-tools
```

## Usage

```bash
lazyapk search --query banking          # Fuzzy search packages
lazyapk pull com.example.app -o ./apks  # Pull APK from device
lazyapk proxy set 192.168.1.1 8080      # Set device HTTP proxy
lazyapk frida install                   # Install frida-server
lazyapk frida start                     # Start frida-server
lazyapk unpin com.example.app           # Bypass SSL pinning
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | List/Search packages with fuzzy matching (name, label, type) |
| `pull` | Pull APK(s) from device, supports split APKs |
| `proxy` | Manage device HTTP proxy (set/get/clear) |
| `frida` | Full frida-server lifecycle (install/start/stop/status) |
| `unpin` | Universal SSL pinning bypass via Frida |

## CLI Standards

- `-s SERIAL` — target a specific device when multiple are connected
- `-v` / `--verbose` — show every ADB/Frida command and its output
- `--json` — machine-parseable JSON output on `search`, `proxy get`, `pull`
- `--help` — thorough documentation for every command
- Signal-safe: SIGINT/SIGTERM handled gracefully, no traceback leaks
- 30s default timeout on ADB operations, 120s+ on downloads

## License

MIT
