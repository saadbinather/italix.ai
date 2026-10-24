# Step 5: Orchestra-style core platform

ITALIX implements a small Observe → Evaluate → Improve → Deploy control loop.
It borrows architectural ideas—not source code—from the MIT-licensed Understudy
projects: stable workload identities, metadata-first capture, explicit payload
consent, durable local artifacts, evidence gates, and reversible routes.

## Run

```bash
source .venv/bin/activate
python -m italix.main
```

The server binds to `127.0.0.1:8000`. SQLite state is stored in
`var/italix.db`, which is ignored because opted-in traces may contain sensitive
payloads. Local inference uses only the cached Qwen model.

## Completion request

`POST /v1/chat/completions` accepts the OpenAI chat shape plus four ITALIX
fields:

- `workload`: optional stable workload name; PR diffs are detected as
  `pr_summary` when omitted.
- `capture`: defaults to false. Prompts and responses remain NULL unless true.
- `allow_cloud`: defaults to false and is required for any Gemini/Groq route.
- `model`: `italix-auto` routes through the registry; `gemini` or `groq`
  explicitly requests that provider.

The response includes standard `choices` and `usage` plus an `italix` object
with trace ID, workload, route, selected registry model, reason, and capture
state. Streaming is intentionally outside this MVP.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Local/cloud configuration status without revealing keys |
| POST | `/v1/chat/completions` | OpenAI-compatible inference |
| GET | `/v1/traces/{trace_id}` | Trace metadata and opted-in payloads |
| POST | `/v1/traces/{trace_id}/feedback` | Approve, correct-and-approve, or reject |
| GET | `/v1/training/queue` | Pending/excluded example counts |
| POST | `/v1/training/jobs` | Plan a batch, or explicitly execute local LoRA training |
| GET | `/v1/models` | Base, failed experimental, and qualified models |
| POST | `/v1/models/{id}/evaluation` | Apply fixed qualification criteria |
| POST | `/v1/models/{id}/activate` | Activate only base/qualified models |
| GET | `/v1/routes/{workload}` | Inspect the active route |
| POST | `/v1/routes/{workload}/rollback` | Restore the base route |

Feedback is training-eligible only when payload capture was explicitly enabled.
Approval queues the model response; correction queues the developer's corrected
response; rejection never queues an example and excludes any prior pending row.

The training-job endpoint records a `planned` batch by default. Step 6 adds an
explicit `execute=true` mode that snapshots eligible approvals, exports MLX-LM
records, trains from the frozen base, verifies adapter tensor changes, and
registers an experimental candidate. See `STEP6_LEARNING_LOOP.md`.

## Qualification gate

An adapter becomes `qualified` only when all server-generated independent
metrics pass; clients cannot submit or override scores:

- at least three validation examples;
- every validation example passes;
- heading compliance is 100 percent;
- zero repetition failures;
- zero unsupported-claim failures.

V1 and v2 are seeded as `experimental_failed`, inactive, and cannot be deployed.
No savings claim is produced by this backend.

## Provider safety

Gemini and Groq clients are implemented with direct HTTPS calls and no provider
SDK. A provider key alone does not authorize a call: each request must also set
`allow_cloud=true`. Automatic Gemini fallback happens only after local failure,
explicit opt-in, and key availability. Tests inject mock providers and never
contact either service.
