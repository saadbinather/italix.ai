"""Create a controlled fictional Git repository for the Developer Memory demo."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


COMMITS = [
    (
        "Record PostgreSQL as the billing datastore",
        "docs/decisions/database.md",
        """# Billing database\n\nUse PostgreSQL for transactional invoice and payment updates.\nStore flexible provider payloads in JSONB. MongoDB is not the billing source of truth.\n""",
        "2026-01-11T10:00:00+00:00",
    ),
    (
        "Add Redis plan catalog cache with database fallback",
        "docs/decisions/cache.md",
        """# Pricing cache\n\nCache plan catalog lookups in Redis under pricing:plans:v1 for 60 seconds.\nFall back to PostgreSQL when Redis is unavailable; Redis is not the source of truth.\n""",
        "2026-02-04T10:00:00+00:00",
    ),
    (
        "Document partner API token-bucket limit",
        "docs/decisions/rate-limit.md",
        """# Partner rate limit\n\nUse a per-API-key token bucket at 120 requests per minute.\nReturn HTTP 429 and Retry-After, and fail open if the limiter store is unavailable.\n""",
        "2026-02-19T10:00:00+00:00",
    ),
    (
        "Redact sensitive fields before log serialization",
        "docs/decisions/logging.md",
        """# Logging privacy\n\nOmit session_id, access_token, and email before serialization.\nRetain request_id for incident investigation.\n""",
        "2026-03-08T10:00:00+00:00",
    ),
]


def git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path("var/demo/memory-repo"))
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")
    destination.mkdir(parents=True)
    git(destination, "init", "-q")
    git(destination, "config", "user.name", "ITALIX Demo Team")
    git(destination, "config", "user.email", "demo@italix.local")
    for message, relative, content, timestamp in COMMITS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        git(destination, "add", relative)
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
            "GIT_AUTHOR_NAME": "ITALIX Demo Team",
            "GIT_AUTHOR_EMAIL": "demo@italix.local",
            "GIT_COMMITTER_NAME": "ITALIX Demo Team",
            "GIT_COMMITTER_EMAIL": "demo@italix.local",
        }
        git(destination, "commit", "-q", "-m", message, env=env)
    print(f"Created fictional Git repository with {len(COMMITS)} commits: {destination}")
    print("Discussion demo: data/demo_discussions.jsonl (synthetic)")


if __name__ == "__main__":
    main()
