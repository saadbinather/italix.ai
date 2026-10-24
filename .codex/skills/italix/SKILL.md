---
name: italix
description: Use the local ITALIX gateway to analyze code changes, show learning progress, or plan explicitly approved specialist training and deployment. Trigger for requests such as "ITALIX, analyze my current code changes," "ITALIX, what have you learned?", "ITALIX, train my specialist," and "ITALIX, deploy my specialist."
---

# ITALIX

Use only the registered `italix_status`, `italix_learning_status`, `italix_train_specialist`, `italix_deploy_specialist`, `italix_chat`, and `italix_submit_feedback` MCP tools. Keep inference local: do not authorize cloud calls, download models, change Codex configuration, or modify repository files.

## Status

For model or gateway status requests, call `italix_status`. Report gateway health and each active workload, model, status, and adapter version.

For learning, feedback-queue, adapter, evaluation, or specialist-training progress requests, call `italix_learning_status`. Report pending approved examples and readiness per workload, planned and completed jobs, adapter qualification, active models, and the latest evaluation. Status requests are read-only and never authorize training or activation.

## Specialist training

For training requests, first call `italix_train_specialist` with `execute=false`. Show its readiness, eligible/minimum examples, base model, configuration, and resource estimate. Do not treat the original training request as execution consent.

Only after showing that plan, ask the user to explicitly confirm local LoRA training. Call the tool again with `execute=true` and the exact confirmation text returned by the plan only when the user confirms in a later message. Never infer or manufacture confirmation. Training must remain blocked when readiness is false. Report the job, adapter, metrics, and evaluation exactly as returned. Never activate an adapter; qualification and activation remain separate workflows, and failed candidates remain undeployable.

## Specialist deployment

For deployment requests, first call `italix_deploy_specialist` with the candidate model and `execute=false`. Show its workload, evaluation, current route, qualification status, and whether it is activatable. Do not treat the original deployment request as activation consent.

Only after showing that plan, ask the user to explicitly confirm activation. Call the tool again with `execute=true` and the exact confirmation text returned by the plan only when the user confirms in a later message. Never infer or manufacture confirmation. Never attempt to deploy a candidate unless the plan reports `qualified=true` and `activatable=true`; `experimental_failed` adapters remain blocked even with confirmation. Report the resulting route and audit event exactly as returned.

## Analyze changes or summarize a PR

1. Inspect changes read-only with `git status --short`, `git diff --no-ext-diff --binary`, and `git diff --cached --no-ext-diff --binary`. Never stage, edit, or clean files. Do not read untracked file contents.
2. Before sending a diff, omit binary patches and any file whose path suggests secrets or sensitive material, including `.env*`, credentials, secrets, tokens, private keys, certificates, keystores, auth files, or password stores. Redact values on remaining lines that resemble passwords, API keys, tokens, authorization headers, cookies, private-key material, or connection strings. If safe redaction is uncertain, omit the file or line and say so.
3. If no safe tracked diff remains, do not call `italix_chat`; explain that there is nothing safe to analyze. Otherwise call `italix_chat` with the sanitized diff and user request. Use `pr_summary` for summaries and general change analysis; use `change_triage` only when the user explicitly asks for triage, risk, or prioritization.
4. Present the model's response without silently correcting it, followed by the selected model, route, latency, and trace ID returned by the tool. Mention omitted material without exposing it.

## Capture and feedback

`italix_chat` defaults to `capture=false`. Before setting `capture=true`, explain that the sanitized prompt and model response will be stored locally and ask for explicit user consent. A prior request to analyze code is not consent to capture it.

Never call `italix_submit_feedback` until the user explicitly approves that specific action and trace. Explain that `approve` queues the captured response, `correct` queues the captured prompt with their correction, and `reject` records rejection without adding a training example. Feedback never starts training. Approve/correct require a captured trace; if capture was off, make a new captured request only after separately obtaining consent.

For `change_triage`, display the returned validation status and reason. Clearly label invalid model classifications or corrections; never rewrite, normalize, or silently repair them.

Always end model-generated analysis with: **Review required:** This is model-generated analysis and its claims may be incomplete or incorrect; verify them against the code and tests.
