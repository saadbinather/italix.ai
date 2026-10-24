"""Frozen contract for the company-specific change-triage specialist."""

from __future__ import annotations

import json
from typing import Any

COMPACT_PROMPT = """You are the ITALIX change-triage specialist. Return only one compact JSON object
with string keys owner, risk, reviewer in that order. Do not add markdown or explanation."""

PRODUCTION_PROMPT = COMPACT_PROMPT + """
Apply the internal routing policy:
- billing/ledger changes: owner payments, risk high, reviewer finops
- auth/permissions changes: owner identity, risk high, reviewer security
- infra/terraform changes: owner platform, risk high, reviewer sre
- api/rate_limit changes: owner platform, risk medium, reviewer sre
- pricing/cache changes: owner growth, risk medium, reviewer platform
- web/components changes: owner product, risk low, reviewer frontend
Use the first matching path and emit exactly the three allowed keys."""

PRODUCTION_PROMPT += """
Examples:
billing/ledger/example.py -> {"owner":"payments","risk":"high","reviewer":"finops"}
auth/permissions/example.py -> {"owner":"identity","risk":"high","reviewer":"security"}
infra/terraform/example.tf -> {"owner":"platform","risk":"high","reviewer":"sre"}
api/rate_limit/example.py -> {"owner":"platform","risk":"medium","reviewer":"sre"}
pricing/cache/example.py -> {"owner":"growth","risk":"medium","reviewer":"platform"}
web/components/example.tsx -> {"owner":"product","risk":"low","reviewer":"frontend"}
Copy the matching example's values exactly, but output only the JSON object."""

LABELS = {
    "billing/ledger": {"owner": "payments", "risk": "high", "reviewer": "finops"},
    "auth/permissions": {"owner": "identity", "risk": "high", "reviewer": "security"},
    "infra/terraform": {"owner": "platform", "risk": "high", "reviewer": "sre"},
    "api/rate_limit": {"owner": "platform", "risk": "medium", "reviewer": "sre"},
    "pricing/cache": {"owner": "growth", "risk": "medium", "reviewer": "platform"},
    "web/components": {"owner": "product", "risk": "low", "reviewer": "frontend"},
}

MAX_GENERATION_TOKENS = 60

TRIAGE_KEYS = ("owner", "risk", "reviewer")


def deterministic_triage(text: str) -> dict:
    """Resolve hard policy from changed paths, or abstain on unknown/ambiguous input."""
    matched = [(prefix, labels) for prefix, labels in LABELS.items() if f"/{prefix}/" in text]
    unique = {tuple(labels.items()) for _, labels in matched}
    if not matched:
        return {"resolved": False, "reason": "no supported policy path found", "result": None}
    if len(unique) != 1:
        return {"resolved": False, "reason": "change spans conflicting policy domains", "result": None}
    prefix, labels = matched[0]
    return {"resolved": True, "reason": f"deterministic path policy matched {prefix}",
            "result": labels, "policy_path": prefix}


def validate_triage_output(text: str, source: str) -> dict[str, Any]:
    """Validate compact JSON against the policy implied by the source diff."""
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {"valid": False, "reason": "output is not valid JSON", "classification": None}
    if not isinstance(parsed, dict):
        return {"valid": False, "reason": "output must be one JSON object", "classification": None}
    if tuple(parsed) != TRIAGE_KEYS:
        return {
            "valid": False,
            "reason": "output must contain exactly owner, risk, reviewer in that order",
            "classification": parsed,
        }
    if not all(isinstance(parsed[key], str) for key in TRIAGE_KEYS):
        return {
            "valid": False,
            "reason": "owner, risk, and reviewer must be strings",
            "classification": parsed,
        }
    policy = deterministic_triage(source)
    if not policy["resolved"]:
        return {
            "valid": False,
            "reason": f"classification cannot be validated: {policy['reason']}",
            "classification": parsed,
        }
    if parsed != policy["result"]:
        return {
            "valid": False,
            "reason": f"classification does not match company policy for {policy['policy_path']}",
            "classification": parsed,
            "policy_path": policy["policy_path"],
        }
    return {
        "valid": True,
        "reason": f"classification matches company policy for {policy['policy_path']}",
        "classification": parsed,
        "policy_path": policy["policy_path"],
    }
