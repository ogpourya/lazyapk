# AGENTS.md — LazyAPK Development Guide

## Workflow
- Always commit and push after significant progress AND user verification ("I verified your work").
- Single `main` branch only.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
  `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `style:`
- Keep AGENTS.md up to date with any workflow or architectural changes.

## Dependencies
- Use `uv add <package>` to add dependencies. Never edit `pyproject.toml` manually for deps.
- Use `uv sync` after changes.

## Versioning
- Strict [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

## Architecture
- Package in `src/lazyapk/` with separate modules per domain.
- `cli.py` — Click CLI entry point with global options (-s, -v, --json).
- `adb.py` — ADB subprocess wrapper with timeouts and device resolution (incl. `root()`, `pidof()` helpers).
- `search.py` — Fuzzy package search engine using rapidfuzz.
- `transfer.py` — APK pull with split APK support.
- `proxy.py` — Android global HTTP proxy management via settings.
- `frida_mgr.py` — Frida-server lifecycle: download, push, start, stop, status. Start escalates to root (`adb root` / `su -c`) — frida-server needs root to ptrace app processes.
- `ssl.py` — SSL unpinning via httptoolkit's frida-interception-and-unpinning script. Cached bundle is injected with a CA cert (`--ca` or auto-detect `~/.mitmproxy/mitmproxy-ca-cert.pem`) and run with `frida -D <serial>`; attach mode resolves pid via `pidof` (process names/labels are unreliable on some emulators).
- `info.py` — Package info viewer via dumpsys parsing.
- `logcat.py` — Filtered logcat streaming for a specific package.
- `manifest.py` — AndroidManifest.xml parser using pyaxmlparser.
- `utils.py` — Shared: Rich console, verbose logging, signal handling, Transaction class.
- `cli.py` commands: `search`, `pull`, `proxy set/get/clear`, `frida install/start/stop/status`, `unpin` (with `--ca`), `reset` (clears cache, stops frida-server, clears proxy), `info`, `logcat`, `manifest`, `doctor`, `launch`, `kill`.
- Output: Rich tables to stdout (default), errors/info to stderr, `--json` flag emits JSON to stdout.

## CLI Standards
- CLI tool using Click + Rich.
- Full `--help` with thorough explanations for every command/option.
- Handle stdin, stdout, stderr properly. No print() — use Rich or Click output.
- Verbose mode (`-v` / `--verbose`) throughout.
- Signal handling: catch SIGINT/SIGTERM gracefully, clean exit.
- Never let raw Python exceptions or tracebacks leak to the user.
- Transaction-style architecture: each operation has a commit/rollback path.
- Timeouts on every external operation (ADB, Frida, network, etc.).
