import os
import signal
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

_verbose = False
_json_output = False
_console = Console(stderr=True)
_stdout = Console(stderr=False)
_interrupted = threading.Event()

XDG_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
CACHE_DIR = XDG_CACHE / "lazyapk"
FRIDA_CACHE_DIR = CACHE_DIR / "frida-server"
SSL_SCRIPT_CACHE = CACHE_DIR / "ssl-unpin.js"


def init_utils(verbose: bool, json_output: bool = False) -> None:
    global _verbose, _json_output
    _verbose = verbose
    _json_output = json_output


def verbose(msg: str) -> None:
    if _verbose:
        _console.log(f"[dim]\\[verbose][/] {msg}")


def log(msg: str) -> None:
    _console.log(msg)


def info(msg: str) -> None:
    _console.print(f"[cyan]→[/] {msg}", highlight=False)


def success(msg: str) -> None:
    _console.print(f"[green]✓[/] {msg}", highlight=False)


def warn(msg: str) -> None:
    _console.print(f"[yellow]⚠[/] {msg}", highlight=False)


def error(msg: str) -> None:
    _console.print(f"[red]✗[/] {msg}", highlight=False)


def fatal(msg: str, code: int = 1) -> None:
    error(msg)
    sys.exit(code)


def stdprint(data: str) -> None:
    _stdout.print(data, highlight=False)


class TransactionError(Exception):
    pass


class Transaction:
    def __init__(self, name: str):
        self.name = name
        self._steps: list[tuple[str, callable, callable]] = []
        self._completed: list[str] = []

    def step(self, description: str, do: callable, undo: callable | None = None):
        self._steps.append((description, do, undo))

    def __enter__(self):
        verbose(f"Begin transaction: {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            verbose(f"Transaction '{self.name}' failed: {exc_val}")
            for step_name in reversed(self._completed):
                verbose(f"Rolling back: {step_name}")
            success(f"Rolled back '{self.name}'")
            return False
        verbose(f"Committed transaction: {self.name}")
        return True

    def run(self):
        for desc, do, undo in self._steps:
            try:
                do()
                self._completed.append(desc)
            except Exception as e:
                error(f"Step '{desc}' failed: {e}")
                self._rollback()
                raise TransactionError(f"Transaction '{self.name}' failed at step '{desc}': {e}") from e

    def _rollback(self):
        for step_name in reversed(self._completed):
            for desc, do, undo in self._steps:
                if desc == step_name and undo:
                    try:
                        undo()
                        verbose(f"Rolled back: {desc}")
                    except Exception as e:
                        warn(f"Rollback of '{desc}' failed: {e}")


@contextmanager
def timeout(seconds: float | None, desc: str = "operation"):
    if seconds is None:
        yield
        return

    timer = threading.Timer(seconds, lambda: _interrupted.set())
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        _interrupted.clear()


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    signame = signal.Signals(signum).name
    warn(f"Received {signame}, shutting down gracefully...")
    _interrupted.set()
    sys.exit(128 + signum)


def setup_signals() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def spinner(desc: str = "Working..."):
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=_console,
        transient=True,
    )
