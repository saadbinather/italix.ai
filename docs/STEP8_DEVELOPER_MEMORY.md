# Step 8: local developer memory

Developer Memory is a small secondary feature beside ITALIX's core specialist
training platform. It stores explicitly imported engineering history and uses
SQLite FTS5 plus the frozen local Qwen base model to answer source-grounded
questions. Memory records never enter `training_queue`.

## Data flow

```text
selected Git metadata + approved discussion export
  -> memory_sources + memory_sources_fts
  -> deterministic keyword retrieval
  -> frozen local Qwen
  -> cited answer or abstention
```

Git import records the repository identity, commit SHA, author, timestamp,
message, changed paths, and optionally `--shortstat`. It does not read file
contents, execute repository code, run hooks, modify the repository, or push.
Imports are keyed by repository and SHA, so retries are idempotent.

Discussion imports accept only an explicitly supplied `.json` or `.jsonl` file
up to 2 MiB. Required fields are `message_id`, `channel`, `timestamp`, `author`,
and `text`; `thread_id` and `permalink` are optional. Only valid HTTP(S)
permalinks are exposed as links.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/memory/import/git` | Import selected local commit metadata |
| POST | `/v1/memory/import/discussions` | Import an approved JSON/JSONL export |
| GET | `/v1/memory/search?q=...` | Return ranked FTS5 evidence |
| POST | `/v1/memory/query` | Retrieve and answer with local base Qwen |
| GET | `/v1/memory/sources/{id}` | Inspect one exact source record |

`POST /v1/memory/query` does not expose a cloud option. If retrieval returns no
evidence, it abstains before loading or calling the model. Generated citation
labels are accepted only when they exactly match retrieved records; invalid
labels are removed. When Qwen emits no labels, the API appends the complete
retrieved source set rather than inventing references.

## Controlled fictional demo

Create the fictional repository once:

```bash
source .venv/bin/activate
python scripts/create_memory_demo.py
```

The repository is created under `var/demo/memory-repo`, and the eight synthetic
discussion messages are in `data/demo_discussions.jsonl`. Both cover database
selection, Redis caching, API rate limits, and logging privacy.

In the dashboard's **Developer Memory** tab:

1. Import `<repository>/var/demo/memory-repo`.
2. Approve and import `<repository>/data/demo_discussions.jsonl`.
3. Ask `Why did we introduce Redis caching?`.
4. Inspect the retrieved commit SHA and discussion message IDs.
5. Ask `Why did we choose Apache Kafka for lunar telemetry?` to demonstrate
   evidence-based abstention.

The verified Redis answer cited the Redis decision commit and discussion
records. The Kafka question returned no sources and did not invoke Qwen.

## Scope and limitations

- FTS5 is lexical retrieval, not semantic vector search. Use concrete system,
  component, or decision terms.
- Commit metadata and messages may still be sensitive; import only approved
  repositories and commits.
- The local MVP has no authentication or per-user memory permissions.
- Diff contents, pull requests, real Slack OAuth, and knowledge graphs are out
  of scope.
