"""Build frozen team-authored synthetic change-triage splits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from italix.change_triage import COMPACT_PROMPT, LABELS


EXTENSIONS = ["py", "ts", "go", "rb", "yaml", "tf", "tsx", "js", "sql", "rs", "java", "kt", "swift", "ex", "cs", "php"]


def record(prefix: str, index: int, split: str) -> dict:
    domain = prefix.replace("/", "_")
    extension = EXTENSIONS[(index + len(prefix) + len(split)) % len(EXTENSIONS)]
    filename = f"{domain}_{split}_{index}.{extension}"
    identifier = f"{domain.upper()}_{split.upper()}_{index}"
    diff = (
        f"Classify this change using ITALIX policy:\n\n"
        f"diff --git a/{prefix}/{filename} b/{prefix}/{filename}\n"
        f"--- a/{prefix}/{filename}\n+++ b/{prefix}/{filename}\n"
        f"@@ -1 +1 @@\n-{identifier} = false\n+{identifier} = true"
    )
    answer = json.dumps(LABELS[prefix], separators=(",", ":"))
    return {"messages": [
        {"role": "system", "content": COMPACT_PROMPT},
        {"role": "user", "content": diff},
        {"role": "assistant", "content": answer},
    ]}


def build() -> dict[str, list[dict]]:
    return {
        "train": [record(prefix, i, "train") for prefix in LABELS for i in range(10)],
        "valid": [record(prefix, i, "valid") for prefix in LABELS for i in range(2)],
        "holdout": [record(prefix, i, "holdout") for prefix in LABELS for i in range(2)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/change_triage"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    splits = build()
    args.output.mkdir(parents=True, exist_ok=True)
    prompts = set()
    for name, rows in splits.items():
        for row in rows:
            prompt = row["messages"][-2]["content"]
            if prompt in prompts:
                raise SystemExit("duplicate prompt across splits")
            prompts.add(prompt)
            parsed = json.loads(row["messages"][-1]["content"])
            if list(parsed) != ["owner", "risk", "reviewer"]:
                raise SystemExit("invalid output contract")
        payload = "\n".join(json.dumps(row) for row in rows) + "\n"
        path = args.output / f"{name}.jsonl"
        if args.check and path.exists() and path.read_text() != payload:
            raise SystemExit(f"frozen split differs: {path}")
        path.write_text(payload)
        print(f"{name}: {len(rows)}, sha256={hashlib.sha256(payload.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
