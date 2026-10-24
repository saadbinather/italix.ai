"""Local, provenance-preserving developer memory using SQLite FTS5."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlparse

from italix.database import Database, utc_now


MAX_DISCUSSION_FILE_BYTES = 2 * 1024 * 1024
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")
CITATION_PATTERN = re.compile(r"\[(?:GIT|DISCUSSION):[^\]]+\]")

MEMORY_SYSTEM_PROMPT = """You answer questions about engineering decisions using only the supplied evidence.
Keep the answer under 140 words. Cite claims with the exact evidence labels, such as [GIT:abc1234]
or [DISCUSSION:msg-1]. Distinguish recorded facts from reasonable inference. If the evidence does not
establish the reason, say so. Never create a source label or claim that is absent from the evidence."""


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _safe_reference(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname.endswith(".invalid"):
        return None
    return value


class MemoryService:
    def __init__(self, database: Database, local_engine):
        self.database = database
        self.local_engine = local_engine

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or "git command failed")
        return result.stdout

    def _insert(self, record: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM memory_sources WHERE source_key=?", (record["source_key"],)
            ).fetchone()
            if existing:
                return False
            connection.execute(
                """INSERT INTO memory_sources
                (id, source_key, kind, repository, title, timestamp, author, content,
                 reference, metadata_json, imported_at)
                VALUES (:id, :source_key, :kind, :repository, :title, :timestamp, :author,
                        :content, :reference, :metadata_json, :imported_at)""",
                record,
            )
            connection.execute(
                "INSERT INTO memory_sources_fts(source_id, title, content) VALUES (?, ?, ?)",
                (record["id"], record["title"], record["content"]),
            )
        return True

    def import_git(
        self,
        repository_path: str,
        commits: list[str] | None = None,
        max_commits: int = 50,
        include_diff_summary: bool = False,
    ) -> dict[str, Any]:
        repo = Path(repository_path).expanduser().resolve(strict=True)
        if not repo.is_dir() or not (repo / ".git").exists():
            raise ValueError("selected path must be the root of a local Git repository")
        root = Path(self._git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
        if root != repo:
            raise ValueError("select the repository root, not a parent or nested directory")
        try:
            remote = self._git(repo, "config", "--get", "remote.origin.url").strip()
        except ValueError:
            remote = ""
        repository = remote or repo.name
        if commits:
            if len(commits) > max_commits or any(not SHA_PATTERN.fullmatch(item) for item in commits):
                raise ValueError("commit selections must be 7–40 hex characters and within max_commits")
            revisions = commits
        else:
            revisions = self._git(repo, "rev-list", f"--max-count={max_commits}", "HEAD").splitlines()
        imported = duplicates = 0
        source_ids = []
        for revision in revisions:
            raw = self._git(
                repo,
                "show",
                "-s",
                "--format=%H%x00%aI%x00%an%x00%s%x00%b",
                revision,
            ).rstrip("\n")
            parts = raw.split("\x00", 4)
            if len(parts) != 5:
                raise ValueError(f"could not parse commit metadata for {revision}")
            sha, timestamp, author, subject, body = parts
            files = [
                line
                for line in self._git(
                    repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha
                ).splitlines()
                if line
            ][:100]
            stat = ""
            if include_diff_summary:
                stat = self._git(repo, "show", "--format=", "--shortstat", "--no-renames", sha).strip()
            content_parts = [subject, body.strip(), "Changed files: " + ", ".join(files)]
            if stat:
                content_parts.append("Diff summary: " + stat)
            label = sha[:12]
            reference = None
            if remote.startswith("https://"):
                reference = remote.removesuffix(".git") + f"/commit/{sha}"
            source_key = f"git:{repository}:{sha}"
            record = {
                "id": _stable_id("mem", source_key),
                "source_key": source_key,
                "kind": "git",
                "repository": repository,
                "title": subject,
                "timestamp": timestamp,
                "author": author,
                "content": "\n".join(part for part in content_parts if part),
                "reference": reference,
                "metadata_json": json.dumps({"sha": sha, "files": files, "citation": f"[GIT:{label}]"}),
                "imported_at": utc_now(),
            }
            if self._insert(record):
                imported += 1
                source_ids.append(record["id"])
            else:
                duplicates += 1
        return {
            "repository": repository,
            "selected_path": str(repo),
            "imported": imported,
            "duplicates": duplicates,
            "source_ids": source_ids,
            "code_executed": False,
        }

    def import_discussions(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            raise ValueError("select a local .json or .jsonl discussion export")
        if path.stat().st_size > MAX_DISCUSSION_FILE_BYTES:
            raise ValueError("discussion import is limited to 2 MiB")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            payload = json.loads(text)
            rows = payload if isinstance(payload, list) else payload.get("messages", [])
        required = {"message_id", "channel", "timestamp", "author", "text"}
        imported = duplicates = 0
        source_ids = []
        for row in rows:
            missing = required - row.keys()
            if missing:
                raise ValueError(f"discussion record missing: {', '.join(sorted(missing))}")
            datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
            source_key = f"discussion:{row['channel']}:{row['message_id']}"
            citation = f"[DISCUSSION:{row['message_id']}]"
            record = {
                "id": _stable_id("mem", source_key),
                "source_key": source_key,
                "kind": "discussion",
                "repository": None,
                "title": f"#{row['channel']} · {row['message_id']}",
                "timestamp": row["timestamp"],
                "author": row["author"],
                "content": row["text"],
                "reference": _safe_reference(row.get("permalink")),
                "metadata_json": json.dumps(
                    {"message_id": row["message_id"], "channel": row["channel"],
                     "thread_id": row.get("thread_id"), "citation": citation,
                     "synthetic": bool(row.get("synthetic", False))}
                ),
                "imported_at": utc_now(),
            }
            if self._insert(record):
                imported += 1
                source_ids.append(record["id"])
            else:
                duplicates += 1
        return {"file": str(path), "imported": imported, "duplicates": duplicates, "source_ids": source_ids}

    def search(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = list(dict.fromkeys(token.lower() for token in TOKEN_PATTERN.findall(question)))
        stop = {"the", "and", "why", "did", "we", "was", "were", "what", "when", "how", "our", "for"}
        tokens = [token for token in tokens if token not in stop][:12]
        if not tokens:
            return []
        query = " OR ".join(f'"{token}"' for token in tokens)
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT s.*, bm25(memory_sources_fts, 4.0, 1.0) AS rank
                FROM memory_sources_fts f JOIN memory_sources s ON s.id=f.source_id
                WHERE memory_sources_fts MATCH ? ORDER BY rank, s.timestamp DESC LIMIT ?""",
                (query, limit),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            item.pop("source_key", None)
            results.append(item)
        return results

    def source(self, source_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM memory_sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        result.pop("source_key", None)
        return result

    def query(self, question: str, limit: int = 5) -> dict[str, Any]:
        evidence = self.search(question, limit)
        if not evidence:
            return {
                "answer": "The imported engineering memory does not contain enough evidence to establish this.",
                "sources": [],
                "model": None,
                "abstained": True,
                "cloud_used": False,
            }
        blocks = []
        allowed = set()
        for item in evidence:
            citation = item["metadata"]["citation"]
            allowed.add(citation)
            blocks.append(f"{citation}\n{item['title']}\n{item['content']}")
        generation = self.local_engine.generate(
            [
                {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Question: {question}\n\nEvidence:\n\n" + "\n\n".join(blocks)},
            ],
            max_tokens=220,
            temperature=0.0,
            adapter_path=None,
        )
        answer = CITATION_PATTERN.sub(
            lambda match: match.group(0) if match.group(0) in allowed else "[unsupported citation removed]",
            generation.text,
        ).strip()
        cited = [item for item in evidence if item["metadata"]["citation"] in answer]
        if not cited:
            cited = evidence
            answer += "\n\nSources: " + ", ".join(item["metadata"]["citation"] for item in cited)
        return {
            "answer": answer,
            "sources": cited,
            "retrieved": evidence,
            "model": generation.model,
            "abstained": False,
            "cloud_used": False,
        }
