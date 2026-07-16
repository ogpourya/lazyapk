import json
import shutil
import tempfile
from pathlib import Path

import httpx

from . import adb, utils

FRIDA_GITHUB_RELEASES = "https://api.github.com/repos/frida/frida/releases"
FRIDA_DOWNLOAD_BASE = "https://github.com/frida/frida/releases/download"

ARCH_MAP = {
    "arm64": "arm64",
    "arm": "arm",
    "x86_64": "x86_64",
    "x86": "x86",
}


def _get_latest_version() -> str:
    utils.verbose("Fetching latest frida-server version...")
    with httpx.Client(follow_redirects=True, timeout=15) as client:
        resp = client.get(FRIDA_GITHUB_RELEASES + "/latest")
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub API returned {resp.status_code}")
        data = resp.json()
        tag = data["tag_name"]
    return tag.lstrip("v")


def _download_frida_server(version: str, arch: str, dest: Path) -> Path:
    base = f"frida-server-{version}-android-{arch}"
    filename = f"{base}.xz"
    url = f"{FRIDA_DOWNLOAD_BASE}/{version}/{filename}"
    utils.info(f"Downloading {filename}...")

    with httpx.Client(follow_redirects=True, timeout=120) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Download failed: HTTP {resp.status_code}")

        tmp = dest.with_suffix(".xz")
        tmp.write_bytes(resp.content)
        utils.verbose(f"Downloaded to {tmp}")

    import lzma
    with lzma.open(tmp) as f:
        data = f.read()
    dest.write_bytes(data)
    dest.chmod(0o755)
    tmp.unlink()
    utils.verbose(f"Extracted to {dest}")
    return dest


def _detect_device_arch(serial: str | None) -> str:
    arch = adb.get_arch(serial)
    mapped = ARCH_MAP.get(arch)
    if not mapped:
        raise RuntimeError(f"Unknown device architecture: {arch}")
    # ponytail: coarse arch mapping, refine if rare archs appear
    return mapped


def _get_cached_path(version: str, arch: str) -> Path:
    utils.FRIDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return utils.FRIDA_CACHE_DIR / f"frida-server-{version}-android-{arch}"


def check_frida_installed() -> str | None:
    import shutil
    frida = shutil.which("frida")
    if frida:
        return frida
    return None


def cmd_install(serial: str | None, version: str | None = None):
    frida_bin = check_frida_installed()
    if not frida_bin:
        utils.warn("frida CLI not found on host. Install with: uv add frida-tools")

    arch = _detect_device_arch(serial)
    ver = version or _get_latest_version()
    utils.info(f"Target: Android {arch}, frida-server v{ver}")

    cached = _get_cached_path(ver, arch)
    if cached.exists():
        utils.info(f"Using cached {cached}")
        binary = cached
    else:
        import tempfile
        tmpdir = Path(tempfile.mkdtemp(prefix="lazyapk-"))
        try:
            tmp_bin = tmpdir / cached.name
            _download_frida_server(ver, arch, tmp_bin)
            utils.FRIDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_bin, cached)
            binary = cached
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    dev_path = "/data/local/tmp/frida-server"
    utils.info("Pushing to device...")
    with utils.Transaction("install-frida-server") as tx:
        pushed = False

        def do_push():
            adb.push(serial, binary, dev_path)
            nonlocal pushed
            pushed = True
        def undo_push():
            if pushed:
                adb.rm(serial, dev_path, timeout=5)

        def do_chmod():
            adb.chmod(serial, dev_path)

        tx.step("push binary", do_push, undo_push)
        tx.step("set executable", do_chmod, None)
        tx.run()

    utils.success(f"frida-server v{ver} installed at {dev_path}")


def cmd_start(serial: str | None):
    if adb.process_exists(serial, "frida-server"):
        utils.warn("frida-server already running")
        return

    dev_path = "/data/local/tmp/frida-server"
    utils.info("Starting frida-server on device...")
    try:
        adb.shell(serial, f"{dev_path} &", timeout=5)
    except Exception:
        pass
    import time
    time.sleep(1)

    if adb.process_exists(serial, "frida-server"):
        utils.success("frida-server is running")
    else:
        utils.fatal("Failed to start frida-server")


def cmd_stop(serial: str | None):
    if not adb.process_exists(serial, "frida-server"):
        utils.warn("frida-server is not running")
        return
    utils.info("Stopping frida-server...")
    adb.kill_process(serial, "frida-server")
    if adb.process_exists(serial, "frida-server"):
        utils.fatal("Failed to stop frida-server")
    utils.success("frida-server stopped")


def cmd_status(serial: str | None):
    if adb.process_exists(serial, "frida-server"):
        utils.success("frida-server is running")
    else:
        utils.info("frida-server is not running")
