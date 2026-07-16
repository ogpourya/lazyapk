from pathlib import Path

from . import adb, utils


def pull_apk(serial: str | None, package: str, output_dir: str | Path, all_splits: bool = False, json_output: bool = False) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    utils.info(f"Resolving APK paths for {package}...")
    paths = adb.path_for_package(serial, package)

    if not paths:
        utils.fatal(f"Package '{package}' not found on device")

    if len(paths) > 1 and not all_splits:
        utils.info(f"Package has {len(paths)} split APKs. Use --all to pull all")
        paths = paths[:1]

    pulled = []
    for remote in paths:
        name = f"{package}.apk" if len(paths) == 1 else f"{package}.{Path(remote).name}"
        local = output / name
        utils.info(f"Pulling {remote} → {local}")
        adb.pull(serial, remote, local)
        pulled.append(local)
        utils.success(f"Pulled {local}")

    if json_output:
        import json
        utils.stdprint(json.dumps([str(p) for p in pulled], indent=2))
    else:
        utils.success(f"Done — {len(pulled)} APK(s) saved to {output}")

    return pulled
