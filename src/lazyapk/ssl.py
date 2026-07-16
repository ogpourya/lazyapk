import subprocess
from pathlib import Path

import httpx

from . import adb, utils

BASE_URL = "https://raw.githubusercontent.com/httptoolkit/frida-interception-and-unpinning/main"
SCRIPT_FILES = ["config.js", "android-certificate-unpinning.js"]

CACHE_DIR = utils.CACHE_DIR / "ssl-unpin"
CACHE_SCRIPTS = CACHE_DIR / "scripts.js"


def _download_bundle() -> str:
    if CACHE_SCRIPTS.exists():
        utils.verbose("Using cached SSL unpinning scripts")
        return CACHE_SCRIPTS.read_text()

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

    combined = "\n\n".join(parts)

    CACHE_SCRIPTS.parent.mkdir(parents=True, exist_ok=True)
    CACHE_SCRIPTS.write_text(combined)
    utils.verbose("Scripts cached")
    return combined


def check_frida_tools() -> str | None:
    import shutil
    for name in ("frida", "frida-tools"):
        path = shutil.which(name)
        if path:
            return path
    return None


def cmd_unpin(serial: str | None, package: str, attach: bool = False):
    if not check_frida_tools():
        utils.fatal(
            "frida-tools not found. Install:\n"
            "  uv add frida-tools\n"
            "  or: pip install frida-tools"
        )

    if not adb.process_exists(serial, "frida-server"):
        utils.fatal("frida-server is not running. Start it with: lazyapk frida start")

    script_path = _download_bundle()

    dev_serial = adb.resolve_device(serial)
    utils.info(f"Target device: {dev_serial}")
    utils.info(f"Target app: {package}")
    utils.info(f"Mode: {'attach' if attach else 'spawn'}")

    frida_bin = check_frida_tools()
    cmd = [frida_bin, "-U", "-l", script_path]

    if attach:
        cmd.extend(["-n", package])
    else:
        cmd.extend(["-f", package])

    utils.verbose(f"Running: {' '.join(cmd)}")
    utils.info(f"Starting Frida — app will launch. Press Ctrl+C to stop.")

    try:
        subprocess.run(cmd, timeout=300)
    except subprocess.TimeoutExpired:
        utils.warn("Frida session timed out after 300s")
    except KeyboardInterrupt:
        utils.info("Frida session terminated by user")
