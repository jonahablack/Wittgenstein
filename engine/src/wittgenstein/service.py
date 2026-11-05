"""Wittgenstein as a local background service, beside the user's RAG app.

- start / stop / status: run the server detached from any terminal (state and log in
  ~/.wittgenstein: server.json, server.log).
- autostart enable / disable: start it at login (macOS launchd agent, Linux systemd
  user unit, Windows Startup folder).
- run: start a Python program with the LangChain / LlamaIndex hooks loaded, without
  installing anything into that program's environment (a sitecustomize shim).
- settings (config.json): the model-proxy upstreams and the port, applied by `serve`.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

LABEL = "org.wittgenstein.server"
DEFAULT_PORT = 8100


def home() -> Path:
    h = Path(os.environ.get("WITTGENSTEIN_HOME", "~/.wittgenstein")).expanduser()
    h.mkdir(parents=True, exist_ok=True)
    return h


# --------------------------------------------------------------------------- settings
def load_config() -> dict[str, Any]:
    p = home() / "config.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def save_config(updates: dict[str, Any]) -> dict[str, Any]:
    cfg = {**load_config(), **{k: v for k, v in updates.items() if v is not None}}
    (home() / "config.json").write_text(json.dumps(cfg, indent=2))
    return cfg


_CONFIG_ENV = {
    "openai_upstream": "WITTGENSTEIN_OPENAI_UPSTREAM",
    "anthropic_upstream": "WITTGENSTEIN_ANTHROPIC_UPSTREAM",
}


def apply_config_env() -> None:
    """Settings saved with `wittgenstein start --openai-upstream ...` become the server's
    environment defaults (an explicit environment variable still wins)."""
    cfg = load_config()
    for key, env in _CONFIG_ENV.items():
        if cfg.get(key):
            os.environ.setdefault(env, str(cfg[key]))


# --------------------------------------------------------------------------- process
def url(port: int | None = None) -> str:
    return f"http://127.0.0.1:{port or load_config().get('port') or DEFAULT_PORT}"


def responding(port: int | None = None, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url(port) + "/live/config", timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False


def _state() -> dict[str, Any]:
    p = home() / "server.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _serve_argv(port: int) -> list[str]:
    return [sys.executable, "-m", "wittgenstein.cli.main", "serve", "--no-open", "--port", str(port)]


def start(port: int | None = None, wait: float = 90.0) -> tuple[bool, str]:
    """Start the server in the background. (started_now, message)."""
    port = port or load_config().get("port") or DEFAULT_PORT
    save_config({"port": port})
    if responding(port):
        return False, f"Already running on {url(port)}"
    log = open(home() / "server.log", "ab")  # noqa: SIM115 -- handed to the child process
    kwargs: dict[str, Any] = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(_serve_argv(port), **kwargs)  # noqa: S603 -- our own interpreter and module
    (home() / "server.json").write_text(json.dumps({"pid": proc.pid, "port": port, "started": time.time()}))
    deadline = time.time() + wait
    while time.time() < deadline:
        if responding(port):
            return True, f"Running on {url(port)}"
        if proc.poll() is not None:
            return False, f"The server exited (code {proc.returncode}); see {home() / 'server.log'}"
        time.sleep(0.5)
    return False, f"Started, but not responding yet; see {home() / 'server.log'}"


def stop() -> str:
    st = _state()
    pid = st.get("pid")
    if pid and _alive(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(40):
            if not _alive(pid):
                break
            time.sleep(0.25)
        (home() / "server.json").unlink(missing_ok=True)
        return "Stopped."
    (home() / "server.json").unlink(missing_ok=True)
    if autostart_enabled():
        _autostart_stop()
        return "Stopped (it starts again at next login; `wittgenstein autostart disable` to prevent that)."
    if responding():
        return f"Something is answering on {url()} that this command didn't start; stop it where it was started."
    return "Not running."


def status() -> dict[str, Any]:
    cfg = load_config()
    up = responding()
    audits = None
    if up:
        try:
            with urllib.request.urlopen(url() + "/v1/audits", timeout=3) as r:
                audits = len(json.loads(r.read())["audits"])
        except OSError:
            pass
    return {
        "running": up,
        "url": url(),
        "pid": _state().get("pid"),
        "autostart": autostart_enabled(),
        "audits": audits,
        "openai_upstream": cfg.get("openai_upstream") or "https://api.openai.com",
        "anthropic_upstream": cfg.get("anthropic_upstream") or "https://api.anthropic.com",
        "home": str(home()),
    }


# --------------------------------------------------------------------------- autostart
def _plist_path() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"


def _systemd_path() -> Path:
    return Path("~/.config/systemd/user/wittgenstein.service").expanduser()


def _startup_path() -> Path:
    return Path(os.environ.get("APPDATA", "~")).expanduser() / (
        "Microsoft/Windows/Start Menu/Programs/Startup/wittgenstein.cmd"
    )


def autostart_enabled() -> bool:
    system = platform.system()
    if system == "Darwin":
        return _plist_path().exists()
    if system == "Linux":
        return _systemd_path().exists()
    if system == "Windows":
        return _startup_path().exists()
    return False


def _plist(port: int) -> str:
    args = "".join(f"\n    <string>{a}</string>" for a in _serve_argv(port))
    log = home() / "server.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>{args}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>WITTGENSTEIN_HOME</key>
    <string>{home()}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
</dict>
</plist>
"""


def autostart_enable(port: int | None = None) -> str:
    port = port or load_config().get("port") or DEFAULT_PORT
    save_config({"port": port})
    system = platform.system()
    if _state().get("pid"):
        stop()  # the login service takes over from a manually started one
    if system == "Darwin":
        p = _plist_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(p)], capture_output=True)  # noqa: S603,S607
        p.write_text(_plist(port))
        r = subprocess.run(["launchctl", "bootstrap", domain, str(p)], capture_output=True, text=True)  # noqa: S603,S607
        if r.returncode != 0:
            return f"Wrote {p}, but launchctl refused it: {r.stderr.strip()}"
        return f"Starts at login (launchd agent {p}). Running on {url(port)}."
    if system == "Linux":
        p = _systemd_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        cmd = " ".join(f'"{a}"' for a in _serve_argv(port))
        p.write_text(
            "[Unit]\nDescription=Wittgenstein review layer for RAG\n\n[Service]\n"
            f"Environment=WITTGENSTEIN_HOME={home()}\nExecStart={cmd}\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n"
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)  # noqa: S603,S607
        r = subprocess.run(
            ["systemctl", "--user", "enable", "--now", "wittgenstein"], capture_output=True, text=True
        )  # noqa: S603,S607
        if r.returncode != 0:
            return f"Wrote {p}, but systemctl refused it: {r.stderr.strip()}"
        return f"Starts at login (systemd user unit {p}). Running on {url(port)}."
    if system == "Windows":
        p = _startup_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        p.write_text(f'@start "" "{exe}" -m wittgenstein.cli.main serve --no-open --port {port}\r\n')
        start(port)
        return f"Starts at login ({p}). Running on {url(port)}."
    return f"Autostart isn't supported on {system}; use `wittgenstein start`."


def _autostart_stop() -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["launchctl", "kill", "TERM", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)  # noqa: S603,S607
    elif system == "Linux":
        subprocess.run(["systemctl", "--user", "stop", "wittgenstein"], capture_output=True)  # noqa: S603,S607


def autostart_disable() -> str:
    system = platform.system()
    if system == "Darwin":
        p = _plist_path()
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(p)], capture_output=True)  # noqa: S603,S607
        p.unlink(missing_ok=True)
        return "Won't start at login; stopped."
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "disable", "--now", "wittgenstein"], capture_output=True)  # noqa: S603,S607
        _systemd_path().unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)  # noqa: S603,S607
        return "Won't start at login; stopped."
    if system == "Windows":
        _startup_path().unlink(missing_ok=True)
        stop()
        return "Won't start at login; stopped."
    return "Nothing to disable."


# --------------------------------------------------------------------------- run
_SITECUSTOMIZE = '''"""Loaded by `wittgenstein run`: hooks LangChain / LlamaIndex for this process, then
hands over to any sitecustomize that was already on the path."""
import importlib.util as _u
import os as _os
import sys as _sys

try:
    import _wittgenstein_monitor as _wm

    _hooked = _wm.instrument()
    if _os.environ.get("WITTGENSTEIN_VERBOSE"):
        print("wittgenstein: hooked", _hooked or "nothing (no LangChain or LlamaIndex found)", file=_sys.stderr)
except Exception as _e:  # never stop the program from starting
    print(f"wittgenstein: couldn't hook this program ({type(_e).__name__}: {_e})", file=_sys.stderr)

_here = _os.path.dirname(_os.path.abspath(__file__))
for _p in list(_sys.path):
    if _os.path.abspath(_p or ".") == _here:
        continue
    _f = _os.path.join(_p or ".", "sitecustomize.py")
    if _os.path.isfile(_f):
        _spec = _u.spec_from_file_location("_sitecustomize_next", _f)
        if _spec and _spec.loader:
            _spec.loader.exec_module(_u.module_from_spec(_spec))
        break
'''


def shim_dir() -> Path:
    """A directory with the hooks as a standalone package and a sitecustomize that loads
    them: on PYTHONPATH, any Python (3.10+) gets the hooks without installing anything."""
    d = home() / "shim"
    pkg = d / "_wittgenstein_monitor"
    if pkg.exists():
        shutil.rmtree(pkg)
    src = Path(__file__).resolve().parent / "monitor"
    shutil.copytree(src, pkg, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "sitecustomize.py").write_text(_SITECUSTOMIZE)
    return d


def run(command: list[str], source: str | None = None) -> int:
    if not responding():
        start()
    env = dict(os.environ)
    d = str(shim_dir())
    env["PYTHONPATH"] = d + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("WITTGENSTEIN_URL", url())
    env.setdefault("WITTGENSTEIN_SOURCE", source or Path(command[-1]).name)
    return subprocess.call(command, env=env)  # noqa: S603 -- the user's own command


__all__ = [
    "apply_config_env",
    "autostart_disable",
    "autostart_enable",
    "autostart_enabled",
    "home",
    "load_config",
    "run",
    "save_config",
    "shim_dir",
    "start",
    "status",
    "stop",
    "url",
]
