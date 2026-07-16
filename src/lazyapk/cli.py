import sys

import click

from . import utils
from . import adb as adb_mod
from . import frida_mgr, proxy as proxy_mod, search, ssl, transfer, info as info_mod, logcat as logcat_mod, manifest as manifest_mod

_EPILOG = """
Examples:

  lazyapk search --query banking
  lazyapk info com.example.app
  lazyapk manifest com.example.app
  lazyapk logcat com.example.app
  lazyapk pull com.example.app -o ./apks
  lazyapk proxy set 192.168.1.1 8080
  lazyapk frida install
  lazyapk frida start
  lazyapk unpin com.example.app
  lazyapk doctor
"""


class _GlobalState:
    def __init__(self):
        self.serial: str | None = None
        self.verbose: bool = False
        self.json: bool = False


pass_state = click.make_pass_decorator(_GlobalState, ensure=True)


def _resolve_serial(ctx: click.Context, param: click.Parameter, value: str | None):
    state = ctx.ensure_object(_GlobalState)
    if value:
        state.serial = value
    return value


def _set_verbose(ctx: click.Context, param: click.Parameter, value: bool):
    if value:
        utils.init_utils(verbose=True)
        state = ctx.ensure_object(_GlobalState)
        state.verbose = True
    return value


def _set_json(ctx: click.Context, param: click.Parameter, value: bool):
    if value:
        state = ctx.ensure_object(_GlobalState)
        state.json = True
        utils.init_utils(verbose=state.verbose, json_output=True)
    return value


@click.group(epilog=_EPILOG)
@click.option(
    "-s", "--serial",
    help="Device serial number. Required when multiple devices connected.",
    metavar="SERIAL",
    callback=_resolve_serial,
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Show detailed command output for debugging.",
    callback=_set_verbose,
)
@click.option(
    "--json",
    is_flag=True,
    help="Output results in JSON format for machine parsing.",
    callback=_set_json,
)
@click.version_option(version="1.0.0", prog_name="lazyapk")
def cli(**kwargs):
    """
    LazyAPK — A toolbox of practical ADB and Frida commands for Android hacking and debugging.

    Every command runs against a single connected device. If exactly one device
    is connected, it is auto-selected. Use -s <serial> when multiple devices
    are present.
    """
    pass


# ── search ──────────────────────────────────────────────────────────


@cli.command("search")
@click.option("-q", "--query", help="General search across package name and label.")
@click.option("-n", "--name", help="Search by package name (partial, fuzzy).")
@click.option("-l", "--label", help="Search by app label (partial, fuzzy).")
@click.option("-u", "--user", is_flag=True, help="Show only user-installed packages.")
@click.option("--system", is_flag=True, help="Show only system packages.")
@click.option("--third-party", is_flag=True, help="Show only third-party packages.")
@click.option("--all", "all_pkgs", is_flag=True, help="Show all packages (no filter).")
@click.option("--min-score", type=int, default=60, show_default=True, help="Minimum fuzzy match score (0-100).")
@pass_state
def cmd_search(
    state: _GlobalState,
    query: str | None,
    name: str | None,
    label: str | None,
    user: bool,
    system: bool,
    third_party: bool,
    all_pkgs: bool,
    min_score: int,
):
    """Search and list Android packages on the device.

    Powerful fuzzy search across package names and app labels. Combine
    filters to narrow results. Defaults to user-installed packages only
    when no --all flag is given.
    """
    utils.init_utils(verbose=state.verbose, json_output=state.json)
    utils.setup_signals()

    serial = _serial(state)

    if not query and not name and not label and not all_pkgs and not user and not system and not third_party:
        user = True

    try:
        with utils.spinner("Fetching packages...") as p:
            p.add_task("", total=None)
            apps = search.fetch_packages(serial, user_only=user, system_only=system, third_party=third_party)
    except adb_mod.AdbError as e:
        utils.fatal(str(e))

    if not apps:
        utils.info("No packages found matching filters")
        return

    ranked = search.search_apps(apps, query=query, name=name, label=label, min_score=min_score)
    search.display_apps(ranked, json_output=state.json)


# ── pull ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@click.option("-o", "--output", type=click.Path(file_okay=False), default=".", show_default=True, help="Output directory for APK files.")
@click.option("--all", "all_splits", is_flag=True, help="Pull all split APKs, not just base.")
@pass_state
def pull(state: _GlobalState, package: str, output: str, all_splits: bool):
    """Pull APK(s) from a device to the local machine.

    Given a package name, finds the APK path on device and pulls it.
    For apps with split APKs, only the base APK is pulled unless
    --all is specified.
    """
    utils.init_utils(verbose=state.verbose, json_output=state.json)
    utils.setup_signals()

    serial = _serial(state)
    transfer.pull_apk(serial, package, output, all_splits=all_splits, json_output=state.json)


# ── proxy ───────────────────────────────────────────────────────────


@cli.group()
def proxy():
    """Manage HTTP proxy settings on the device (global).

    Uses Android's global proxy settings. Requires root or a debuggable
    device for some operations on newer Android versions.
    """
    pass


@proxy.command("set")
@click.argument("host", metavar="HOST")
@click.argument("port", type=int, metavar="PORT")
@pass_state
def proxy_set(state: _GlobalState, host: str, port: int):
    """Set the device's global HTTP proxy to HOST:PORT."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    proxy_mod.cmd_set(serial, host, port)


@proxy.command("get")
@pass_state
def proxy_get(state: _GlobalState):
    """Show the current HTTP proxy configuration."""
    utils.init_utils(verbose=state.verbose, json_output=state.json)
    utils.setup_signals()
    serial = _serial(state)
    proxy_mod.cmd_get(serial, json_output=state.json)


@proxy.command("clear")
@pass_state
def proxy_clear(state: _GlobalState):
    """Remove the global HTTP proxy configuration."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    proxy_mod.cmd_clear(serial)


# ── frida ───────────────────────────────────────────────────────────


@cli.group()
def frida():
    """Manage frida-server on the device.

    Handles the full lifecycle: download, install, start, stop, status.
    frida-server is required for Frida-based operations like SSL unpinning.
    """
    pass


@frida.command("install")
@click.option("--version", help="Specific frida-server version (default: latest).")
@pass_state
def frida_install(state: _GlobalState, version: str | None):
    """Download and install frida-server onto the device.

    Auto-detects device architecture and downloads the matching binary.
    Caches binaries in ~/.cache/lazyapk/frida-server/.
    """
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    try:
        frida_mgr.cmd_install(serial, version=version)
    except Exception as e:
        utils.fatal(str(e))


@frida.command("start")
@pass_state
def frida_start(state: _GlobalState):
    """Start frida-server in the background on the device."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    frida_mgr.cmd_start(serial)


@frida.command("stop")
@pass_state
def frida_stop(state: _GlobalState):
    """Stop frida-server on the device."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    frida_mgr.cmd_stop(serial)


@frida.command("status")
@pass_state
def frida_status(state: _GlobalState):
    """Check if frida-server is running on the device."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    frida_mgr.cmd_status(serial)


# ── unpin ───────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@click.option("--attach", is_flag=True, help="Attach to a running app process instead of spawning a new one.")
@pass_state
def unpin(state: _GlobalState, package: str, attach: bool):
    """Bypass SSL pinning on a target app using Frida.

    Downloads the universal frida-interception-and-unpinning script
    from httptoolkit and runs it against the target app.

    Requires frida-server to be running on the device. Start it with
    'lazyapk frida start' before running this command.
    """
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)

    try:
        ssl.cmd_unpin(serial, package, attach=attach)
    except Exception as e:
        utils.fatal(str(e))


# ── helpers ─────────────────────────────────────────────────────────




# ── info ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@pass_state
def info(state: _GlobalState, package: str):
    """Show detailed info about an installed package.

    Queries the device's package manager and displays version,
    permissions, components, and other metadata.
    """
    utils.init_utils(verbose=state.verbose, json_output=state.json)
    utils.setup_signals()
    serial = _serial(state)
    try:
        info_mod.cmd_info(serial, package, json_output=state.json)
    except adb_mod.AdbError as e:
        utils.fatal(str(e))


# ── logcat ──────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@click.option("--level", "-l", default="V", show_default=True,
              type=click.Choice(["V", "D", "I", "W", "E", "F"], case_sensitive=False),
              help="Minimum log level to show.")
@pass_state
def logcat(state: _GlobalState, package: str, level: str):
    """Stream logcat output filtered to a specific package.

    Shows only log messages from the given app process. Requires
    the app to be running. Press Ctrl+C to stop.
    """
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    logcat_mod.cmd_logcat(serial, package, level=level.upper())


# ── manifest ────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@pass_state
def manifest(state: _GlobalState, package: str):
    """Show the AndroidManifest.xml of an installed app.

    Pulls the APK from the device and parses its binary manifest
    using pyaxmlparser. Shows package info, permissions, and all
    components with their intent filters.
    """
    utils.init_utils(verbose=state.verbose, json_output=state.json)
    utils.setup_signals()
    serial = _serial(state)
    try:
        manifest_mod.cmd_manifest(serial, package, json_output=state.json)
    except Exception as e:
        utils.fatal(str(e))


# ── doctor ──────────────────────────────────────────────────────────


@cli.command()
@pass_state
def doctor(state: _GlobalState):
    """Check environment for all required and optional tools.

    Scans PATH for every tool lazyapk can use and reports what's
    installed, what's missing, and how to install it.
    """
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    doctor_cmd()
def _serial(state: _GlobalState) -> str | None:
    if state.serial:
        return state.serial
    try:
        return adb_mod.resolve_device(None)
    except adb_mod.MultipleDevices as e:
        utils.fatal(str(e))
    except adb_mod.DeviceNotFound as e:
        utils.fatal(str(e))


def main():
    utils.setup_signals()

    try:
        cli(obj={})
    except adb_mod.DeviceNotFound as e:
        utils.fatal(f"No device connected: {e}")
    except adb_mod.MultipleDevices as e:
        utils.fatal(str(e))
    except adb_mod.AdbError as e:
        utils.fatal(f"ADB error: {e}")
    except KeyboardInterrupt:
        utils.info("Interrupted by user")
        sys.exit(128 + 2)
    except Exception as e:
        if utils._verbose:
            import traceback
            utils._console.print_exception()
        utils.fatal(f"{type(e).__name__}: {e}")

def doctor_cmd():
    import shutil
    from rich.table import Table
    from rich.panel import Panel

    results = []
    for cmd, desc, hint in [
        ("adb", "Required for all commands", "apt install adb / brew install android-platform-tools"),
        ("frida", "Required for unpin", "uv tool install frida-tools"),
    ]:
        path = shutil.which(cmd)
        results.append(("\u2705" if path else "\u274c", cmd, desc, path or hint))

    try:
        import pyaxmlparser
        results.append(("\u2705", "pyaxmlparser", "Required for manifest", "installed"))
    except ImportError:
        results.append(("\u274c", "pyaxmlparser", "Required for manifest", "uv add pyaxmlparser"))

    try:
        devs = adb_mod.get_devices()
        results.append(("\U0001f4f1", "device", "Connected device", f"{len(devs)} device(s): {', '.join(d['serial'] for d in devs)}"))
    except adb_mod.DeviceNotFound:
        results.append(("\U0001f4f1", "device", "Connected device", "No device connected"))
    except adb_mod.MultipleDevices as e:
        results.append(("\U0001f4f1", "device", "Connected device", str(e)))

    try:
        serial = adb_mod.resolve_device(None)
        if adb_mod.process_exists(serial, "frida-server"):
            results.append(("\u2705", "frida-server", "Required for unpin", "Running"))
        else:
            results.append(("\u274c", "frida-server", "Required for unpin", "Not running. Start: lazyapk frida start"))
    except Exception:
        results.append(("\u274c", "frida-server", "Required for unpin", "Unknown"))

    t = Table()
    t.add_column(style="bold")
    t.add_column("Component", style="cyan")
    t.add_column("Requirement", style="dim")
    t.add_column("Status", style="white")
    for icon, name, req, status in results:
        t.add_row(icon, name, req, str(status))
    utils._stdout.print(Panel(t, title="[bold]lazyapk Doctor", border_style="blue"))

# ── launch ──────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@pass_state
def launch(state: _GlobalState, package: str):
    """Launch an app on the device.

    Starts the main activity of the given package using monkey.
    """
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    try:
        adb_mod.shell(serial, f"monkey -p {package} 1", timeout=10)
        utils.success(f"Launched {package}")
    except adb_mod.AdbError as e:
        utils.fatal(str(e))


# ── kill ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("package", metavar="PACKAGE")
@pass_state
def kill(state: _GlobalState, package: str):
    """Stop a running app process.

    Uses am force-stop. Works on all devices (no root needed)."""
    utils.init_utils(verbose=state.verbose)
    utils.setup_signals()
    serial = _serial(state)
    try:
        adb_mod.shell(serial, f"am force-stop {package}", timeout=10)
        utils.success(f"Stopped {package}")
    except adb_mod.AdbError:
        utils.info(f"Package {package} is not running")
