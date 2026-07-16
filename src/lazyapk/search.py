from rapidfuzz import fuzz, process

from . import adb, utils


class AppInfo:
    def __init__(self, package: str, label: str = "", version: str = "", category: str = ""):
        self.package = package
        self.label = label
        self.version = version
        self.category = category

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "label": self.label or self.package.rsplit(".", 1)[-1],
            "version": self.version,
            "category": self.category or ("system" if self.category == "system" else "third-party"),
        }

    @classmethod
    def from_package(cls, package: str) -> "AppInfo":
        return cls(package=package)


def categorize_package(package: str) -> str:
    prefixes = [
        "android.", "com.android.", "com.google.android.", "com.qualcomm.",
        "com.mediatek.", "com.samsung.", "com.xiaomi.", "com.miui.",
        "com.oneplus.", "com.oppo.", "com.vivo.", "com.realme.",
        "com.asus.", "com.lge.", "com.sony.", "com.huawei.",
        "com.sec.", "com.htc.", "com.nokia.",
    ]
    for prefix in prefixes:
        if package.startswith(prefix):
            return "system"
    return "third-party"


def fetch_packages(serial: str | None, user_only: bool = False, system_only: bool = False, third_party: bool = False) -> list[AppInfo]:
    all_pkgs = adb.list_packages(serial)
    apps = []
    for pkg in all_pkgs:
        cat = categorize_package(pkg)
        if system_only and cat != "system":
            continue
        if third_party and cat != "third-party":
            continue
        if user_only and cat != "third-party":
            continue
        apps.append(AppInfo(package=pkg, category=cat))

    if user_only:
        try:
            raw = adb.shell(serial, "cmd package list packages -3", timeout=10)
            user_pkgs = set()
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    user_pkgs.add(line[8:])
            apps = [a for a in apps if a.package in user_pkgs]
            for a in apps:
                a.category = "user"
        except Exception:
            pass

    return apps


def search_apps(
    apps: list[AppInfo],
    query: str | None = None,
    name: str | None = None,
    label: str | None = None,
    min_score: int = 60,
) -> list[tuple[AppInfo, int]]:

    results: dict[str, tuple[AppInfo, int]] = {}

    candidates = []
    for app in apps:
        display_name = app.label or app.package.rsplit(".", 1)[-1]
        candidates.append((app, app.package, display_name))

    if query:
        q = query.lower()
        for app in apps:
            display = app.label or app.package.rsplit(".", 1)[-1]
            score = 0
            for text in (app.package, display):
                t = text.lower()
                if q in t:
                    score = max(score, int(90 + 10 * (len(q) / len(t))))
                else:
                    fuzzy = fuzz.WRatio(q, t)
                    if fuzzy >= 70:
                        score = max(score, int(fuzzy))
            if score:
                existing = results.get(app.package)
                if not existing or score > existing[1]:
                    results[app.package] = (app, score)

    if name:
        n = name.lower()
        for app in apps:
            t = app.package.lower()
            score = 0
            if n in t:
                score = int(90 + 10 * (len(n) / len(t)))
            else:
                fuzzy = fuzz.partial_ratio(n, t)
                if fuzzy >= 70:
                    score = int(fuzzy)
            if score:
                existing = results.get(app.package)
                if not existing or score > existing[1]:
                    results[app.package] = (app, score)

    if label:
        l = label.lower()
        for app in apps:
            display = (app.label or app.package.rsplit(".", 1)[-1]).lower()
            score = 0
            if l in display:
                score = int(90 + 10 * (len(l) / len(display)))
            else:
                fuzzy = fuzz.partial_ratio(l, display)
                if fuzzy >= 70:
                    score = int(fuzzy)
            if score:
                existing = results.get(app.package)
                if not existing or score > existing[1]:
                    results[app.package] = (app, score)

    if not query and not name and not label:
        return [(app, 100) for app in apps]

    ranked = sorted(results.values(), key=lambda x: (-x[1], x[0].package))
    return ranked


def display_apps(ranked: list[tuple[AppInfo, int]], json_output: bool = False) -> None:
    if json_output:
        import json
        data = [{"package": a.package, "label": a.label, "version": a.version, "category": a.category, "score": s} for a, s in ranked]
        utils.stdprint(json.dumps(data, indent=2, ensure_ascii=False))
        return

    from rich.table import Table
    table = Table(title=f"Found {len(ranked)} packages")
    table.add_column("Package", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Score", style="dim", justify="right")

    for app, score in ranked:
        label = app.label or app.package.rsplit(".", 1)[-1]
        cat = app.category or categorize_package(app.package)
        table.add_row(app.package, label, cat, str(score))

    utils._stdout.print(table)
