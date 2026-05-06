from __future__ import annotations

import argparse
import importlib.util
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace


def _load_build_desktop_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py"
    spec = importlib.util.spec_from_file_location("build_desktop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_command_bundles_target_specific_playwright_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_desktop = _load_build_desktop_module()
    monkeypatch.setattr(build_desktop.platform, "machine", lambda: "arm64")
    (tmp_path / "playwright" / "mac-arm64" / "browsers" / "chromium-1").mkdir(parents=True)

    args = argparse.Namespace(
        target="mac",
        name="LuxNews",
        no_clean=False,
    )
    command = build_desktop._build_command(args, tmp_path)
    archive_path = (
        tmp_path / "build" / "pyinstaller" / "mac" / "playwright-cache" / "mac-arm64.tar.gz"
    )

    assert "--add-data" in command
    assert f"{archive_path}:playwright" in command
    assert archive_path.exists()
    with tarfile.open(archive_path, "r:gz") as archive:
        assert "browsers/chromium-1" in archive.getnames()


def test_build_command_falls_back_to_legacy_playwright_cache(monkeypatch, tmp_path: Path) -> None:
    build_desktop = _load_build_desktop_module()
    (tmp_path / "playwright").mkdir(parents=True)
    (tmp_path / "playwright" / "browsers" / "chromium-1").mkdir(parents=True)
    monkeypatch.setattr(build_desktop.platform, "machine", lambda: "AMD64")

    args = argparse.Namespace(
        target="windows",
        name="LuxNews",
        no_clean=False,
    )
    command = build_desktop._build_command(args, tmp_path)
    archive_path = (
        tmp_path / "build" / "pyinstaller" / "windows" / "playwright-cache" / "windows-x64.tar.gz"
    )

    assert f"{archive_path};playwright" in command
    assert archive_path.exists()


def test_ensure_playwright_cache_ready_uses_target_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_desktop = _load_build_desktop_module()
    monkeypatch.setattr(build_desktop.platform, "machine", lambda: "arm64")
    calls = []

    def fake_ensure_playwright_browser(*, cache_dir):
        calls.append(("ensure", cache_dir))
        return cache_dir / "browsers" / "chromium"

    monkeypatch.setitem(
        sys.modules,
        "luxnews.playwright_utils",
        SimpleNamespace(
            ensure_playwright_browser=fake_ensure_playwright_browser,
            install_playwright_browser=lambda *, cache_dir: calls.append(("install", cache_dir)),
        ),
    )

    cache_dir = build_desktop._ensure_playwright_cache_ready(tmp_path, "mac", force=False)

    assert cache_dir == tmp_path / "playwright" / "mac-arm64"
    assert calls == [("ensure", cache_dir)]


def test_require_playwright_cache_bundle_fails_without_cache(tmp_path: Path) -> None:
    build_desktop = _load_build_desktop_module()

    try:
        build_desktop._require_playwright_cache_bundle(tmp_path, "linux")
    except SystemExit as exc:
        assert "No bundled Playwright browser cache" in str(exc)
    else:
        raise AssertionError("Expected SystemExit")
