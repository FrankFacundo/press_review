from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TARGETS = ("mac", "linux", "windows")
HOST_TARGETS = {
    "Darwin": "mac",
    "Linux": "linux",
    "Windows": "windows",
}
EXCLUDED_MODULES = (
    "boto3",
    "botocore",
    "marimo",
    "onnxruntime",
    "pytest",
    "scipy",
    "sklearn",
    "streamlit.external",
    "streamlit.hello",
    "streamlit.testing",
    "sympy",
    "tensorflow",
    "tensorboard",
    "torch",
    "transformers",
)


def _has_playwright_browser_cache(cache_dir: Path) -> bool:
    browsers_dir = cache_dir / "browsers"
    if not browsers_dir.is_dir():
        return False
    try:
        return any(browsers_dir.iterdir())
    except OSError:
        return False


def _playwright_cache_platform_for_target(target: str) -> str:
    machine = platform.machine().lower()
    if target == "mac":
        if machine in {"arm64", "aarch64"}:
            return "mac-arm64"
        return "mac-x64"
    if target == "windows":
        return "windows-x64"
    if machine in {"arm64", "aarch64"}:
        return "linux-arm64"
    return "linux-x64"


def _playwright_cache_archive_stem(cache_dir: Path) -> str:
    browsers_dir = cache_dir / "browsers"
    browser_entries: list[str] = []
    if browsers_dir.is_dir():
        browser_entries = sorted(
            entry.name.replace(".", "-")
            for entry in browsers_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
    suffix = "-".join(browser_entries) if browser_entries else "browser-cache"
    return f"{cache_dir.name}-{suffix}"


def _build_playwright_cache_archive(cache_dir: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_base = output_dir / _playwright_cache_archive_stem(cache_dir)
    archive_path = archive_base.with_suffix(".tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    generated_archive = Path(
        shutil.make_archive(
            str(archive_base),
            "gztar",
            root_dir=cache_dir,
        )
    )
    if generated_archive != archive_path:
        if archive_path.exists():
            archive_path.unlink()
        generated_archive.rename(archive_path)
    return archive_path


def _host_target() -> str:
    system = platform.system()
    try:
        return HOST_TARGETS[system]
    except KeyError as exc:
        raise SystemExit(f"Unsupported host platform: {system}") from exc


def _pick_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the LuxNews desktop package.")
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default=_host_target(),
        help="Platform to build on this machine.",
    )
    parser.add_argument(
        "--name",
        default="LuxNews",
        help="Application name used for the generated artifact.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the built artifact locally and wait for Streamlit healthcheck.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Reuse existing PyInstaller work directories.",
    )
    return parser.parse_args()


def _ensure_pyinstaller_installed() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    raise SystemExit(
        "PyInstaller is not installed. Run `python3 -m pip install -e .[packaging]` "
        "or `python3 -m pip install pyinstaller` first."
    )


def _ensure_playwright_installed() -> None:
    playwright_spec = importlib.util.find_spec("playwright")
    sync_api_spec = importlib.util.find_spec("playwright.sync_api")
    if sync_api_spec is not None:
        return
    if playwright_spec is not None and playwright_spec.loader is None:
        raise SystemExit(
            "This Python interpreter only sees the repo's `playwright/` cache directory, "
            "not the Playwright package. Activate the project virtualenv or run "
            "`python3 -m pip install -e .[packaging]` in the interpreter you will use "
            "for the build."
        )
    raise SystemExit(
        "Playwright is not installed in this Python environment. Run "
        "`python3 -m pip install -e .[packaging]` first."
    )


def _build_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    target = args.target
    work_root = repo_root / "build" / "pyinstaller" / target
    dist_dir = repo_root / "dist" / target
    data_separator = ";" if target == "windows" else ":"
    entry_script = repo_root / "run_streamlit.py"
    streamlit_app = repo_root / "src" / "luxnews" / "streamlit_app.py"
    icon_dir = repo_root / "assets" / "icons"
    playwright_cache_root = repo_root / "playwright"
    playwright_cache_dir = playwright_cache_root / _playwright_cache_platform_for_target(target)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        args.name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_root / "work"),
        "--specpath",
        str(work_root / "spec"),
        "--paths",
        str(repo_root / "src"),
        "--collect-all",
        "playwright",
        "--collect-all",
        "streamlit",
        "--collect-submodules",
        "luxnews",
        "--add-data",
        f"{streamlit_app}{data_separator}luxnews",
    ]
    if _has_playwright_browser_cache(playwright_cache_dir):
        playwright_archive = _build_playwright_cache_archive(
            playwright_cache_dir,
            work_root / "resources" / "playwright",
        )
        command.extend(
            [
                "--add-data",
                f"{playwright_archive}{data_separator}playwright-bundles",
            ]
        )
    elif _has_playwright_browser_cache(playwright_cache_root):
        command.extend(
            [
                "--add-data",
                f"{playwright_cache_root}{data_separator}playwright",
            ]
        )
    for module_name in EXCLUDED_MODULES:
        command.extend(["--exclude-module", module_name])
    if not args.no_clean:
        command.append("--clean")

    if target == "mac":
        icns_path = icon_dir / "luxnews.icns"
        if icns_path.exists():
            command.extend(["--icon", str(icns_path)])
        command.extend(
            [
                "--windowed",
                "--osx-bundle-identifier",
                "lu.luxnews.desktop",
            ]
        )
    elif target == "windows":
        ico_path = icon_dir / "luxnews.ico"
        if ico_path.exists():
            command.extend(["--icon", str(ico_path)])
        command.extend(["--onefile", "--windowed"])
    else:
        command.append("--onefile")

    command.append(str(entry_script))
    return command


def _artifact_path(target: str, repo_root: Path, name: str) -> Path:
    dist_dir = repo_root / "dist" / target
    if target == "mac":
        return dist_dir / f"{name}.app"
    if target == "windows":
        return dist_dir / f"{name}.exe"
    return dist_dir / name


def _artifact_executable(target: str, artifact_path: Path, name: str) -> Path:
    if target == "mac":
        return artifact_path / "Contents" / "MacOS" / name
    return artifact_path


def _wait_for_streamlit(port: int, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2.0) as response:
                body = response.read().decode("utf-8", errors="replace").strip().lower()
                if response.status == 200 and "ok" in body:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1.0)
            continue
    raise TimeoutError(f"Timed out waiting for Streamlit healthcheck at {health_url}.")


def _run_packaged_self_test(executable: Path, repo_root: Path) -> None:
    env = os.environ.copy()
    env["LUXNEWS_DESKTOP_SELFTEST"] = "browser_imports"
    env["LUXNEWS_BROWSER_AUTO_OPEN"] = "0"
    try:
        subprocess.run(
            [str(executable)],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or "").strip() or (exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"Packaged self-test failed: {details}") from exc


def _smoke_test(target: str, artifact: Path, repo_root: Path, name: str) -> None:
    executable = _artifact_executable(target, artifact, name)
    if not executable.exists():
        raise FileNotFoundError(f"Built executable not found: {executable}")

    _run_packaged_self_test(executable, repo_root)

    port = _pick_free_port()
    env = os.environ.copy()
    env["LUXNEWS_STREAMLIT_PORT"] = str(port)
    env["LUXNEWS_BROWSER_AUTO_OPEN"] = "0"
    process = subprocess.Popen(
        [str(executable)],
        cwd=repo_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_streamlit(port, timeout_seconds=45.0)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10.0)


def _build_environment(repo_root: Path, target: str) -> dict[str, str]:
    build_root = repo_root / "build" / "pyinstaller" / target
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(build_root / "cache")
    env["MPLCONFIGDIR"] = str(build_root / "mplconfig")
    return env


def main() -> int:
    args = _parse_args()
    host_target = _host_target()
    if args.target != host_target:
        if host_target == "mac" and args.target == "linux":
            raise SystemExit(
                "Cannot build `linux` natively on `mac` with PyInstaller. "
                "Use `scripts/build_linux_bin.sh` for the Docker-based Linux cross-build."
            )
        if host_target == "mac" and args.target == "windows":
            raise SystemExit(
                "Cannot build `windows` natively on `mac` with PyInstaller. "
                "On Apple Silicon, tested Wine-based Docker builders abort under amd64 emulation, "
                "so use the GitHub Actions `Desktop Packages` workflow or a native Windows host."
            )
        raise SystemExit(
            f"Cannot build `{args.target}` on `{host_target}` with PyInstaller. "
            "Build Windows artifacts on Windows, Linux artifacts on Linux, and macOS artifacts on macOS."
        )

    _ensure_pyinstaller_installed()
    _ensure_playwright_installed()

    repo_root = Path(__file__).resolve().parents[1]
    command = _build_command(args, repo_root)
    env = _build_environment(repo_root, args.target)
    print(f"Building LuxNews for {args.target}...")
    subprocess.run(command, cwd=repo_root, check=True, env=env)

    artifact = _artifact_path(args.target, repo_root, args.name)
    print(f"Build complete: {artifact}")

    if args.smoke_test:
        print("Running smoke test...")
        _smoke_test(args.target, artifact, repo_root, args.name)
        print("Smoke test passed.")

    if host_target == "mac" and args.target == "mac":
        print(
            "To test a Windows .exe from macOS, build it on Windows first and then run it "
            "through Wine/CrossOver or a Windows VM such as UTM/Parallels."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
