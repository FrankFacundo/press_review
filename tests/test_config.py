from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

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


def test_run_config_deduplicates_lessentiel_alias() -> None:
    cfg = config.RunConfig(
        keywords=["k"],
        medias=["lessentiel.lu", "lessentiel.lu/fr", "rtl.lu", "lessentiel.lu/fr"],
    )

    assert cfg.medias == ["lessentiel.lu", "rtl.lu"]


def test_default_job_uses_canonical_lessentiel_id() -> None:
    job = config.get_default_jobs()["daily_job_1"]

    assert "lessentiel.lu" in job.medias
    assert "lessentiel.lu/fr" not in job.medias


def test_get_playwright_default_cache_dir_uses_platform_subdirectory(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.delattr(config.sys, "frozen", raising=False)
    monkeypatch.setattr(config, "get_source_checkout_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "mac-arm64")

    assert config.get_playwright_default_cache_dir() == tmp_path / "playwright" / "mac-arm64"


def test_get_playwright_cache_dir_falls_back_to_legacy_source_checkout_cache(
    monkeypatch, tmp_path
) -> None:
    legacy_cache = tmp_path / "playwright" / "browsers" / "chromium-1"
    legacy_cache.mkdir(parents=True)

    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.delattr(config.sys, "frozen", raising=False)
    monkeypatch.setattr(config, "get_source_checkout_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "mac-arm64")

    assert config.get_playwright_cache_dir() == tmp_path / "playwright"


def test_get_playwright_cache_dir_prefers_bundled_cache_in_packaged_app(
    monkeypatch, tmp_path
) -> None:
    bundle_root = tmp_path / "bundle"
    bundled_cache = bundle_root / "playwright" / "windows-x64" / "browsers" / "chromium-1"
    bundled_cache.mkdir(parents=True)

    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "windows-x64")

    assert config.get_playwright_cache_dir() == bundle_root / "playwright" / "windows-x64"


def test_get_playwright_cache_dir_prefers_platform_subdirectory_in_packaged_app_data(
    monkeypatch, tmp_path
) -> None:
    cache_dir = (
        tmp_path
        / "Library"
        / "Application Support"
        / "LuxNews"
        / "playwright"
        / "mac-arm64"
        / "browsers"
        / "chromium-1"
    )
    cache_dir.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "mac-arm64")

    assert config.get_playwright_cache_dir() == (
        tmp_path / "Library" / "Application Support" / "LuxNews" / "playwright" / "mac-arm64"
    )


def test_get_playwright_cache_dir_extracts_bundled_archive_for_packaged_app(
    monkeypatch,
    tmp_path,
) -> None:
    bundle_root = tmp_path / "bundle"
    source_cache = tmp_path / "source-cache"
    browser_file = source_cache / "browsers" / "chromium-1" / "chrome"
    browser_file.parent.mkdir(parents=True)
    browser_file.write_text("browser", encoding="utf-8")
    archive_path = bundle_root / "playwright" / "mac-arm64.tar.gz"
    archive_path.parent.mkdir(parents=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source_cache / "browsers", arcname="browsers")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "mac-arm64")

    cache_dir = config.get_playwright_cache_dir()

    expected_cache_dir = (
        tmp_path / "Library" / "Application Support" / "LuxNews" / "playwright" / "mac-arm64"
    )
    assert cache_dir == expected_cache_dir
    assert (expected_cache_dir / "browsers" / "chromium-1" / "chrome").read_text(
        encoding="utf-8"
    ) == "browser"


def test_get_playwright_cache_dir_falls_back_to_app_data_without_bundled_cache(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", raising=False)
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setattr(config, "get_source_checkout_dir", lambda: None)
    monkeypatch.setattr(config, "get_playwright_runtime_platform", lambda: "mac-arm64")

    assert config.get_playwright_cache_dir() == (
        tmp_path / "Library" / "Application Support" / "LuxNews" / "playwright" / "mac-arm64"
    )


def test_get_playwright_cache_dir_honors_env_override(monkeypatch, tmp_path) -> None:
    custom_cache = tmp_path / "pw-cache"
    monkeypatch.setenv("LUXNEWS_PLAYWRIGHT_CACHE_DIR", str(custom_cache))

    assert config.get_playwright_cache_dir() == custom_cache


def test_run_config_validates_driver() -> None:
    with pytest.raises(ValueError, match="driver must be"):
        config.RunConfig(keywords=["k"], medias=["rtl.lu"], driver="firefox")
    with pytest.raises(ValueError, match="driver must be"):
        config.RunConfig(keywords=["k"], medias=["rtl.lu"], driver="chrome")


def test_contacto_credentials_fall_back_to_wort_credentials(monkeypatch) -> None:
    monkeypatch.delenv("CONTACTO_EMAIL", raising=False)
    monkeypatch.delenv("CONTACTO_PASSWORD", raising=False)
    monkeypatch.setenv("WORT_USERNAME", "wort@example.com")
    monkeypatch.setenv("WORT_PASSWORD", "wort-secret")

    cfg = config.RunConfig(keywords=["k"], medias=["contacto.lu"])

    assert cfg.contacto_email == "wort@example.com"
    assert cfg.contacto_password == "wort-secret"


def test_contacto_credentials_override_wort_fallback(monkeypatch) -> None:
    monkeypatch.setenv("CONTACTO_EMAIL", "contacto@example.com")
    monkeypatch.setenv("CONTACTO_PASSWORD", "contacto-secret")
    monkeypatch.setenv("WORT_USERNAME", "wort@example.com")
    monkeypatch.setenv("WORT_PASSWORD", "wort-secret")

    cfg = config.RunConfig(keywords=["k"], medias=["contacto.lu"])

    assert cfg.contacto_email == "contacto@example.com"
    assert cfg.contacto_password == "contacto-secret"
