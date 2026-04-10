from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

DEFAULT_DOCKER_IMAGE = "luxnews-linux-builder:py313"
DEFAULT_DOCKER_PLATFORM = "linux/amd64"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _dockerfile_path(repo_root: Path) -> Path:
    return repo_root / "docker" / "linux-builder.Dockerfile"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Linux LuxNews desktop package from macOS via Docker."
    )
    parser.add_argument("--name", default="LuxNews", help="Application name for the artifact.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the packaged Linux smoke test inside the container after building.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Reuse existing PyInstaller work directories.",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_DOCKER_IMAGE,
        help="Docker image tag to use for the Linux builder.",
    )
    parser.add_argument(
        "--docker-platform",
        default=DEFAULT_DOCKER_PLATFORM,
        help="Docker platform to emulate for the builder container.",
    )
    parser.add_argument(
        "--skip-image-build",
        action="store_true",
        help="Reuse the existing builder image instead of rebuilding it.",
    )
    return parser.parse_args()


def _docker_build_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    return [
        "docker",
        "build",
        "--platform",
        args.docker_platform,
        "-t",
        args.image,
        "-f",
        str(_dockerfile_path(repo_root)),
        str(repo_root),
    ]


def _inner_build_args(args: argparse.Namespace) -> list[str]:
    build_args = ["--name", args.name]
    if args.smoke_test:
        build_args.append("--smoke-test")
    if args.no_clean:
        build_args.append("--no-clean")
    return build_args


def _docker_run_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        args.docker_platform,
        "-u",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp/luxnews-builder-home",
        "-v",
        f"{repo_root}:/workspace",
        "-w",
        "/workspace",
        args.image,
        "/bin/bash",
        "/workspace/scripts/_build_linux_container.sh",
    ]
    command.extend(_inner_build_args(args))
    return command


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()

    if not args.skip_image_build:
        subprocess.run(_docker_build_command(args, repo_root), check=True, cwd=repo_root)

    subprocess.run(_docker_run_command(args, repo_root), check=True, cwd=repo_root)
    artifact = repo_root / "dist" / "linux" / args.name
    print(f"Linux build complete: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
