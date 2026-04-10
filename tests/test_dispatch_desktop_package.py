from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import zipfile

import pytest


def _load_dispatch_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dispatch_desktop_package.py"
    spec = importlib.util.spec_from_file_location("dispatch_desktop_package", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        ("git@github.com:FrankFacundo/press_review.git", "FrankFacundo/press_review"),
        ("https://github.com/FrankFacundo/press_review.git", "FrankFacundo/press_review"),
        ("ssh://git@github.com/FrankFacundo/press_review.git", "FrankFacundo/press_review"),
    ],
)
def test_parse_repo_slug_supports_common_github_remotes(remote_url: str, expected: str) -> None:
    dispatch = _load_dispatch_module()

    assert dispatch._parse_repo_slug(remote_url) == expected


def test_parse_repo_slug_rejects_non_github_hosts() -> None:
    dispatch = _load_dispatch_module()

    with pytest.raises(ValueError, match="Unsupported Git remote host"):
        dispatch._parse_repo_slug("https://example.com/FrankFacundo/press_review.git")


def test_download_artifact_zip_uses_binary_response_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch = _load_dispatch_module()

    class _Response:
        def __init__(self) -> None:
            self.headers = {"Content-Disposition": 'attachment; filename="LuxNews-windows.zip"'}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"zip-bytes"

    def _fake_urlopen(request):
        assert request.full_url == "https://api.github.com/artifacts/123/zip"
        assert request.headers["Authorization"] == "Bearer test-token"
        return _Response()

    monkeypatch.setattr(dispatch.urllib.request, "urlopen", _fake_urlopen)

    payload, filename = dispatch._download_artifact_zip(
        url="https://api.github.com/artifacts/123/zip",
        token="test-token",
    )

    assert payload == b"zip-bytes"
    assert filename == "LuxNews-windows.zip"


def test_extract_zip_archive_replaces_previous_contents(tmp_path: Path) -> None:
    dispatch = _load_dispatch_module()
    zip_path = tmp_path / "artifact.zip"
    extract_dir = tmp_path / "downloads"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("LuxNews.exe", "binary")
    zip_path.write_bytes(buffer.getvalue())

    target_dir = extract_dir / "artifact"
    target_dir.mkdir(parents=True)
    stale_file = target_dir / "stale.txt"
    stale_file.write_text("old")

    extracted_dir = dispatch._extract_zip_archive(zip_path, extract_dir)

    assert extracted_dir == target_dir
    assert not stale_file.exists()
    assert (target_dir / "LuxNews.exe").read_text() == "binary"
