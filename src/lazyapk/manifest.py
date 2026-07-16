import json
import tempfile
from pathlib import Path

from . import adb, utils


def _parse_manifest(apk_path: Path) -> dict:
    try:
        from pyaxmlparser import APK
        a = APK(apk_path)
    except Exception as e:
        raise RuntimeError(f"Failed to parse APK: {e}")

    info: dict = {}
    info["package"] = a.package
    info["version"] = a.version_name or "—"
    info["version_code"] = str(a.version_code) if a.version_code else "—"
    info["min_sdk"] = str(a.get_min_sdk_version()) if a.get_min_sdk_version() else "—"
    info["target_sdk"] = str(a.get_target_sdk_version()) if a.get_target_sdk_version() else "—"

    try:
        ns = "http://schemas.android.com/apk/res/android"
        root = a.axml
        info["permissions"] = []
        for child in root.iter():
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "uses-permission":
                name = child.get(f'{{{ns}}}name')
                if name:
                    info["permissions"].append(name)

        info["components"] = []
        for child in root.iter():
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("activity", "service", "receiver", "provider"):
                name = child.get(f'{{{ns}}}name')
                exported = child.get(f'{{{ns}}}exported', "?")
                comp = {"type": tag, "name": name or "?", "exported": exported}
                ifilters = []
                for intent in child.findall("intent-filter"):
                    actions = intent.findall("action")
                    cats = intent.findall("category")
                    datas = intent.findall("data")
                    entry = {}
                    if actions:
                        entry["actions"] = [a.get(f'{{{ns}}}name') for a in actions if a.get(f'{{{ns}}}name')]
                    if cats:
                        entry["categories"] = [c.get(f'{{{ns}}}name') for c in cats if c.get(f'{{{ns}}}name')]
                    if datas:
                        d = {}
                        for dt in datas:
                            for attr in ("scheme", "host", "mimeType"):
                                v = dt.get(f'{{{ns}}}{attr}')
                                if v:
                                    d[attr] = v
                        if d:
                            entry["data"] = d
                    if entry:
                        ifilters.append(entry)
                if ifilters:
                    comp["intent_filters"] = ifilters
                info["components"].append(comp)
    except Exception as e:
        utils.verbose(f"Component parsing error: {e}")

    return info


def cmd_manifest(serial: str | None, package: str, json_output: bool = False):
    paths = adb.path_for_package(serial, package)
    if not paths:
        utils.fatal(f"Package '{package}' not found")

    with tempfile.TemporaryDirectory(prefix="lazyapk-") as tmp:
        local = Path(tmp) / f"{package}.apk"
        utils.info("Pulling APK to analyze manifest...")
        adb.pull(serial, paths[0], local)
        info = _parse_manifest(local)

    if json_output:
        utils.stdprint(json.dumps(info, indent=2, ensure_ascii=False))
        return

    from rich.table import Table
    from rich.panel import Panel

    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold cyan")
    g.add_column()
    g.add_row("Package", info.get("package", "—"))
    g.add_row("Version", f'{info.get("version", "—")} ({info.get("version_code", "—")})')
    g.add_row("SDK", f'min={info.get("min_sdk", "—")}  target={info.get("target_sdk", "—")}')
    utils._stdout.print(Panel(g, title="[bold]AndroidManifest", border_style="cyan"))

    perms = info.get("permissions", [])
    if perms:
        pt = Table(title=f"Permissions ({len(perms)})")
        pt.add_column("Permission", style="green")
        for p in perms:
            pt.add_row(p)
        utils._stdout.print(pt)

    comps = info.get("components", [])
    if comps:
        ct = Table(title=f"Components ({len(comps)})")
        ct.add_column("Type", style="yellow")
        ct.add_column("Name", style="white")
        ct.add_column("Exported", style="dim")
        ct.add_column("Intent Filters", style="cyan")
        for c in comps:
            ifs = c.get("intent_filters", [])
            summary = ""
            for f in ifs:
                parts = []
                acts = f.get("actions", [])
                if acts:
                    parts.append(", ".join(a.rsplit(".", 1)[-1] for a in acts[:2]))
                data = f.get("data", {})
                if data:
                    dparts = []
                    for k in ("scheme", "host", "mimeType"):
                        if k in data:
                            dparts.append(data[k])
                    if dparts:
                        parts.append(":".join(dparts))
                if parts:
                    summary = "; ".join(parts)
            ct.add_row(c["type"], c["name"].rsplit(".", 1)[-1], str(c.get("exported", "?")), summary or "—")
        utils._stdout.print(ct)
