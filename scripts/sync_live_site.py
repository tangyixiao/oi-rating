#!/usr/bin/env python3
"""Mirror the published OI rating site into this repository.

``https://sxyz-elo-rating.pages.dev`` is where the application actually runs.
Its shell files and shared dataset are copied here so one revision carries both
the page and the data: GitHub Pages publishes the same page, and every dataset
change becomes a reviewable commit before it reaches a published site.

The dataset is written twice on purpose. ``data.json`` is the readable copy that
humans and tests open; ``api/data`` is the path the mirrored page fetches at
runtime. Both always hold the same bytes.

Only the Python standard library is used, so the scheduled job installs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SOURCE = "https://sxyz-elo-rating.pages.dev"
USER_AGENT = "oi-rating-sync/1.0 (+https://github.com/tangyixiao/oi-rating)"
TIMEOUT_SECONDS = 30
ATTEMPTS = 3

TEXT_FILES = ("index.html", "sw.js", "manifest.webmanifest")
BINARY_FILES = ("icon-192.png", "icon-512.png")
DATASET_PATHS = (Path("data.json"), Path("api") / "data")
DATASET_ENDPOINT = "api/data"

# Markers the served page must still contain before it may replace our copy.
# A Cloudflare Pages project answers unknown paths with its entry page, so a
# mistyped URL or a broken deployment would otherwise be mirrored happily.
SHELL_MARKERS = ('data-tab="rating"', DATASET_ENDPOINT, "oi-rating-system-v")


def fetch(url: str) -> bytes:
    """Return the body of *url*, retrying transient network failures."""
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise OSError(f"HTTP {response.status}")
                return response.read()
        except (urllib.error.URLError, OSError) as error:
            last_error = error
            if attempt < ATTEMPTS:
                continue
    raise SystemExit(f"error: cannot read {url}: {last_error}")


def validate_shell(markup: str) -> None:
    """Refuse to overwrite the page with something that is not our application."""
    missing = [marker for marker in SHELL_MARKERS if marker not in markup]
    if missing:
        raise SystemExit(
            f"error: the served page is missing {missing}; "
            "refusing to replace this repository's index.html"
        )


def validate_dataset(data: object) -> tuple[int, int, int, list[str]]:
    """Check the shape of the published dataset; return counts and warnings."""
    if not isinstance(data, dict):
        raise SystemExit("error: the dataset is not a JSON object")
    users = data.get("users")
    contests = data.get("contests")
    if not isinstance(users, list) or not users:
        raise SystemExit("error: the dataset has no users")
    if not isinstance(contests, list) or not contests:
        raise SystemExit("error: the dataset has no contests")

    user_ids = [entry.get("id") for entry in users if isinstance(entry, dict)]
    if len(user_ids) != len(users):
        raise SystemExit("error: the dataset has a user entry that is not an object")
    if len(set(user_ids)) != len(user_ids):
        raise SystemExit("error: the dataset repeats a user id")

    contest_ids = [entry.get("id") for entry in contests if isinstance(entry, dict)]
    if len(contest_ids) != len(contests):
        raise SystemExit("error: the dataset has a contest entry that is not an object")
    if len(set(contest_ids)) != len(contest_ids):
        raise SystemExit("error: the dataset repeats a contest id")

    known = set(user_ids)
    referenced = {
        result.get("userId")
        for contest in contests
        for result in contest.get("results", [])
        if isinstance(result, dict)
    }
    warnings = []
    unknown = sorted(referenced - known, key=str)
    if unknown:
        # A removed participant leaves historical results behind. Mirror the
        # data as published and record the gap instead of failing the sync.
        warnings.append(f"{len(unknown)} historical result(s) reference missing user ids: {unknown[:5]}")

    version = data.get("version")
    if not isinstance(version, int):
        raise SystemExit("error: the dataset has no integer version")
    return len(users), len(contests), version, warnings


def encode_dataset(data: object) -> bytes:
    """Serialise the dataset the same way every run, so diffs stay readable."""
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def collect(source: str) -> tuple[list[tuple[Path, bytes]], dict]:
    """Download everything this repository mirrors and describe the dataset."""
    payloads: list[tuple[Path, bytes]] = []

    for name in TEXT_FILES:
        body = fetch(f"{source}/{name}")
        try:
            markup = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"error: {name} is not UTF-8: {error}")
        if name == "index.html":
            validate_shell(markup)
        payloads.append((Path(name), body))

    for name in BINARY_FILES:
        payloads.append((Path(name), fetch(f"{source}/{name}")))

    raw = fetch(f"{source}/{DATASET_ENDPOINT}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"error: the dataset is not valid UTF-8 JSON: {error}")

    users, contests, version, warnings = validate_dataset(data)
    encoded = encode_dataset(data)
    for relative in DATASET_PATHS:
        payloads.append((relative, encoded))

    dataset = {
        "users": users,
        "contests": contests,
        "version": version,
        "endpoint": f"{source}/{DATASET_ENDPOINT}",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "warnings": warnings,
    }
    return payloads, dataset


def sync(root: Path, source: str, write: bool) -> dict:
    """Compare the published files with this checkout and optionally write them."""
    payloads, dataset = collect(source)

    files = []
    for relative, body in payloads:
        target = root / relative
        current = target.read_bytes() if target.exists() else None
        if current == body:
            status = "unchanged"
        elif current is None:
            status = "added"
        else:
            status = "updated"
        files.append({"path": relative.as_posix(), "status": status, "bytes": len(body)})
        if write and status != "unchanged":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)

    changed = [entry["path"] for entry in files if entry["status"] != "unchanged"]
    return {
        "source": source,
        "dataset": dataset,
        "files": files,
        "changed": changed,
        "written": bool(write),
    }


def render_step_summary(summary: dict) -> str:
    """Describe this run for the workflow's job summary page."""
    dataset = summary["dataset"]
    lines = [
        "### Mirrored dataset",
        "",
        f"- Users: {dataset['users']}",
        f"- Contests: {dataset['contests']}",
        f"- Schema version: {dataset['version']}",
        f"- Digest: `sha256:{dataset['sha256']}`",
        "",
    ]
    changed = [entry for entry in summary["files"] if entry["status"] != "unchanged"]
    if changed:
        lines.append("Changed files:")
        lines.append("")
        lines.extend(
            f"- `{entry['path']}` - {entry['status']} ({entry['bytes']:,} bytes)" for entry in changed
        )
    else:
        lines.append("The checkout already matches the deployment; nothing to commit.")
    if dataset["warnings"]:
        lines.extend(["", "Warnings:", ""])
        lines.extend(f"- {item}" for item in dataset["warnings"])
    return "\n".join(lines).rstrip("\n") + "\n"


def render_pr_body(summary: dict) -> str:
    """Describe a sync run in the shape this repository already uses in PRs."""
    dataset = summary["dataset"]
    files = "\n".join(
        f"- `{entry['path']}` — {entry['status']} ({entry['bytes']:,} bytes)"
        for entry in summary["files"]
        if entry["status"] != "unchanged"
    ) or "- none"
    warnings = "\n".join(f"- {item}" for item in dataset["warnings"]) or "- none"

    return f"""## Problem

The application is deployed at <{summary['source']}>, and its dataset moves on
without this repository noticing. The published page and the copy kept here
drift apart, so the data users see cannot be reviewed in Git and GitHub Pages
serves an older application.

## Approach

`scripts/sync_live_site.py` downloads the deployed shell files and the shared
dataset, checks that the page is still this application and that the dataset is
structurally sound, then writes them into the checkout. The page is fetched from
`{dataset['endpoint']}`. The dataset is stored at `data.json` for reading and at
`api/data` for the mirrored page to load at runtime.

A scheduled workflow runs the script, and when the result differs from the
default branch it commits the change, opens this pull request and merges it.
Only the workflow's own token is used; no pull request content executes with
write access.

## Scope

Files touched by this run:

{files}

## Validation

- Source reachable: `{summary['source']}` returned the application shell and dataset.
- Dataset: {dataset['users']} users, {dataset['contests']} contests, schema version {dataset['version']}.
- Dataset digest: `sha256:{dataset['sha256']}`.
- Local checks: `python3 scripts/sync_live_site.py --check` compares the checkout with the same source.
- CI: not applicable — this branch is produced by the sync workflow itself.
- Deployment: GitHub Pages rebuilds from `main` after this pull request merges; the deployed result was not checked by this job.
- GitHub settings or other platform state: not applicable.
- Actual runtime or user flow: not checked by this job.

Dataset warnings:

{warnings}

## Resources and retained work

The workflow job downloads the published files to a temporary runner directory
and keeps nothing else. No long-lived background process or local cache is left
behind.

## Review notes

Generated by `.github/workflows/sync-live-site.yml`; do not edit by hand. The
mirrored page carries the site's existing client-side admin passphrase verbatim.
That passphrase was already public in the deployed page, and changing it here
would break the deployed application, so this sync copies it unchanged.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="base URL of the deployed site")
    parser.add_argument("--root", default=None, help="checkout to update (default: repository root)")
    parser.add_argument("--check", action="store_true", help="report differences without writing")
    parser.add_argument("--summary", default=None, help="write the run summary as JSON here")
    parser.add_argument("--step-summary", default=None, help="append a job summary in Markdown here")
    parser.add_argument("--pr-body", default=None, help="write a pull request description here")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    if not (root / "index.html").exists() and not args.check:
        print(f"error: {root} does not look like the repository root", file=sys.stderr)
        return 2

    summary = sync(root, args.source.rstrip("/"), write=not args.check)

    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.step_summary:
        with open(args.step_summary, "a", encoding="utf-8") as handle:
            handle.write(render_step_summary(summary))
    if args.pr_body:
        body = render_pr_body(summary) if summary["changed"] else ""
        Path(args.pr_body).write_text(body, encoding="utf-8")

    dataset = summary["dataset"]
    print(
        json.dumps(
            {
                "source": summary["source"],
                "users": dataset["users"],
                "contests": dataset["contests"],
                "version": dataset["version"],
                "sha256": dataset["sha256"],
                "changed": summary["changed"],
                "written": summary["written"],
                "warnings": dataset["warnings"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
