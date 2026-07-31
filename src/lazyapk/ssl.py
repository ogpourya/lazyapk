import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import adb, utils

BASE_URL = "https://raw.githubusercontent.com/httptoolkit/frida-interception-and-unpinning/main"
SCRIPT_FILES = ["config.js", "android/android-certificate-unpinning.js"]

CACHE_DIR = utils.CACHE_DIR / "ssl-unpin"
CACHE_SCRIPTS = CACHE_DIR / "scripts.js"

CERT_PATTERN = re.compile(r"const CERT_PEM = `.*?`;", re.S)


def _download_bundle() -> Path:
    if not CACHE_SCRIPTS.exists():
        utils.info("Downloading SSL unpinning scripts...")

        parts = []
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            for name in SCRIPT_FILES:
                url = f"{BASE_URL}/{name}"
                utils.verbose(f"Downloading {url}")
                resp = client.get(url)
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to download {name}: HTTP {resp.status_code}")
                parts.append(resp.text)

        CACHE_SCRIPTS.parent.mkdir(parents=True, exist_ok=True)
        CACHE_SCRIPTS.write_text("\n\n".join(parts))
        utils.verbose("Scripts cached")
    else:
        utils.verbose("Using cached SSL unpinning scripts")
    return CACHE_SCRIPTS


def _find_ca() -> Path | None:
    for p in (
        Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem",
        Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer",
        Path.home() / ".config" / "mitmproxy" / "mitmproxy-ca-cert.pem",
    ):
        if p.exists():
            return p
    return None


def _write_injected_script(bundle: Path, ca_path: Path | None) -> Path:
    script = bundle.read_text()
    if ca_path:
        ca = ca_path.read_text()
        if "BEGIN CERTIFICATE" not in ca:
            raise RuntimeError(f"{ca_path} is not a PEM certificate")
        script, n = CERT_PATTERN.subn("const CERT_PEM = `" + ca.strip() + "`;", script, count=1)
        if n != 1:
            raise RuntimeError("Could not inject CA certificate into script")
    fd, path = tempfile.mkstemp(suffix=".js", prefix="lazyapk-unpin-")
    with os.fdopen(fd, "w") as f:
        f.write(script)
    return Path(path)


def check_frida_tools() -> str | None:
    import shutil
    for name in ("frida", "frida-tools"):
        path = shutil.which(name)
        if path:
            return path
    return None


def cmd_unpin(serial: str | None, package: str, attach: bool = False, ca_path: Path | None = None):
    if not check_frida_tools():
        utils.fatal(
            "frida-tools not found. Install:\n"
            "  uv add frida-tools\n"
            "  or: pip install frida-tools"
        )

    if not adb.process_exists(serial, "frida-server"):
        utils.fatal("frida-server is not running. Start it with: lazyapk frida start")

    ca = ca_path or _find_ca()
    if ca:
        utils.verbose(f"Using CA certificate: {ca}")
    else:
        utils.warn("No CA certificate found — unpinning only, use --ca to enable interception")

    script_path = _write_injected_script(_download_bundle(), ca)

    dev_serial = adb.resolve_device(serial)
    utils.info(f"Target device: {dev_serial}")
    utils.info(f"Target app: {package}")
    utils.info(f"Mode: {'attach' if attach else 'spawn'}")

    frida_bin = check_frida_tools()
    # ponytail: -D <serial> instead of -U, avoids stale adb devices shadowing
    cmd = [frida_bin, "-D", dev_serial, "-l", str(script_path)]

    if attach:
        pid = adb.pidof(serial, package)
        if not pid:
            utils.fatal(f"{package} is not running. Launch it first, or drop --attach to spawn it.")
        cmd.extend(["-p", pid])
    else:
        cmd.extend(["-f", package])

    utils.verbose(f"Running: {' '.join(str(c) for c in cmd)}")
    utils.info(f"Starting Frida — app will launch. Press Ctrl+C to stop.")

    try:
        subprocess.run(cmd, timeout=300)
    except subprocess.TimeoutExpired:
        utils.warn("Frida session timed out after 300s")
    except KeyboardInterrupt:
        utils.info("Frida session terminated by user")
