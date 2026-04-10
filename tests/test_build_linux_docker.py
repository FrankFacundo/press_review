from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path


def _load_build_linux_docker_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_linux_docker.py"
    spec = importlib.util.spec_from_file_location("build_linux_docker", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docker_build_command_uses_expected_defaults(tmp_path: Path) -> None:
    build_linux_docker = _load_build_linux_docker_module()
    args = argparse.Namespace(
        name="LuxNews",
        smoke_test=False,
        no_clean=False,
        image=build_linux_docker.DEFAULT_DOCKER_IMAGE,
        docker_platform=build_linux_docker.DEFAULT_DOCKER_PLATFORM,
        skip_image_build=False,
    )

    command = build_linux_docker._docker_build_command(args, tmp_path)

    assert command[:4] == ["docker", "build", "--platform", "linux/amd64"]
    assert command[-3:] == [
        "-f",
        str(tmp_path / "docker" / "linux-builder.Dockerfile"),
        str(tmp_path),
    ]


def test_docker_run_command_mounts_repo_and_forwards_build_args(monkeypatch, tmp_path: Path) -> None:
    build_linux_docker = _load_build_linux_docker_module()
    monkeypatch.setattr(os, "getuid", lambda: 501)
    monkeypatch.setattr(os, "getgid", lambda: 20)
    args = argparse.Namespace(
        name="LuxNewsTest",
        smoke_test=True,
        no_clean=True,
        image="luxnews-linux-builder:test",
        docker_platform="linux/amd64",
        skip_image_build=False,
    )

    command = build_linux_docker._docker_run_command(args, tmp_path)

    assert command[:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert "501:20" in command
    assert f"{tmp_path}:/workspace" in command
    assert command[-4:] == ["--name", "LuxNewsTest", "--smoke-test", "--no-clean"]
