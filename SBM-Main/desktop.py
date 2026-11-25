"""Desktop startup helpers for the local SBM web interface."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


IS_WINDOWS = os.name == "nt"
WINDOW_TITLE = "SBM"
WINDOW_SIZE = (1440, 900)
APP_ICON_PATH = Path(__file__).resolve().parent / "images" / "logo.ico"
WINDOWS_APP_ID = "SBM.Desktop"
_SW_HIDE = 0
_BUNDLED_WEBVIEW_BINARIES = (
    Path("pythonnet/runtime/Python.Runtime.dll"),
    Path("clr_loader/ffi/dlls/amd64/ClrLoader.dll"),
    Path("webview/lib/Microsoft.Web.WebView2.Core.dll"),
    Path("webview/lib/Microsoft.Web.WebView2.WinForms.dll"),
    Path("webview/lib/WebBrowserInterop.x64.dll"),
    Path("webview/lib/runtimes/win-x64/native/WebView2Loader.dll"),
)


def console_log_path() -> Path:
    return Path.cwd() / "sbm.log"


def hide_console(log_path: Path | None = None) -> bool:
    """Hide a console owned only by SBM and redirect its streams to a log.

    A console shared with the terminal that launched SBM is deliberately left
    alone, because hiding it would also hide the user's terminal window.
    """
    if not IS_WINDOWS:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]

    console_hwnd = kernel32.GetConsoleWindow()
    if not console_hwnd or not _owns_console(kernel32):
        return False

    user32.ShowWindow(ctypes.c_void_p(console_hwnd), _SW_HIDE)
    _redirect_standard_streams(log_path or console_log_path())
    kernel32.FreeConsole()
    return True


def _owns_console(kernel32: Any) -> bool:
    process_ids = (ctypes.c_ulong * 16)()
    attached_processes = kernel32.GetConsoleProcessList(process_ids, len(process_ids))
    return attached_processes == 1


def _redirect_standard_streams(log_path: Path) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        null_fd = os.open(os.devnull, os.O_RDONLY)
    except OSError as error:
        print(f"Could not open the log file {log_path}: {error}")
        return

    # These descriptors must remain valid after FreeConsole(), otherwise later
    # print calls would still point at the detached console handles.
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    os.dup2(null_fd, 0)
    if log_fd > 2:
        os.close(log_fd)
    if null_fd > 2:
        os.close(null_fd)

    sys.stdout = open(1, "w", buffering=1, encoding="utf-8", errors="replace", closefd=False)
    sys.stderr = open(2, "w", buffering=1, encoding="utf-8", errors="replace", closefd=False)
    sys.stdin = open(0, "r", encoding="utf-8", errors="replace", closefd=False)


def unblock_bundled_webview_binaries(base_dir: Path | None = None) -> list[Path]:
    """Remove Internet-zone markers from the .NET files shipped with SBM.

    Windows propagates the downloaded ZIP's ``Zone.Identifier`` stream to
    extracted files.  The executable itself may still run, but .NET Framework
    then refuses to load Python.Runtime.dll and clr_loader reports the rather
    misleading "Failed to resolve ... Loader.Initialize" error.

    Only SBM's explicitly listed pywebview/pythonnet binaries are touched.
    Source checkouts normally have none of these files next to desktop.py, so
    this is effectively a frozen-build startup repair.
    """
    if not IS_WINDOWS:
        return []

    bundle_dir = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    unblocked: list[Path] = []
    failures: list[tuple[Path, OSError]] = []

    for relative_path in _BUNDLED_WEBVIEW_BINARIES:
        binary_path = bundle_dir / relative_path
        if not binary_path.is_file():
            continue

        zone_identifier = f"{binary_path}:Zone.Identifier"
        try:
            os.remove(zone_identifier)
        except FileNotFoundError:
            continue
        except OSError as error:
            failures.append((binary_path, error))
        else:
            unblocked.append(binary_path)

    if unblocked:
        print(f"Removed Windows download blocking from {len(unblocked)} bundled UI file(s).")
    for binary_path, error in failures:
        print(f"Could not remove Windows download blocking from {binary_path}: {error}")

    return unblocked


def webview2_runtime_available() -> bool:
    """Whether the Edge WebView2 runtime that pywebview's window needs is installed.

    pywebview silently falls back to the deprecated MSHTML (Internet Explorer)
    renderer when the runtime is missing, and the dashboard does not work there.
    Treat a missing runtime as "no desktop window" so the app window is used.
    """
    if not IS_WINDOWS:
        return True
    try:
        import winreg
    except ImportError:
        return False

    client_guids = (
        "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",  # WebView2 runtime
        "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",  # beta
        "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",  # dev
        "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",  # canary
    )
    paths = [
        rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"
        for guid in client_guids
    ] + [
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"
        for guid in client_guids
    ]
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    version, _kind = winreg.QueryValueEx(key, "pv")
            except OSError:
                continue
            if version and str(version) != "0.0.0.0":
                return True
    return False


def find_chromium_browser() -> str | None:
    """Path of an installed Edge or Chrome, used for a chromeless app window."""
    if not IS_WINDOWS:
        return None

    candidates: list[Path] = []

    # Windows registers installed browsers under App Paths; this also finds custom
    # install locations that the standard folders below miss.
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for exe in ("msedge.exe", "chrome.exe", "brave.exe"):
                for view in (0, winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(
                            hive,
                            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                            0,
                            winreg.KEY_READ | view,
                        ) as key:
                            value, _kind = winreg.QueryValueEx(key, "")
                    except OSError:
                        continue
                    if value:
                        candidates.append(Path(value))
    except ImportError:
        pass

    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if not base:
            continue
        candidates.extend([
            Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(base) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ])
    for name in ("msedge", "chrome", "brave"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def open_app_window(local_url: str, window_size: tuple[int, int] = WINDOW_SIZE) -> bool:
    """Open the dashboard as a standalone Edge/Chrome app window (no tabs or address bar).

    Used when pywebview cannot start, so the UI still opens in its own window on
    machines without the WebView2 runtime instead of in the user's browser.
    """
    executable = find_chromium_browser()
    if not executable:
        return False
    try:
        subprocess.Popen(
            [
                executable,
                f"--app={local_url}",
                f"--window-size={window_size[0]},{window_size[1]}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        print(f"Could not open the app window: {error}")
        return False
    return True


def import_webview() -> tuple[Any | None, Exception | None]:
    """Return the optional pywebview module, or the reason it could not load."""
    unblock_bundled_webview_binaries()
    try:
        # Keep this as a regular import so PyInstaller can discover pywebview
        # and run its hook, which bundles the Windows WebView2/.NET files.
        import webview

        return webview, None
    except Exception as error:
        return None, error


def set_windows_app_id(app_id: str = WINDOWS_APP_ID) -> bool:
    """Give interpreted runs their own Windows taskbar identity.

    Without an explicit AppUserModelID, Windows groups the pywebview form under
    python.exe and may keep showing Python's icon even when Form.Icon is set.
    """
    if not IS_WINDOWS:
        return False

    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        return set_app_id(app_id) >= 0
    except (AttributeError, OSError):
        return False


def run_webview(
    app: Any,
    local_url: str,
    webview_module: Any,
    on_close: Callable[[], None] | None = None,
    window_size: tuple[int, int] = WINDOW_SIZE,
    window_title: str = WINDOW_TITLE,
) -> None:
    """Serve Flask in the background and run pywebview on the main thread."""
    from werkzeug.serving import make_server

    set_windows_app_id()
    host = "127.0.0.1"
    port = int(local_url.rsplit(":", 1)[1].split("/", 1)[0])
    server = make_server(host, port, app, threaded=True)
    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="sbm-web-server",
    )
    server_thread.start()

    try:
        window = webview_module.create_window(
            window_title,
            local_url,
            width=window_size[0],
            height=window_size[1],
            maximized=True,
        )
        if on_close is not None:
            window.events.closed += lambda *_args: on_close()
        print("SBM is running in a pywebview desktop window.")
        icon = str(APP_ICON_PATH) if APP_ICON_PATH.is_file() else None
        webview_module.start(icon=icon)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
