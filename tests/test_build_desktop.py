from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


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

    assert "--add-data" in command
    assert f"{tmp_path / 'playwright' / 'mac-arm64'}:playwright/mac-arm64" in command


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
