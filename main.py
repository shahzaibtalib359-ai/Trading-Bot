from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND_PORT = int(os.getenv("TRADING_BACKEND_PORT", "8012"))
BACKEND_HEALTH_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/healthz"


def is_running_in_project_venv() -> bool:
    return Path(sys.executable).resolve() == VENV_PYTHON.resolve()


def relaunch_with_venv_if_available() -> int | None:
    if VENV_PYTHON.exists() and not is_running_in_project_venv():
        return subprocess.call([str(VENV_PYTHON), str(ROOT / "main.py"), *sys.argv[1:]])
    return None


def require_venv() -> bool:
    if VENV_PYTHON.exists():
        return True
    print("Run setup_windows.bat first")
    return False


def require_modules(modules: list[str], install_hint: str) -> bool:
    missing = [module for module in modules if importlib.util.find_spec(module) is None]
    if not missing:
        return True
    print(f"Missing dependencies: {', '.join(missing)}")
    print(f"Run: {install_hint}")
    return False


def backend_is_running() -> bool:
    try:
        with urllib.request.urlopen(BACKEND_HEALTH_URL, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_backend_for_desktop() -> subprocess.Popen:
    env = os.environ.copy()
    env["TRADING_BACKEND_PORT"] = str(BACKEND_PORT)
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    return subprocess.Popen(
        [str(VENV_PYTHON), str(ROOT / "main.py"), "backend"],
        cwd=str(ROOT),
        env=env,
        creationflags=flags,
    )


def wait_for_backend(timeout_seconds: int = 25) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if backend_is_running():
            return True
        time.sleep(1)
    return False


def run_backend() -> int:
    if not require_venv():
        return 1
    if not require_modules(
        ["fastapi", "uvicorn", "pydantic"],
        r".venv\Scripts\python.exe -m pip install -r requirements.txt",
    ):
        return 1

    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        reload=False,
        app_dir=str(ROOT),
    )
    return 0


def run_desktop() -> int:
    if not require_venv():
        return 1
    if not require_modules(
        ["PyQt6", "requests"],
        r".venv\Scripts\python.exe -m pip install -r desktop\requirements.txt",
    ):
        return 1
    if not backend_is_running():
        print(f"Backend is not running on {BACKEND_HEALTH_URL}. Starting it now...")
        start_backend_for_desktop()
        if not wait_for_backend():
            print("Backend did not become ready in time.")
            print(f"Health check failed: {BACKEND_HEALTH_URL}")
            return 1
        print("Backend is ready.")
    return subprocess.call([sys.executable, str(ROOT / "desktop" / "main.py")])


def main() -> int:
    relaunch_code = relaunch_with_venv_if_available()
    if relaunch_code is not None:
        return relaunch_code

    parser = argparse.ArgumentParser(description="AI Trading Signal Application launcher")
    parser.add_argument(
        "target",
        nargs="?",
        choices=["backend", "desktop"],
        default="backend",
        help="Run backend API server or desktop client. Default: backend",
    )
    args = parser.parse_args()

    if args.target == "desktop":
        return run_desktop()
    return run_backend()


if __name__ == "__main__":
    raise SystemExit(main())
