import shutil
import subprocess
import sys

from . import adb, utils


def cmd_logcat(serial: str | None, package: str, level: str = "V"):
    utils.setup_signals()

    pid = adb.shell(serial, f"pidof -s {package}", timeout=5).strip()
    if not pid or not pid.isdigit():
        utils.fatal(f"Package '{package}' is not running")

    serial_arg = ["-s", serial] if serial else []
    adb_bin = shutil.which("adb") or utils.fatal("adb not found on PATH")
    cmd = [adb_bin, *serial_arg, "logcat", f"--pid={pid}", f"*:{level}"]

    utils.verbose(f"Running: {' '.join(cmd)}")
    utils.info(f"Logcat for {package} (PID {pid}). Ctrl+C to stop.")

    proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        utils.info("Logcat terminated")
