# Step 7: product dashboard

The Streamlit dashboard is a thin client over the FastAPI gateway. Operational
counts, traces, queue state, jobs, models, routes, and deployment events come
from SQLite through API endpoints. Training and evaluation evidence comes from
the job/model records generated in Steps 4–6. The UI contains no synthetic
operational totals.

## Start it

Terminal 1:

```bash
cd /path/to/italix.ai
source .venv/bin/activate
python -m italix.main
```

Terminal 2:

```bash
cd /path/to/italix.ai
source .venv/bin/activate
ITALIX_API_URL=http://127.0.0.1:8000 streamlit run dashboard.py
```

Streamlit prints its local browser URL, normally `http://localhost:8501`.

## Product areas

- **Command Center:** persisted request, routing, review, queue, job, token,
  latency, active-model, and latest-evaluation status.
- **AI Gateway:** real local/optional cloud routing, explicit capture and cloud
  consent, response metadata, and approve/correct/reject feedback.
- **Teach ITALIX:** queue counts, frozen LoRA configuration, training history,
  loss charts, parameter-update evidence, and an explicit confirmed training
  action.
- **Evaluation:** saved per-example format, repetition, testing evidence,
  content, identifier, and unsupported-claim results.
- **Registry:** model status, current route, eligible activation, rollback, and
  deployment-event history. Failed adapters are not offered for activation.
- **Costs:** measured request/token/latency totals and a separately labeled
  hypothetical scenario. Realized savings are not calculated without provider
  billing evidence.
- **Developer Memory:** explicitly selected Git metadata and approved
  discussion imports, local FTS5 search, cited base-Qwen answers, and
  evidence-based abstention. This remains isolated from the training loop.
- **Demo:** a timed three-minute presentation script.

The trace-list endpoint returns metadata only. It never includes captured
prompts or responses. A single trace can still be inspected by its known ID,
consistent with the consent-based Step 5 behavior.

## Disposable demo state

Create a copy of the current database before a presentation:

```bash
python scripts/prepare_demo.py
ITALIX_DB_PATH=var/demo/italix-demo.db python -m italix.main
```

Use `python scripts/prepare_demo.py --force` to refresh only the disposable
copy. The script never overwrites `var/italix.db`, model artifacts, or sealed
datasets.

## Safety behavior

- Gemini/Groq remain blocked unless the playground cloud toggle is enabled for
  that individual request.
- Training remains disabled until at least one pending example exists and the
  user checks the explicit optimization confirmation.
- Training is synchronous in this MVP; displayed losses are recorded results,
  not fabricated progress animation.
- Only `base` or server-`qualified` models can be activated.
- v1, v2, and v3 remain failed and undeployable.
- The original test split and v3 holdout are not read by the dashboard.
