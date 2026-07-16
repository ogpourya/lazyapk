import re

from . import adb, utils


def _parse_dumpsys(raw: str) -> dict:
    info: dict = {}

    pkg_match = re.search(r'Package\s+\[([^\]]+)\]\s+\((\w+)\)', raw)
    if pkg_match:
        info["name"] = pkg_match.group(1)
        info["uid"] = pkg_match.group(2)

    vc = re.search(r'versionCode=(\S+)', raw)
    if vc:
        info["version_code"] = vc.group(1)
    vn = re.search(r'versionName=(\S+)', raw)
    if vn:
        info["version_name"] = vn.group(1)

    sdk = re.search(r'compileSdk=\'(\d+)\'', raw)
    if sdk:
        info["compile_sdk"] = sdk.group(1)
    min_sdk = re.search(r'minSdk=(\d+)', raw)
    if min_sdk:
        info["min_sdk"] = min_sdk.group(1)
    target_sdk = re.search(r'targetSdk=(\d+)', raw)
    if target_sdk:
        info["target_sdk"] = target_sdk.group(1)

    installer = re.search(r'installerPackageName=([^\s]+)', raw)
    if installer:
        info["installer"] = installer.group(1)

    flags = re.search(r'pkgFlags=\[([^\]]+)\]', raw)
    if flags:
        info["flags"] = [f.strip() for f in flags.group(1).split()]

    perms = []
    in_perms = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped == "installPermissions:":
            in_perms = True
            continue
        if in_perms:
            if not stripped or line[0] != ' ':
                in_perms = False
                continue
            perms.append(stripped.split("=")[0].strip())
    info["permissions"] = perms

    return info


def _pm_dump(serial: str | None, package: str) -> str:
    raw = adb.shell(serial, f"dumpsys package {package}", timeout=15)
    if "Unable to find" in raw or "not found" in raw:
        raise adb.AdbError(f"Package '{package}' not found")
    return raw


def cmd_info(serial: str | None, package: str, json_output: bool = False):
    raw = _pm_dump(serial, package)
    info = _parse_dumpsys(raw)

    if json_output:
        import json
        utils.stdprint(json.dumps(info, indent=2, ensure_ascii=False))
        return

    if not info.get("name"):
        utils.fatal(f"No info found for package '{package}'")

    from rich.table import Table
    from rich.panel import Panel

    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold cyan")
    g.add_column()
    g.add_row("Package", info.get("name", "—"))
    g.add_row("UID", info.get("uid", "—"))
    g.add_row("Version", f'{info.get("version_name", "—")} ({info.get("version_code", "—")})')
    g.add_row("SDK", f'min={info.get("min_sdk", "—")}  target={info.get("target_sdk", "—")}  compile={info.get("compile_sdk", "—")}')
    g.add_row("Installer", info.get("installer", "—"))
    g.add_row("Flags", " | ".join(info.get("flags", [])))
    utils._stdout.print(Panel(g, title="[bold]Package Info", border_style="cyan"))

    perms = info.get("permissions", [])
    if perms:
        pt = Table(title=f"Permissions ({len(perms)})")
        pt.add_column("Permission", style="green")
        for p in perms:
            pt.add_row(p)
        utils._stdout.print(pt)
