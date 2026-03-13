from __future__ import annotations

from pathlib import Path

from luxnews import config


def test_default_output_dir_in_source_mode(monkeypatch) -> None:
    monkeypatch.delattr(config.sys, "frozen", raising=False)

    assert config.get_default_output_dir() == Path("outputs")
    assert config.resolve_output_dir("outputs") == Path("outputs")


def test_default_output_dir_in_packaged_macos_app(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)

    expected_root = tmp_path / "Library" / "Application Support" / "LuxNews"
    assert config.get_default_output_dir() == expected_root / "outputs"
    assert config.resolve_output_dir("outputs") == expected_root / "outputs"
    assert config.resolve_output_dir("custom/subdir") == expected_root / "custom" / "subdir"


def test_run_config_resolves_relative_output_dir_for_packaged_app(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)

    cfg = config.RunConfig(keywords=["k"], medias=["rtl.lu"], output_dir="outputs")

    assert Path(cfg.output_dir) == (
        tmp_path / "Library" / "Application Support" / "LuxNews" / "outputs"
    )
