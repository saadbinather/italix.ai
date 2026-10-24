"""Small SQLite evidence store, feedback queue, and model registry."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from italix.change_triage import validate_triage_output


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    workload TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    selected_model TEXT NOT NULL,
    route TEXT NOT NULL,
    routing_reason TEXT NOT NULL,
    capture_enabled INTEGER NOT NULL,
    prompt_json TEXT,
    response_text TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms REAL NOT NULL,
    validation_json TEXT NOT NULL,
    feedback_status TEXT NOT NULL DEFAULT 'pending',
    error TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    action TEXT NOT NULL,
    corrected_response TEXT,
    eligible INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(trace_id) REFERENCES traces(id)
);
CREATE TABLE IF NOT EXISTS training_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL UNIQUE,
    workload TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    approved_response TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY(trace_id) REFERENCES traces(id)
);
CREATE TABLE IF NOT EXISTS training_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workload TEXT NOT NULL,
    example_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    candidate_id TEXT,
    adapter_path TEXT,
    log_path TEXT,
    metrics_json TEXT,
    error TEXT,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS training_job_examples (
    job_id INTEGER NOT NULL,
    queue_id INTEGER NOT NULL,
    PRIMARY KEY(job_id, queue_id),
    FOREIGN KEY(job_id) REFERENCES training_jobs(id),
    FOREIGN KEY(queue_id) REFERENCES training_queue(id)
);
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    workload TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT,
    metrics_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deployment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workload TEXT NOT NULL,
    model_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(model_id) REFERENCES models(id)
);
CREATE TABLE IF NOT EXISTS memory_sources (
    id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('git', 'discussion')),
    repository TEXT,
    title TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    author TEXT,
    content TEXT NOT NULL,
    reference TEXT,
    metadata_json TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_sources_fts USING fts5(
    source_id UNINDEXED,
    title,
    content,
    tokenize='unicode61 remove_diacritics 2'
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_model_per_workload
ON models(workload) WHERE active = 1;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(training_jobs)")
            }
            additions = {
                "candidate_id": "TEXT",
                "adapter_path": "TEXT",
                "log_path": "TEXT",
                "metrics_json": "TEXT",
                "error": "TEXT",
                "completed_at": "TEXT",
            }
            for name, kind in additions.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE training_jobs ADD COLUMN {name} {kind}")
            now = utc_now()
            seeds = (
                ("qwen-base", "pr_summary", "base", "base", None, {}, 1, now),
                (
                    "pr-summary-deterministic-v1",
                    "pr_summary",
                    "system",
                    "validation_passed",
                    "italix/hybrid_pr_summary.py",
                    {
                        "development_passed": 16,
                        "development_total": 16,
                        "audit_scenarios_passed": 8,
                        "audit_scenarios_total": 8,
                        "source": "ITX-07.3",
                        "trained": False,
                    },
                    0,
                    now,
                ),
                (
                    "adapter-v1",
                    "pr_summary",
                    "adapter",
                    "experimental_failed",
                    "artifacts/adapters/v1",
                    {"validation": "failed", "source": "step3"},
                    0,
                    now,
                ),
                (
                    "adapter-v2",
                    "pr_summary",
                    "adapter",
                    "experimental_failed",
                    "artifacts/adapters/v2",
                    {"validation_passed": 2, "validation_total": 3, "source": "step4"},
                    0,
                    now,
                ),
                ("qwen-base-triage", "change_triage", "base", "base", None, {}, 1, now),
            )
            connection.executemany(
                """INSERT OR IGNORE INTO models
                (id, workload, kind, status, path, metrics_json, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(*row[:5], json.dumps(row[5]), *row[6:]) for row in seeds],
            )

    def insert_trace(self, trace: dict[str, Any]) -> None:
        fields = ", ".join(trace)
        placeholders = ", ".join("?" for _ in trace)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO traces ({fields}) VALUES ({placeholders})",
                tuple(trace.values()),
            )

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM traces WHERE id = ?", (trace_id,)).fetchone()
        return dict(row) if row else None

    def list_models(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM models ORDER BY created_at, id").fetchall()
        return [dict(row) for row in rows]

    def model(self, model_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        return dict(row) if row else None

    def dashboard_overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            trace = connection.execute(
                """SELECT COUNT(*) AS total_requests,
                COALESCE(SUM(error IS NULL), 0) AS successful_requests,
                COALESCE(SUM(error IS NOT NULL), 0) AS failed_requests,
                COALESCE(SUM(route IN ('local', 'deterministic')), 0) AS local_requests,
                COALESCE(SUM(route='deterministic'), 0) AS deterministic_requests,
                COALESCE(SUM(route='local'), 0) AS model_inference_requests,
                COALESCE(SUM(route='cloud'), 0) AS cloud_requests,
                COALESCE(SUM(route NOT IN ('local', 'deterministic', 'cloud')), 0)
                    AS other_requests,
                COALESCE(SUM(capture_enabled), 0) AS captured_interactions,
                COALESCE(SUM(feedback_status != 'pending'), 0) AS reviewed_interactions,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                AVG(CASE WHEN route IN ('local', 'deterministic') AND error IS NULL
                    THEN latency_ms END)
                    AS average_local_latency_ms,
                AVG(CASE WHEN route='deterministic' AND error IS NULL THEN latency_ms END)
                    AS average_deterministic_latency_ms,
                AVG(CASE WHEN route='local' AND error IS NULL THEN latency_ms END)
                    AS average_model_inference_latency_ms,
                AVG(CASE WHEN route='cloud' AND error IS NULL THEN latency_ms END)
                    AS average_cloud_latency_ms
                FROM traces"""
            ).fetchone()
            queue = connection.execute(
                """SELECT
                COALESCE(SUM(status='pending'), 0) AS pending,
                COALESCE(SUM(status='used'), 0) AS used,
                COALESCE(SUM(status='excluded'), 0) AS excluded
                FROM training_queue"""
            ).fetchone()
            completed_jobs = connection.execute(
                "SELECT COUNT(*) FROM training_jobs WHERE status='completed'"
            ).fetchone()[0]
            active = connection.execute(
                "SELECT id, workload, kind, status FROM models WHERE active=1 ORDER BY workload"
            ).fetchall()
            registry = connection.execute(
                """SELECT
                COALESCE(SUM(kind='system'), 0) AS deterministic_systems,
                COALESCE(SUM(kind='base'), 0) AS base_models,
                COALESCE(SUM(kind='adapter' AND status='experimental_failed'), 0)
                    AS experimental_lora_adapters,
                COALESCE(SUM(kind='adapter' AND status='qualified'), 0)
                    AS qualified_lora_adapters,
                COALESCE(SUM(kind='system' AND active=1), 0)
                    AS active_deterministic_systems,
                COALESCE(SUM(kind='base' AND active=1), 0) AS active_base_models,
                COALESCE(SUM(kind='adapter' AND active=1), 0) AS active_lora_adapters
                FROM models"""
            ).fetchone()
            latest = connection.execute(
                """SELECT id, candidate_id, status, completed_at, metrics_json
                FROM training_jobs WHERE status='completed'
                ORDER BY completed_at DESC LIMIT 1"""
            ).fetchone()
            latest_model = connection.execute(
                """SELECT id, status, metrics_json FROM models
                WHERE kind='adapter' ORDER BY created_at DESC, id DESC LIMIT 1"""
            ).fetchone()
        result = dict(trace)
        result.update({f"queue_{key}": value for key, value in dict(queue).items()})
        result["training_jobs_completed"] = completed_jobs
        result["active_models"] = [dict(row) for row in active]
        result["latest_training_job"] = self._decoded_job(latest) if latest else None
        result["latest_evaluation"] = None
        if latest_model:
            metrics = json.loads(latest_model["metrics_json"] or "{}")
            if "evaluation" in metrics:
                metrics = metrics["evaluation"]
            candidates = metrics.get("candidates", [])
            candidate = next((item for item in candidates if item["name"] == "candidate"), None)
            if candidate:
                result["latest_evaluation"] = {
                    "model_id": latest_model["id"],
                    "status": latest_model["status"],
                    "passed": candidate["passed"],
                    "total": candidate["total"],
                    "qualified": bool(metrics.get("qualified")),
                }
        result["measured_cloud_cost_usd"] = None
        result["cloud_cost_note"] = "No provider billing or price evidence has been recorded."
        usage_keys = (
            "total_requests", "successful_requests", "failed_requests", "local_requests",
            "deterministic_requests", "model_inference_requests", "cloud_requests",
            "other_requests", "captured_interactions", "reviewed_interactions",
            "prompt_tokens", "completion_tokens",
        )
        latency_keys = (
            "average_local_latency_ms", "average_deterministic_latency_ms",
            "average_model_inference_latency_ms", "average_cloud_latency_ms",
        )
        result["observed_usage"] = {key: result[key] for key in usage_keys}
        result["latency"] = {key: result[key] for key in latency_keys}
        result["registry"] = dict(registry)
        result["costs"] = {
            "measured_cloud_cost_usd": None,
            "projected_cost_usd": None,
            "projection_configured": False,
            "note": result["cloud_cost_note"],
        }
        return result

    def list_trace_metadata(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT id, created_at, workload, requested_model, selected_model,
                route, routing_reason, capture_enabled, prompt_tokens, completion_tokens,
                latency_ms, feedback_status, error FROM traces
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _decoded_job(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json") or "{}")
        return result

    def list_training_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM training_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decoded_job(row) for row in rows]

    def deployment_history(self, workload: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT id, workload, model_id, action, created_at
                FROM deployment_events WHERE workload=? ORDER BY id DESC LIMIT ?""",
                (workload, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def active_model(self, workload: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM models WHERE workload = ? AND active = 1", (workload,)
            ).fetchone()
        if row is None:
            raise LookupError(f"no active model for workload {workload}")
        return dict(row)

    def activate_model(
        self, model_id: str, workload: str, *, action: str = "activate"
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM models WHERE id = ? AND workload = ?", (model_id, workload)
            ).fetchone()
            if row is None:
                raise LookupError(model_id)
            adapter_allowed = row["kind"] == "adapter" and row["status"] == "qualified"
            system_allowed = row["kind"] == "system" and row["status"] == "validation_passed"
            base_allowed = row["kind"] == "base" and row["status"] == "base"
            if not (adapter_allowed or system_allowed or base_allowed):
                raise PermissionError(
                    f"model status {row['status']} is not eligible for deployment"
                )
            connection.execute("UPDATE models SET active = 0 WHERE workload = ?", (workload,))
            connection.execute("UPDATE models SET active = 1 WHERE id = ?", (model_id,))
            connection.execute(
                """INSERT INTO deployment_events (workload, model_id, action, created_at)
                VALUES (?, ?, ?, ?)""",
                (workload, model_id, action, utc_now()),
            )
        return self.active_model(workload)

    def apply_model_evaluation(self, model_id: str, result: dict[str, Any]) -> dict[str, Any]:
        qualified = bool(result["qualified"])
        status = "qualified" if qualified else "experimental_failed"
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            if row is None:
                raise LookupError(model_id)
            if row["kind"] != "adapter":
                raise PermissionError("only adapter candidates can be evaluated")
            connection.execute(
                "UPDATE models SET status=?, metrics_json=?, active=0 WHERE id=?",
                (status, json.dumps(result), model_id),
            )
        return {"id": model_id, "status": status, "qualified": qualified, "evaluation": result}

    def add_feedback(self, trace_id: str, action: str, corrected: str | None) -> dict[str, Any]:
        trace = self.trace(trace_id)
        if trace is None:
            raise LookupError(trace_id)
        eligible = bool(trace["capture_enabled"] and trace["prompt_json"] and trace["response_text"])
        if action in {"approve", "correct"} and not eligible:
            raise PermissionError("captured prompt and response are required for training eligibility")
        if action == "correct" and trace["workload"] == "change_triage":
            source = "\n".join(
                message.get("content", "") for message in json.loads(trace["prompt_json"])
            )
            validation = validate_triage_output(corrected or "", source)
            if not validation["valid"]:
                raise ValueError(f"invalid change_triage correction: {validation['reason']}")
        status = {"approve": "approved", "correct": "corrected_approved", "reject": "rejected"}[action]
        selected = self.model(trace["selected_model"])
        training_eligible = eligible and (not selected or selected["kind"] != "system")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO feedback (trace_id, action, corrected_response, eligible, created_at) VALUES (?, ?, ?, ?, ?)",
                (trace_id, action, corrected, int(eligible), utc_now()),
            )
            connection.execute("UPDATE traces SET feedback_status = ? WHERE id = ?", (status, trace_id))
            if action == "reject":
                connection.execute(
                    "UPDATE training_queue SET status = 'excluded' WHERE trace_id = ?", (trace_id,)
                )
            elif training_eligible:
                response = corrected if action == "correct" else trace["response_text"]
                connection.execute(
                    """INSERT INTO training_queue
                    (trace_id, workload, messages_json, approved_response, status, created_at)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                    approved_response = excluded.approved_response, status = 'pending', created_at = excluded.created_at""",
                    (trace_id, trace["workload"], trace["prompt_json"], response, utc_now()),
                )
        return {
            "trace_id": trace_id,
            "feedback_status": status,
            "queued": action != "reject" and training_eligible,
        }

    def queue_summary(
        self, workload: str | None = None, minimum_examples: int = 10
    ) -> dict[str, Any]:
        clause, params = ("", ()) if workload is None else (" WHERE workload = ?", (workload,))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM training_queue" + clause + " GROUP BY status",
                params,
            ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        pending = counts.get("pending", 0)
        return {
            "workload": workload,
            "counts": counts,
            "pending": pending,
            "minimum_examples": minimum_examples,
            "enough_examples": pending >= minimum_examples,
        }

    def create_training_job(
        self, workload: str, minimum: int, candidate_id: str | None = None
    ) -> dict[str, Any]:
        count = self.queue_summary(workload, minimum)["pending"]
        if count < minimum:
            raise PermissionError(f"need {minimum} pending examples; found {count}")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO training_jobs
                (workload, example_count, status, created_at, candidate_id)
                VALUES (?, ?, 'planned', ?, ?)""",
                (workload, count, utc_now(), candidate_id),
            )
            job_id = cursor.lastrowid
            rows = connection.execute(
                "SELECT id FROM training_queue WHERE workload = ? AND status = 'pending' ORDER BY id",
                (workload,),
            ).fetchall()
            connection.executemany(
                "INSERT INTO training_job_examples (job_id, queue_id) VALUES (?, ?)",
                [(job_id, row["id"]) for row in rows],
            )
        return {
            "id": job_id,
            "workload": workload,
            "example_count": count,
            "status": "planned",
            "candidate_id": candidate_id,
        }

    def training_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM training_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def job_examples(self, job_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT q.* FROM training_queue q
                JOIN training_job_examples j ON j.queue_id = q.id
                WHERE j.job_id = ? ORDER BY q.id""",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def start_training_job(self, job_id: int) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE training_jobs SET status = 'running' WHERE id = ?", (job_id,))

    def finish_training_job(
        self,
        job_id: int,
        *,
        candidate_id: str,
        adapter_path: str,
        log_path: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """UPDATE training_jobs SET status='completed', candidate_id=?, adapter_path=?,
                log_path=?, metrics_json=?, completed_at=? WHERE id=?""",
                (candidate_id, adapter_path, log_path, json.dumps(metrics), utc_now(), job_id),
            )
            connection.execute(
                """UPDATE training_queue SET status='used'
                WHERE id IN (SELECT queue_id FROM training_job_examples WHERE job_id=?)""",
                (job_id,),
            )
            workload = connection.execute(
                "SELECT workload FROM training_jobs WHERE id=?", (job_id,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO models
                (id, workload, kind, status, path, metrics_json, active, created_at)
                VALUES (?, ?, 'adapter', 'experimental', ?, ?, 0, ?)
                ON CONFLICT(id) DO UPDATE SET status='experimental', path=excluded.path,
                metrics_json=excluded.metrics_json, active=0""",
                (candidate_id, workload, adapter_path, json.dumps(metrics), utc_now()),
            )
        return self.training_job(job_id)

    def fail_training_job(self, job_id: int, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE training_jobs SET status='failed', error=?, completed_at=? WHERE id=?",
                (error, utc_now(), job_id),
            )
