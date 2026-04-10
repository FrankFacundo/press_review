from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path

import pytest


def _load_build_desktop_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py"
    spec = importlib.util.spec_from_file_location("build_desktop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_command_bundles_target_specific_playwright_cache(monkeypatch, tmp_path: Path) -> None:
    build_desktop = _load_build_desktop_module()
    monkeypatch.setattr(build_desktop.platform, "machine", lambda: "arm64")
    (tmp_path / "playwright" / "mac-arm64" / "browsers" / "chromium-1").mkdir(parents=True)

    args = argparse.Namespace(
        target="mac",
        name="LuxNews",
        no_clean=False,
    )
    command = build_desktop._build_command(args, tmp_path)

    playwright_index = command.index("playwright")
    assert command[playwright_index - 1] == "--collect-all"
    assert "--add-data" in command
    add_data_entries = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--add-data"
    ]
    add_data_value = next(
        value for value in add_data_entries if value.endswith(":playwright-bundles")
    )
    archive_path, target_dir = add_data_value.split(":", 1)
    assert Path(archive_path).exists()
    assert target_dir == "playwright-bundles"


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

    assert f"{tmp_path / 'playwright'};playwright" in command


def test_build_playwright_cache_archive_creates_tarball(tmp_path: Path) -> None:
    build_desktop = _load_build_desktop_module()
    cache_dir = tmp_path / "playwright" / "windows-x64"
    (cache_dir / "browsers" / "chromium-1").mkdir(parents=True)
    (cache_dir / "browsers" / "chromium-1" / "chrome.exe").write_text("", encoding="utf-8")

    archive_path = build_desktop._build_playwright_cache_archive(
        cache_dir,
        tmp_path / "out",
    )

    assert archive_path.exists()
    assert archive_path.suffixes[-2:] == [".tar", ".gz"]


def test_ensure_playwright_installed_rejects_namespace_cache_only(monkeypatch) -> None:
    build_desktop = _load_build_desktop_module()

    class _NamespaceSpec:
        loader = None

    def fake_find_spec(name: str):
        if name == "playwright":
            return _NamespaceSpec()
        if name == "playwright.sync_api":
            return None
        return importlib.util.find_spec(name)

    monkeypatch.setattr(build_desktop.importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(SystemExit, match="cache directory"):
        build_desktop._ensure_playwright_installed()
