from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

DEFAULT_WORKFLOW = "desktop-packages.yml"
DEFAULT_TARGET = "windows"
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_DOWNLOAD_DIR = "downloads/desktop-packages"
GITHUB_API_BASE = "https://api.github.com"


class GitHubArtifact(NamedTuple):
    artifact_id: int
    name: str
    archive_download_url: str
    expired: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _parse_repo_slug(remote_url: str) -> str:
    normalized = (remote_url or "").strip()
    if not normalized:
        raise ValueError("Remote URL is empty.")

    if normalized.startswith("git@github.com:"):
        slug = normalized.split(":", 1)[1]
    elif normalized.startswith("ssh://git@github.com/"):
        slug = normalized.split("ssh://git@github.com/", 1)[1]
    else:
        parsed = urllib.parse.urlparse(normalized)
        if parsed.netloc != "github.com":
            raise ValueError(f"Unsupported Git remote host: {normalized}")
        slug = parsed.path.lstrip("/")

    if slug.endswith(".git"):
        slug = slug[:-4]
    if slug.count("/") != 1:
        raise ValueError(f"Could not parse GitHub owner/repo from remote: {normalized}")
    return slug


def _resolve_repo_slug(explicit_repo: str | None) -> str:
    if explicit_repo:
        return explicit_repo.strip()
    remote_url = _run_git("remote", "get-url", "origin")
    return _parse_repo_slug(remote_url)


def _resolve_ref(explicit_ref: str | None) -> str:
    if explicit_ref:
        return explicit_ref.strip()
    current_branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    if current_branch == "HEAD":
        raise SystemExit("Detached HEAD detected. Pass --ref with a branch or tag name.")
    return current_branch


def _github_request(
    path: str,
    *,
    token: str,
    method: str = "GET",
    payload: dict | None = None,
    accept: str = "application/vnd.github+json",
) -> tuple[dict | list | None, dict[str, str]]:
    data = None
    headers = {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "User-Agent": "luxnews-desktop-builder",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{GITHUB_API_BASE}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request) as response:
            response_headers = dict(response.headers.items())
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"GitHub API request failed ({exc.code}): {details}") from exc

    if not raw_body:
        return None, response_headers
    return json.loads(raw_body.decode("utf-8")), response_headers


def _dispatch_workflow(*, repo_slug: str, workflow: str, ref: str, target: str, token: str) -> None:
    _github_request(
        f"/repos/{repo_slug}/actions/workflows/{workflow}/dispatches",
        token=token,
        method="POST",
        payload={
            "ref": ref,
            "inputs": {
                "target": target,
            },
        },
    )


def _list_workflow_runs(*, repo_slug: str, workflow: str, token: str) -> list[dict]:
    payload, _ = _github_request(
        f"/repos/{repo_slug}/actions/workflows/{workflow}/runs?per_page=20",
        token=token,
    )
    if not isinstance(payload, dict):
        return []
    runs = payload.get("workflow_runs")
    if isinstance(runs, list):
        return runs
    return []


def _parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_dispatched_run(
    *,
    repo_slug: str,
    workflow: str,
    ref: str,
    dispatched_after: datetime,
    token: str,
    poll_interval_seconds: float,
) -> dict:
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        for run in _list_workflow_runs(repo_slug=repo_slug, workflow=workflow, token=token):
            if run.get("event") != "workflow_dispatch":
                continue
            if run.get("head_branch") != ref:
                continue
            created_at = _parse_github_datetime(run.get("created_at"))
            if created_at is None or created_at < dispatched_after:
                continue
            return run
        time.sleep(poll_interval_seconds)
    raise RuntimeError("Timed out waiting for the dispatched GitHub Actions run to appear.")


def _wait_for_run_completion(
    *,
    repo_slug: str,
    run_id: int,
    token: str,
    poll_interval_seconds: float,
) -> dict:
    while True:
        payload, _ = _github_request(
            f"/repos/{repo_slug}/actions/runs/{run_id}",
            token=token,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected GitHub API payload while checking run {run_id}.")
        status = payload.get("status")
        conclusion = payload.get("conclusion")
        print(f"Run {run_id}: status={status} conclusion={conclusion or 'pending'}")
        if status == "completed":
            return payload
        time.sleep(poll_interval_seconds)


def _list_artifacts(*, repo_slug: str, run_id: int, token: str) -> list[GitHubArtifact]:
    payload, _ = _github_request(
        f"/repos/{repo_slug}/actions/runs/{run_id}/artifacts",
        token=token,
    )
    if not isinstance(payload, dict):
        return []

    artifacts: list[GitHubArtifact] = []
    for item in payload.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        artifacts.append(
            GitHubArtifact(
                artifact_id=int(item["id"]),
                name=str(item["name"]),
                archive_download_url=str(item["archive_download_url"]),
                expired=bool(item.get("expired", False)),
            )
        )
    return artifacts


def _download_artifact_zip(*, url: str, token: str) -> tuple[bytes, str | None]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "User-Agent": "luxnews-desktop-builder",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request) as response:
            content_disposition = response.headers.get("Content-Disposition")
            filename = None
            if content_disposition:
                for part in content_disposition.split(";"):
                    part = part.strip()
                    if part.startswith("filename="):
                        filename = part.split("=", 1)[1].strip('"')
                        break
            return response.read(), filename
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Artifact download failed ({exc.code}): {details}") from exc


def _write_artifact_zip(
    *,
    artifact: GitHubArtifact,
    output_dir: Path,
    token: str,
) -> Path:
    payload, suggested_filename = _download_artifact_zip(
        url=artifact.archive_download_url,
        token=token,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = suggested_filename or f"{artifact.name}.zip"
    output_path = output_dir / filename
    output_path.write_bytes(payload)
    return output_path


def _extract_zip_archive(zip_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    target_dir = extract_dir / zip_path.stem
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target_dir)
    return target_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger the GitHub desktop packaging workflow from the command line."
    )
    parser.add_argument(
        "--target",
        choices=("windows", "linux", "all"),
        default=DEFAULT_TARGET,
        help="Workflow target input.",
    )
    parser.add_argument(
        "--workflow",
        default=DEFAULT_WORKFLOW,
        help="Workflow file name in .github/workflows/.",
    )
    parser.add_argument(
        "--repo",
        help="GitHub repo in owner/name form. Defaults to origin remote.",
    )
    parser.add_argument(
        "--ref",
        help="Branch or tag to build. Defaults to the current branch.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the workflow run to finish and print the result.",
    )
    parser.add_argument(
        "--download-dir",
        help=(
            "Download workflow artifacts into this directory. "
            f"Defaults to `{DEFAULT_DOWNLOAD_DIR}` when used with --download."
        ),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download the workflow artifacts after a successful run.",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract downloaded artifact zip files after download.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds when --wait is enabled.",
    )
    parser.add_argument(
        "--open-actions-page",
        action="store_true",
        help="Open the workflow page in a browser after dispatching.",
    )
    return parser.parse_args()


def _resolve_download_dir(args: argparse.Namespace) -> Path:
    raw_path = args.download_dir or DEFAULT_DOWNLOAD_DIR
    return (_repo_root() / raw_path).resolve()


def main() -> int:
    args = _parse_args()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set GITHUB_TOKEN with permission to run workflows and read artifacts.")

    repo_slug = _resolve_repo_slug(args.repo)
    ref = _resolve_ref(args.ref)
    workflow_url = f"https://github.com/{repo_slug}/actions/workflows/{args.workflow}"

    print(
        "Dispatching desktop package workflow. "
        "The GitHub runner will build the pushed commit for this ref, not local unpushed changes."
    )
    print(f"Repository: {repo_slug}")
    print(f"Workflow: {args.workflow}")
    print(f"Ref: {ref}")
    print(f"Target: {args.target}")

    dispatched_after = datetime.now(timezone.utc)
    _dispatch_workflow(
        repo_slug=repo_slug,
        workflow=args.workflow,
        ref=ref,
        target=args.target,
        token=token,
    )
    print(f"Workflow dispatched: {workflow_url}")

    if args.open_actions_page:
        webbrowser.open(workflow_url)

    if not (args.wait or args.download or args.extract):
        return 0

    run = _find_dispatched_run(
        repo_slug=repo_slug,
        workflow=args.workflow,
        ref=ref,
        dispatched_after=dispatched_after,
        token=token,
        poll_interval_seconds=args.poll_interval,
    )
    run_id = int(run["id"])
    run_url = str(run.get("html_url") or f"https://github.com/{repo_slug}/actions/runs/{run_id}")
    print(f"Run detected: {run_url}")

    completed_run = _wait_for_run_completion(
        repo_slug=repo_slug,
        run_id=run_id,
        token=token,
        poll_interval_seconds=args.poll_interval,
    )
    conclusion = completed_run.get("conclusion")
    if conclusion != "success":
        raise SystemExit(f"Workflow failed: {run_url}")

    artifacts = _list_artifacts(repo_slug=repo_slug, run_id=run_id, token=token)
    if not artifacts:
        print("Workflow succeeded, but no artifacts were found.")
        return 0

    print("Artifacts:")
    for artifact in artifacts:
        print(f"- {artifact.name}")

    if args.download or args.extract:
        download_dir = _resolve_download_dir(args)
        for artifact in artifacts:
            if artifact.expired:
                print(f"Skipping expired artifact: {artifact.name}")
                continue
            zip_path = _write_artifact_zip(
                artifact=artifact,
                output_dir=download_dir,
                token=token,
            )
            print(f"Downloaded: {zip_path}")
            if args.extract:
                extracted_dir = _extract_zip_archive(zip_path, download_dir)
                print(f"Extracted: {extracted_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
