"""ITALIX.ai product dashboard backed entirely by the local FastAPI service."""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from italix.dashboard_client import DashboardAPIError, DashboardClient


load_dotenv(override=False)

st.set_page_config(page_title="ITALIX.ai", page_icon="◈", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.7rem; max-width: 1450px;}
    [data-testid="stMetric"] {background:#111827;border:1px solid #263247;
      padding:14px;border-radius:12px;}
    .italix-brand {font-size:2rem;font-weight:750;letter-spacing:-.04em;}
    .italix-brand span {color:#53e0b8;}
    .tagline {color:#93a4b8;margin-top:-8px;margin-bottom:20px;}
    .flow {display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 24px}
    .flow div {border:1px solid #263247;border-radius:12px;padding:14px;
      background:linear-gradient(135deg,#111827,#0b1220)}
    .flow b {color:#53e0b8;display:block;font-size:.8rem;letter-spacing:.08em}
    .journey {display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:18px 0 26px}
    .journey div {border:1px solid #263247;border-radius:12px;padding:12px;background:#0d1524;min-height:92px}
    .journey b {display:block;color:#53e0b8;font-size:.72rem;letter-spacing:.07em;margin-bottom:6px}
    .honesty {border-left:4px solid #f3b33d;background:#211b10;padding:12px 16px;
      border-radius:8px;margin:8px 0 16px}
    </style>
    <div class="italix-brand">ITALIX<span>.ai</span></div>
    <div class="tagline">Your AI Learns. Your Costs Shrink.</div>
    """,
    unsafe_allow_html=True,
)

api_url = st.sidebar.text_input(
    "Gateway URL", os.getenv("ITALIX_API_URL", "http://127.0.0.1:8000")
)
client = DashboardClient(api_url)


def api_get(path: str, **params):
    try:
        return client.get(path, **params)
    except DashboardAPIError as exc:
        st.error(str(exc))
        return None


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def fmt_ms(value):
    return "—" if value is None else f"{value:,.0f} ms"


health = api_get("/health")
if not health:
    st.stop()
st.sidebar.success("Local gateway online")
st.sidebar.caption(f"Local model: {health['local_model']}")

tabs = st.tabs(
    ["Learning Journey", "AI Gateway", "Teach ITALIX", "Evaluation", "Registry", "Costs", "Developer Memory", "Demo"]
)

with tabs[0]:
    overview = api_get("/v1/dashboard/overview") or {}
    st.subheader("From expensive calls to a verified local specialist")
    st.write("Send real work, capture expert corrections, train locally in controlled batches, and deploy only when held-out evidence says the specialist is better.")
    st.markdown(
        """<div class="journey">
        <div><b>1 · SEND</b>Route a developer request</div>
        <div><b>2 · REVIEW</b>Approve or correct output</div>
        <div><b>3 · TEACH</b>Queue trusted examples</div>
        <div><b>4 · TRAIN</b>Run real MLX LoRA</div>
        <div><b>5 · PROVE</b>Compare frozen evals</div>
        <div><b>6 · DEPLOY</b>Activate only if better</div>
        </div>""", unsafe_allow_html=True,
    )
    cols = st.columns(6)
    cards = [
        ("Requests", overview.get("total_requests", 0)),
        ("Local / cloud", f"{overview.get('local_requests', 0)} / {overview.get('cloud_requests', 0)}"),
        ("Captured", overview.get("captured_interactions", 0)),
        ("Reviewed", overview.get("reviewed_interactions", 0)),
        ("Queue", overview.get("queue_pending", 0)),
        ("Completed jobs", overview.get("training_jobs_completed", 0)),
    ]
    for column, (label, value) in zip(cols, cards):
        column.metric(label, value)
    active = overview.get("active_models", [])
    st.info(
        "Active route: " + ", ".join(f"{m['workload']} → {m['id']}" for m in active)
        if active else "No active route recorded"
    )
    latest_eval = overview.get("latest_evaluation")
    if latest_eval:
        st.caption(
            f"Latest evaluation: {latest_eval['model_id']} passed "
            f"{latest_eval['passed']}/{latest_eval['total']} — {latest_eval['status']}"
        )
    st.markdown(
        """<div class="flow">
        <div><b>01 · OBSERVE</b>Consent-based traces and corrections</div>
        <div><b>02 · EVALUATE</b>Frozen, server-owned quality gates</div>
        <div><b>03 · IMPROVE</b>Controlled local LoRA batches</div>
        <div><b>04 · DEPLOY</b>Qualified specialists with rollback</div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="honesty"><b>Current evidence:</b> PR-summary v3 remains failed. '
        "Change-triage learned real company routing behavior and improved from 0/12 to 9/12 "
        "with a compact prompt, but the gate requires 12/12—so it also remains undeployed. "
        "The deterministic policy baseline scored 12/12 on validation and is tracked separately as a system candidate, not a qualified adapter. No realized savings or cloud "
        "cost has been measured.</div>",
        unsafe_allow_html=True,
    )
    a, b, c = st.columns(3)
    a.metric("Measured tokens", overview.get("prompt_tokens", 0) + overview.get("completion_tokens", 0))
    b.metric("Average local latency", fmt_ms(overview.get("average_local_latency_ms")))
    c.metric("Measured cloud cost", "Not available")
    traces = api_get("/v1/traces", limit=10)
    if traces:
        st.caption("Recent trace metadata — raw prompts are never included in this list")
        st.dataframe(traces["data"], width="stretch", hide_index=True)

with tabs[1]:
    st.subheader("AI Gateway · Live Playground")
    task = st.text_area(
        "Developer request or Git diff",
        height=220,
        placeholder="Summarize this PR:\n\ndiff --git a/...",
        key="gateway_task",
    )
    c1, c2, c3, c4 = st.columns(4)
    workload = c1.selectbox("Workload", ["change_triage", "pr_summary"])
    requested_model = c2.selectbox("Routing", ["italix-auto", "qwen-base", "gemini", "groq"])
    capture = c3.toggle("Capture payload", value=True, help="Required before feedback can train ITALIX")
    allow_cloud = c4.toggle("Authorize cloud", value=False, help="Off means no Gemini/Groq request is allowed")
    if requested_model in {"gemini", "groq"} and not allow_cloud:
        st.warning("Cloud selection is locked until you explicitly authorize cloud inference.")
    if st.button("Run through ITALIX", type="primary", disabled=not task.strip()):
        try:
            result = client.post(
                "/v1/chat/completions",
                {
                    "model": requested_model,
                    "messages": [{"role": "user", "content": task}],
                    "workload": workload,
                    "capture": capture,
                    "allow_cloud": allow_cloud,
                    "temperature": 0.0,
                    "max_tokens": 160,
                },
            )
            st.session_state["last_completion"] = result
        except DashboardAPIError as exc:
            st.error(str(exc))
    result = st.session_state.get("last_completion")
    if result:
        meta = result["italix"]
        st.markdown(result["choices"][0]["message"]["content"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Route", meta["route"])
        m2.metric("Registry model", meta["registry_model"])
        trace = api_get(f"/v1/traces/{meta['trace_id']}") or {}
        m3.metric("Latency", fmt_ms(trace.get("latency_ms")))
        m4.metric("Trace", meta["trace_id"][-12:])
        st.caption(meta["routing_reason"])
        if not meta["capture_enabled"]:
            st.info("Feedback is disabled because payload capture was not enabled for this trace.")
        else:
            correction = st.text_area(
                "Approved correction",
                value=result["choices"][0]["message"]["content"],
                height=180,
            )
            f1, f2, f3 = st.columns(3)
            actions = {
                "approve": f1.button("Approve response", width="stretch"),
                "correct": f2.button("Save correction", width="stretch"),
                "reject": f3.button("Reject", width="stretch"),
            }
            chosen = next((name for name, clicked in actions.items() if clicked), None)
            if chosen:
                payload = {"action": chosen}
                if chosen == "correct":
                    payload["corrected_response"] = correction
                try:
                    feedback = client.post(f"/v1/traces/{meta['trace_id']}/feedback", payload)
                    queue = client.get("/v1/training/queue", workload=workload)
                    st.success(
                        f"Feedback: {feedback['feedback_status']}. Pending training examples: {queue['pending']}."
                    )
                except DashboardAPIError as exc:
                    st.error(str(exc))

with tabs[2]:
    st.subheader("Teach ITALIX · Controlled Local Learning")
    training_workload = st.selectbox("Specialist workload", ["change_triage", "pr_summary"], key="training_workload")
    queue = api_get("/v1/training/queue", workload=training_workload) or {"counts": {}, "pending": 0}
    jobs = (api_get("/v1/training/jobs") or {"data": []})["data"]
    jobs = [job for job in jobs if job["workload"] == training_workload]
    config = api_get("/v1/training/config", workload=training_workload) or {}
    q1, q2, q3 = st.columns(3)
    q1.metric("Pending approvals", queue.get("pending", 0))
    q2.metric("Used", queue.get("counts", {}).get("used", 0))
    q3.metric("Rejected / excluded", queue.get("counts", {}).get("excluded", 0))
    with st.expander("Frozen training configuration", expanded=True):
        st.json(config)
    st.caption("Training is synchronous in this MVP. The spinner reflects the real HTTP job; losses appear only after MLX-LM records them.")
    candidate_id = st.text_input("New adapter ID", value="triage-adapter-next" if training_workload == "change_triage" else "adapter-v4")
    confirmed = st.checkbox(
        f"I approve real local optimization using {queue.get('pending', 0)} pending {training_workload} example(s)."
    )
    if st.button(
        "Train New Specialist",
        type="primary",
        disabled=not confirmed or queue.get("pending", 0) < 1,
    ):
        with st.spinner("MLX-LM is performing genuine optimizer updates on this Mac…"):
            try:
                job = client.post(
                    "/v1/training/jobs",
                    {
                        "workload": training_workload,
                        "minimum_examples": 1,
                        "candidate_id": candidate_id,
                        "execute": True,
                    },
                )
                st.success(f"Job {job['id']} finished with status {job['status']}.")
                st.rerun()
            except DashboardAPIError as exc:
                st.error(str(exc))
    if jobs:
        st.markdown("#### Training history")
        rows = [{k: v for k, v in job.items() if k != "metrics"} for job in jobs]
        st.dataframe(rows, width="stretch", hide_index=True)
        selected_job = st.selectbox("Loss evidence", jobs, format_func=lambda j: f"Job {j['id']} · {j['candidate_id']}")
        metrics = selected_job.get("metrics", {})
        losses = metrics.get("training_losses", [])
        if losses:
            st.line_chart({"training loss": losses})
        validation = metrics.get("validation_losses", [])
        if validation:
            st.line_chart({"validation loss": {str(v['step']): v['loss'] for v in validation}})
        p1, p2, p3 = st.columns(3)
        p1.metric("Trainable parameters", f"{metrics.get('trainable_parameters', 0):,}")
        p2.metric("Changed parameters", f"{metrics.get('changed_elements', 0):,}")
        p3.metric("Peak MLX memory", f"{metrics.get('peak_mlx_memory_gb', 0):.3f} GB")

with tabs[3]:
    st.subheader("Model Evaluation · Quality Before Deployment")
    models = (api_get("/v1/models") or {"data": []})["data"]
    adapters_with_evidence = [m for m in models if m["kind"] == "adapter"]
    selected_model = st.selectbox("Evaluation evidence", adapters_with_evidence,
                                  index=max(0, len(adapters_with_evidence)-1), format_func=lambda m: f"{m['id']} · {m['workload']} · {m['status']}")
    stored = decode(selected_model.get("metrics_json")) if selected_model else {}
    evidence = stored.get("evaluation", stored)
    candidates = evidence.get("candidates", [])
    if candidates:
        summary = [
            {"model": c["name"], "passed": c["passed"], "total": c["total"], "decision": "qualified" if evidence.get("qualified", False) else "failed" if c["name"] == "candidate" else "baseline"}
            for c in candidates
        ]
        st.dataframe(summary, width="stretch", hide_index=True)
        chosen = st.selectbox("Inspect evidence", candidates, format_func=lambda c: c["name"])
        checks = []
        for example in chosen.get("examples", []):
            if "field_accuracy" in example:
                checks.append({"example": example["index"], "pass": example["passed"],
                               "exact JSON": example["format_ok"], **example["field_accuracy"]})
            else:
                checks.append(
                    {"example": example["index"], "pass": example["passed"],
                     "format": example["format_ok"],
                     "repetition": round(example["repetition_ratio"], 3),
                     "testing evidence": example["testing_ok"],
                     "content recall": round(example["content_recall"], 3),
                     "identifier recall": round(example["identifier_recall"], 3),
                     "unsupported": ", ".join(example["unsupported_hits"]) or "—"}
                )
        st.dataframe(checks, width="stretch", hide_index=True)
        with st.expander("Generated outputs"):
            for example in chosen.get("examples", []):
                st.markdown(f"**Example {example['index']} · {'PASS' if example['passed'] else 'FAIL'}**")
                st.code(example["response"], language="markdown")
    else:
        st.info("No saved server-side evaluation evidence is available yet.")
    systems = [m for m in models if m["kind"] == "system"]
    if systems:
        st.markdown("#### Deterministic system baselines")
        system_rows = []
        for model in systems:
            metrics = decode(model["metrics_json"])
            system_rows.append({"candidate": model["id"], "status": model["status"],
                                "validation": f"{metrics.get('passed', 0)}/{metrics.get('total', 0)}",
                                "adapter qualified": metrics.get("adapter_qualification", False),
                                "adapter used": metrics.get("adapter_used", False)})
        st.dataframe(system_rows, width="stretch", hide_index=True)
    if selected_model and selected_model["status"] == "experimental":
        if st.button("Run frozen server evaluation"):
            try:
                result = client.post(f"/v1/models/{selected_model['id']}/evaluation",
                                     {"workload": selected_model["workload"], "split": "valid"})
                st.success(f"Decision: {result['status']}")
                st.rerun()
            except DashboardAPIError as exc:
                st.error(str(exc))
    st.warning("Training loss measures optimization. Validation quality measures behavior. Only the deployment gate controls eligibility.")

with tabs[4]:
    st.subheader("Model Registry & Routing")
    models = (api_get("/v1/models") or {"data": []})["data"]
    display_models = [{k: v for k, v in model.items() if k != "metrics_json"} for model in models]
    st.dataframe(display_models, width="stretch", hide_index=True)
    route_workload = st.selectbox("Route workload", ["change_triage", "pr_summary"], key="route_workload")
    route = api_get(f"/v1/routes/{route_workload}")
    if route:
        st.success(f"Active {route_workload} route: {route['id']} ({route['status']})")
    qualified = [m for m in models if m["workload"] == route_workload and m["status"] in {"qualified", "base"} and not m["active"]]
    if qualified:
        target = st.selectbox("Eligible model", qualified, format_func=lambda m: m["id"])
        if st.button("Activate eligible model"):
            try:
                client.post(f"/v1/models/{target['id']}/activate", {"workload": route_workload})
                st.success(f"Activated {target['id']}.")
                st.rerun()
            except DashboardAPIError as exc:
                st.error(str(exc))
    else:
        st.caption("No inactive qualified adapter is available. Failed adapters cannot be selected.")
    base_id = "qwen-base-triage" if route_workload == "change_triage" else "qwen-base"
    if st.button(f"Rollback {route_workload} to {base_id}"):
        try:
            client.post(f"/v1/routes/{route_workload}/rollback")
            st.success(f"Route rolled back to {base_id}.")
            st.rerun()
        except DashboardAPIError as exc:
            st.error(str(exc))
    history = api_get(f"/v1/routes/{route_workload}/history")
    if history and history["data"]:
        st.markdown("#### Deployment history")
        st.dataframe(history["data"], width="stretch", hide_index=True)

with tabs[5]:
    st.subheader("API Cost Optimization")
    overview = api_get("/v1/dashboard/overview") or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("Actual local requests", overview.get("local_requests", 0))
    c2.metric("Actual cloud requests", overview.get("cloud_requests", 0))
    c3.metric("Measured cloud cost", "Not available")
    st.info(overview.get("cloud_cost_note", "No billing evidence is available."))
    st.markdown("#### Hypothetical scenario — not realized savings")
    volume = st.number_input("Requests per month", min_value=0, value=10000, step=1000)
    p1, p2 = st.columns(2)
    input_tokens = p1.number_input("Average input tokens / request", min_value=0, value=1000, step=100)
    output_tokens = p2.number_input("Average output tokens / request", min_value=0, value=250, step=50)
    p3, p4 = st.columns(2)
    input_price = p3.number_input("Cloud input price / 1M tokens (USD)", min_value=0.0, value=3.0, step=0.5)
    output_price = p4.number_input("Cloud output price / 1M tokens (USD)", min_value=0.0, value=15.0, step=0.5)
    local_share = st.slider("Requests eligible for local execution", 0, 100, 70)
    fallback_rate = st.slider("Eligible requests falling back to cloud", 0, 100, 10)
    local_per_request = st.number_input("Estimated local compute cost per request (USD)", min_value=0.0, value=0.0002, step=0.0001, format="%.4f")
    fixed_local = st.number_input("Estimated fixed local hosting/electricity per month (USD)", min_value=0.0, value=10.0, step=1.0)
    cloud_per_request = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    monthly_cloud = volume * cloud_per_request
    eligible_requests = volume * local_share / 100
    fallback_requests = eligible_requests * fallback_rate / 100
    local_successes = eligible_requests - fallback_requests
    cloud_requests = volume - eligible_requests + fallback_requests
    mixed_cost = cloud_requests * cloud_per_request + eligible_requests * local_per_request + fixed_local
    avoided = monthly_cloud - mixed_cost
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Baseline scenario", f"${monthly_cloud:,.2f} / month")
    s2.metric("Local-first scenario", f"${mixed_cost:,.2f} / month")
    s3.metric("Potential scenario difference", f"${avoided:,.2f} / month")
    s4.metric("Projected cloud calls avoided", f"{local_successes:,.0f}")
    st.caption("Hypothetical scenario only. Local compute and fixed hosting are user estimates; engineering and hardware depreciation remain excluded. No realized customer savings claim is made.")

with tabs[6]:
    st.subheader("Developer Memory · Local Engineering History")
    st.caption("Secondary feature · imports remain separate from LoRA training and never use cloud inference")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Import Git history")
        repo_path = st.text_input("Explicit local repository path", placeholder="/path/to/approved/repository")
        max_commits = st.number_input("Recent commits", min_value=1, max_value=200, value=50)
        include_stats = st.checkbox("Include bounded diff statistics (no file contents)")
        if st.button("Import selected Git repository", disabled=not repo_path.strip()):
            try:
                imported = client.post(
                    "/v1/memory/import/git",
                    {"repository_path": repo_path, "max_commits": max_commits,
                     "include_diff_summary": include_stats},
                )
                st.success(f"Imported {imported['imported']} commits; skipped {imported['duplicates']} duplicates.")
            except DashboardAPIError as exc:
                st.error(str(exc))
    with right:
        st.markdown("#### Import approved discussions")
        discussion_path = st.text_input(
            "Approved JSON/JSONL path", value=str(Path("data/demo_discussions.jsonl").resolve())
        )
        st.caption("The bundled demo discussions are fictional and explicitly marked synthetic.")
        discussion_confirmed = st.checkbox("I approve importing this selected discussion file")
        if st.button(
            "Import approved discussions",
            disabled=not discussion_confirmed or not discussion_path.strip(),
        ):
            try:
                imported = client.post(
                    "/v1/memory/import/discussions", {"file_path": discussion_path}
                )
                st.success(f"Imported {imported['imported']} messages; skipped {imported['duplicates']} duplicates.")
            except DashboardAPIError as exc:
                st.error(str(exc))
    st.divider()
    search_query = st.text_input("Search engineering history", placeholder="Redis caching decision")
    if st.button("Search memory", disabled=not search_query.strip()):
        result = api_get("/v1/memory/search", q=search_query, limit=8)
        if result is not None:
            st.session_state["memory_search"] = result["data"]
    for item in st.session_state.get("memory_search", []):
        citation = item["metadata"]["citation"]
        with st.expander(f"{citation} · {item['title']}"):
            st.write(item["content"])
            st.caption(f"{item.get('author') or 'Unknown'} · {item['timestamp']}")
            if item["metadata"].get("synthetic"):
                st.caption("Synthetic demonstration discussion")
            if item.get("reference"):
                st.link_button("Open source", item["reference"])
    question = st.text_area(
        "Ask developer memory", placeholder="Why did we introduce Redis caching?", key="memory_question"
    )
    if st.button("Ask local Qwen", type="primary", disabled=not question.strip()):
        with st.spinner("Retrieving local evidence and asking the frozen base model…"):
            try:
                st.session_state["memory_answer"] = client.post(
                    "/v1/memory/query", {"question": question, "limit": 5}
                )
            except DashboardAPIError as exc:
                st.error(str(exc))
    answer = st.session_state.get("memory_answer")
    if answer:
        if answer["abstained"]:
            st.warning(answer["answer"])
        else:
            st.markdown(answer["answer"])
            st.caption(f"Local model: {answer['model']} · Cloud used: {answer['cloud_used']}")
        if answer["sources"]:
            st.markdown("#### Sources")
            for item in answer["sources"]:
                label = f"{item['metadata']['citation']} — {item['title']}"
                if item.get("reference"):
                    st.markdown(f"- [{label}]({item['reference']})")
                else:
                    st.markdown(f"- {label}")

with tabs[7]:
    st.subheader("3–5 Minute Hackathon Demo")
    st.markdown(
        """
1. **Problem (0:00–0:30):** repeated developer tasks consume frontier tokens and lose expert corrections.
2. **Observe (0:30–1:10):** send an `auth/permissions` diff through `change_triage` with capture enabled; show its real local route and trace.
3. **Human signal (1:10–1:40):** correct it to `identity / high / security`, approve it, and show the queue increment.
4. **Improve (1:40–2:20):** show the saved MLX job—1,318,912 changed parameters, 32.97 seconds, and the real loss curve. A fresh run is optional.
5. **Evaluate (2:20–3:10):** compare compact base 0/12, long scaffold 6/12, and LoRA 9/12 at 140 versus 391 prompt tokens.
6. **Deploy safely (3:10–3:40):** show the three remaining risk errors, HTTP 409 protection, and `qwen-base-triage` still active.
7. **Hybrid truth (3:40–4:15):** show deterministic policy at 12/12 as a separate system baseline—not as adapter success—and explain abstention/cloud opt-in for unknown paths.
8. **Economics + memory (4:15–5:00):** adjust token prices and fallback rate, then ask Developer Memory why Redis caching was introduced.
        """
    )
    st.code(
        "python scripts/prepare_demo.py\n"
        "ITALIX_DB_PATH=var/demo/italix-demo.db python -m italix.main\n"
        "ITALIX_API_URL=http://127.0.0.1:8000 streamlit run dashboard.py",
        language="bash",
    )
    st.caption("The demo database is a disposable copy. The operational database and sealed evaluation splits are not modified.")
