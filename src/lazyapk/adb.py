import shlex
import subprocess
import sys
from pathlib import Path

from . import utils


class AdbError(Exception):
    pass


class DeviceNotFound(AdbError):
    pass


class MultipleDevices(AdbError):
    pass


def _check_adb() -> str:
    adb = "adb"
    if utils._verbose:
        utils.verbose("Looking for adb on PATH...")
    import shutil
    path = shutil.which(adb)
    if not path:
        utils.fatal(
            "adb not found. Install it:\n"
            "  Linux:  apt install adb  |  pacman -S android-tools\n"
            "  macOS:  brew install android-platform-tools\n"
            "  Windows: https://developer.android.com/studio/releases/platform-tools"
        )
    return path


def _run_adb(args: list[str], timeout: int = 30) -> str:
    cmd = [_check_adb()] + args
    utils.verbose(f"adb: {' '.join(shlex.quote(a) for a in args)}")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise AdbError(f"adb command timed out after {timeout}s: {' '.join(args)}")

    if r.returncode != 0:
        err = r.stderr.strip() or r.stdout.strip()
        raise AdbError(f"adb failed: {err}")

    return r.stdout.strip()


def _device_arg(serial: str | None) -> list[str]:
    return ["-s", serial] if serial else []


def get_devices(serial: str | None = None) -> list[dict]:
    raw = _run_adb(["devices", "-l"])
    lines = [l for l in raw.splitlines() if l and not l.startswith("List")]
    devices = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1] != "offline":
            dev = {"serial": parts[0], "state": parts[1]}
            for p in parts[2:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    dev[k] = v
            devices.append(dev)

    if serial:
        if not any(d["serial"] == serial for d in devices):
            raise DeviceNotFound(f"Device '{serial}' not found")
        return [d for d in devices if d["serial"] == serial]

    if len(devices) == 0:
        raise DeviceNotFound("No devices connected")
    if len(devices) > 1:
        serials = "\n".join(f"  {d['serial']}" for d in devices)
        raise MultipleDevices(
            f"Multiple devices connected. Use -s <serial>:\n{serials}"
        )
    return devices


def resolve_device(serial: str | None = None) -> str:
    devs = get_devices(serial)
    return devs[0]["serial"]


def shell(serial: str | None, command: str, timeout: int = 30) -> str:
    return _run_adb(_device_arg(serial) + ["shell", command], timeout=timeout)


def list_packages(serial: str | None, options: str = "") -> list[str]:
    raw = shell(serial, f"pm list packages {options}", timeout=15)
    pkgs = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line[8:])
    return sorted(pkgs)


def get_arch(serial: str | None) -> str:
    arch = shell(serial, "uname -m", timeout=10)
    arch = arch.strip()
    mapping = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "arm",
        "arm": "arm",
        "x86_64": "x86_64",
        "x86": "x86",
    }
    return mapping.get(arch, arch)


def path_for_package(serial: str | None, package: str) -> list[str]:
    raw = shell(serial, f"pm path {package}", timeout=10)
    paths = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            paths.append(line[8:])
    return paths


def pull(serial: str | None, remote: str, local: str | Path, timeout: int = 60):
    _run_adb(_device_arg(serial) + ["pull", remote, str(local)], timeout=timeout)


def push(serial: str | None, local: str | Path, remote: str, timeout: int = 60):
    _run_adb(_device_arg(serial) + ["push", str(local), remote], timeout=timeout)


def install(serial: str | None, apk_paths: list[Path], timeout: int = 120):
    args = _device_arg(serial) + ["install-multiple" if len(apk_paths) > 1 else "install", "-r", "-d"]
    for p in apk_paths:
        args.append(str(p))
    _run_adb(args, timeout=timeout)


def kill_process(serial: str | None, name: str, timeout: int = 10):
    try:
        shell(serial, f"killall {name}", timeout=timeout)
    except AdbError:
        pass


def process_exists(serial: str | None, name: str) -> bool:
    try:
        out = shell(serial, f"pgrep -x {name}", timeout=5)
        return out.strip().isdigit()
    except AdbError:
        return False


def chmod(serial: str | None, path: str, mode: str = "755", timeout: int = 10):
    shell(serial, f"chmod {mode} {path}", timeout=timeout)


def rm(serial: str | None, path: str, timeout: int = 10):
    shell(serial, f"rm -f {path}", timeout=timeout)


def settings_get(serial: str | None, namespace: str, key: str) -> str:
    return shell(serial, f"settings get {namespace} {key}", timeout=10)


def settings_put(serial: str | None, namespace: str, key: str, value: str):
    shell(serial, f"settings put {namespace} {key} {value}", timeout=10)


def pm_list_packages(serial: str | None, filter_flag: str | None = None) -> list[str]:
    opts = filter_flag if filter_flag else ""
    return list_packages(serial, opts)
