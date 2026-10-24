"""Reproducible server-side PR-summary evaluation and qualification gates."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from italix.engines import cached_qwen_path
from italix.pr_summary import SYSTEM_PROMPT
from italix.change_triage import COMPACT_PROMPT, MAX_GENERATION_TOKENS as TRIAGE_TOKENS, PRODUCTION_PROMPT

HEADINGS = ("## Summary", "## Changes", "## Testing", "## Risk")
MAX_TOKENS = 160
REPETITION_LIMIT = 0.12
MIN_CONTENT_RECALL = 0.32
MIN_IDENTIFIER_RECALL = 0.60
STOPWORDS = {
    "add", "added", "and", "are", "before", "behavior", "change", "changes",
    "configured", "existing", "for", "from", "into", "not", "only", "other",
    "return", "returns", "the", "their", "this", "when", "with", "without",
}
CODE_STOPWORDS = {
    "def", "function", "export", "return", "if", "else", "true", "false", "const",
    "let", "var", "string", "int", "bool", "end", "func",
}
UNSUPPORTED_PHRASES = (
    "renamed",
    "updated import",
    "without any sanitization",
    "tests passed",
    "verified with",
)
UNSUPPORTED_BEHAVIOR_PHRASES = (
    "best practices",
    "more concise",
    "nil or undefined",
)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def content_words(text: str) -> set[str]:
    return {word for word in words(text) if len(word) > 2 and word not in STOPWORDS}


def repetition_ratio(text: str, size: int = 4) -> float:
    sequence = words(text)
    ngrams = [tuple(sequence[i : i + size]) for i in range(len(sequence) - size + 1)]
    if not ngrams:
        return 0.0
    counts = Counter(ngrams)
    return sum(count - 1 for count in counts.values() if count > 1) / len(ngrams)


def salient_identifiers(diff: str) -> set[str]:
    additions = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+", additions))
    salient = {
        token.lower()
        for token in tokens
        if token.lower() not in CODE_STOPWORDS
        and ("_" in token or token.isupper() or token.isdigit() or len(token) >= 5)
    }
    return salient


def _normalized_identifier(value: str) -> str:
    return value.lower().rstrip("!?")


def invented_rename_claims(response: str, target: str, diff: str) -> list[dict[str, str]]:
    """Find rename claims without a matching remove/add rename in the evidence."""
    removed = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")
    ).lower()
    added = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    ).lower()
    claims = []
    pattern = re.compile(
        r"\brenam\w*[^`\n]*`([^`]+)`[^.\n]*?\bto\s+`([^`]+)`", re.IGNORECASE
    )
    for match in pattern.finditer(response):
        source, destination = match.group(1), match.group(2)
        supported = (
            "renam" in target.lower()
            or (_normalized_identifier(source) in removed
                and _normalized_identifier(destination) in added)
        )
        if not supported:
            claims.append({"from": source, "to": destination})
    return claims


def invented_code_identifiers(response: str, target: str, diff: str) -> list[str]:
    """Find simple backticked identifiers absent from both diff and approved target."""
    evidence = {
        _normalized_identifier(token)
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*[!?]?", f"{diff}\n{target}")
    }
    mentioned = {
        token
        for span in re.findall(r"`([^`\n]+)`", response)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*[!?]?", span.strip())
        for token in [span.strip()]
    }
    return sorted(token for token in mentioned if _normalized_identifier(token) not in evidence)


def unsupported_behavior_claims(response: str, target: str, diff: str) -> list[str]:
    evidence = f"{diff}\n{target}".lower().replace("`", "")
    lowered = response.lower().replace("`", "")
    claims = [
        phrase for phrase in UNSUPPORTED_BEHAVIOR_PHRASES
        if phrase in lowered and phrase not in evidence
    ]
    for prior in re.findall(r"\binstead of\s+`([^`]+)`", response, re.IGNORECASE):
        claim = f"replacement of nonexistent `{prior}`"
        if _normalized_identifier(prior) not in evidence and claim not in claims:
            claims.append(claim)
    return claims


def required_fallback_values(diff: str) -> set[str]:
    additions = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    values = set()
    for match in re.finditer(
        r"\b(?:fetch|get)\([^,\n]+,\s*[^)\n]*?['\"]([^'\"]+)['\"]", additions
    ):
        values.add(match.group(1).lower())
    return values


def score_response(response: str, target: str, diff: str) -> dict[str, Any]:
    heading_counts = {heading: response.count(heading) for heading in HEADINGS}
    positions = [response.find(heading) for heading in HEADINGS]
    format_ok = all(value == 1 for value in heading_counts.values()) and positions == sorted(positions)
    repeated = repetition_ratio(response)
    testing_section = response.partition("## Testing")[2].partition("## Risk")[0].strip()
    testing_ok = testing_section == "- Not run (not shown in diff)."
    target_tokens = content_words(target)
    response_tokens = content_words(response)
    content_recall = len(target_tokens & response_tokens) / len(target_tokens)
    identifiers = salient_identifiers(diff)
    lowered = response.lower()
    identifier_hits = {identifier for identifier in identifiers if identifier in lowered}
    identifier_recall = len(identifier_hits) / len(identifiers) if identifiers else 1.0
    unsupported_hits = [
        phrase for phrase in UNSUPPORTED_PHRASES if phrase in lowered and phrase not in target.lower()
    ]
    rename_claims = invented_rename_claims(response, target, diff)
    invented_identifiers = invented_code_identifiers(response, target, diff)
    behavior_claims = unsupported_behavior_claims(response, target, diff)
    fallback_values = required_fallback_values(diff)
    missing_fallbacks = sorted(value for value in fallback_values if value not in lowered)
    passed = (
        format_ok
        and repeated <= REPETITION_LIMIT
        and testing_ok
        and content_recall >= MIN_CONTENT_RECALL
        and identifier_recall >= MIN_IDENTIFIER_RECALL
        and not unsupported_hits
        and not rename_claims
        and not invented_identifiers
        and not behavior_claims
        and not missing_fallbacks
    )
    return {
        "passed": passed,
        "format_ok": format_ok,
        "heading_counts": heading_counts,
        "repetition_ratio": repeated,
        "testing_ok": testing_ok,
        "content_recall": content_recall,
        "required_identifiers": sorted(identifiers),
        "identifier_hits": sorted(identifier_hits),
        "identifier_recall": identifier_recall,
        "unsupported_hits": unsupported_hits,
        "invented_rename_claims": rename_claims,
        "invented_identifiers": invented_identifiers,
        "unsupported_behavior_claims": behavior_claims,
        "required_fallback_values": sorted(fallback_values),
        "missing_fallback_values": missing_fallbacks,
    }


class ServerEvaluator:
    def __init__(self, root: str | Path | None = None, *, allow_holdout: bool = False):
        self.root = Path(root or Path(__file__).resolve().parents[1])
        self.allow_holdout = allow_holdout

    def _candidate(self, name: str, adapter_path: str | None, rows: list[dict], scaffold: bool) -> dict:
        import mlx.core as mx
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_logits_processors, make_sampler

        model, tokenizer = load(str(cached_qwen_path()), adapter_path=adapter_path)
        sampler = make_sampler(temp=0.0)
        processors = make_logits_processors(repetition_penalty=1.05, repetition_context_size=64)
        results = []
        for index, row in enumerate(rows, 1):
            user = row["messages"][-2]
            messages = ([{"role": "system", "content": SYSTEM_PROMPT}] if scaffold else []) + [user]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            response = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=MAX_TOKENS,
                sampler=sampler,
                logits_processors=processors,
                verbose=False,
            ).strip()
            target = row["messages"][-1]["content"]
            result = score_response(response, target, user["content"])
            result.update({"index": index, "response": response})
            results.append(result)
        del model, tokenizer
        mx.clear_cache()
        return {
            "name": name,
            "adapter_path": adapter_path,
            "scaffold": scaffold,
            "passed": sum(result["passed"] for result in results),
            "total": len(results),
            "examples": results,
        }

    def _compare_pr(self, candidate_path: str, split: str) -> dict[str, Any]:
        if split not in {"valid", "holdout"}:
            raise ValueError("evaluation split must be valid or holdout")
        rows = [
            json.loads(line)
            for line in (self.root / f"data/v3/{split}.jsonl").read_text().splitlines()
        ]
        candidates = [
            self._candidate("base_raw", None, rows, scaffold=False),
            self._candidate("base_scaffold", None, rows, scaffold=True),
            self._candidate("adapter_v2", str(self.root / "artifacts/adapters/v2"), rows, scaffold=True),
            self._candidate("candidate", str(self.root / candidate_path), rows, scaffold=True),
        ]
        scaffold = next(item for item in candidates if item["name"] == "base_scaffold")
        candidate = next(item for item in candidates if item["name"] == "candidate")
        qualified = candidate["passed"] == candidate["total"] and candidate["passed"] > scaffold["passed"]
        return {
            "split": split,
            "policy": {
                "max_tokens": MAX_TOKENS,
                "temperature": 0.0,
                "repetition_penalty": 1.05,
                "repetition_limit": REPETITION_LIMIT,
                "minimum_content_recall": MIN_CONTENT_RECALL,
                "minimum_identifier_recall": MIN_IDENTIFIER_RECALL,
                "testing_line": "- Not run (not shown in diff).",
            },
            "candidates": candidates,
            "qualified": qualified,
            "qualification_reason": (
                "candidate passed every example and exceeded scaffold baseline"
                if qualified
                else "candidate did not pass every example or did not exceed scaffold baseline"
            ),
        }

    def _triage_candidate(self, name, adapter_path, rows, system_prompt):
        import mlx.core as mx
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler

        model, tokenizer = load(str(cached_qwen_path()), adapter_path=adapter_path)
        results, prompt_tokens = [], []
        for index, row in enumerate(rows, 1):
            messages = [{"role": "system", "content": system_prompt}, row["messages"][-2]]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            prompt_tokens.append(len(tokenizer.encode(prompt)))
            response = generate(model, tokenizer, prompt=prompt, max_tokens=TRIAGE_TOKENS,
                                sampler=make_sampler(temp=0.0), verbose=False).strip()
            expected = row["messages"][-1]["content"]
            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                parsed = None
            target = json.loads(expected)
            fields = {key: bool(isinstance(parsed, dict) and parsed.get(key) == value)
                      for key, value in target.items()}
            passed = response == expected and all(fields.values()) and list(parsed or {}) == list(target)
            results.append({"index": index, "passed": passed, "format_ok": response == expected,
                            "field_accuracy": fields, "response": response, "expected": expected})
        del model, tokenizer
        mx.clear_cache()
        return {"name": name, "adapter_path": adapter_path,
                "passed": sum(item["passed"] for item in results), "total": len(results),
                "average_prompt_tokens": sum(prompt_tokens) / len(prompt_tokens), "examples": results}

    def _compare_triage(self, candidate_path: str, split: str) -> dict[str, Any]:
        rows = [json.loads(line) for line in
                (self.root / f"data/change_triage/{split}.jsonl").read_text().splitlines()]
        candidates = [
            self._triage_candidate("base_compact", None, rows, COMPACT_PROMPT),
            self._triage_candidate("base_production_scaffold", None, rows, PRODUCTION_PROMPT),
            self._triage_candidate("candidate", str(self.root / candidate_path), rows, COMPACT_PROMPT),
        ]
        scaffold, candidate = candidates[1], candidates[2]
        qualified = (candidate["passed"] == candidate["total"]
                     and candidate["passed"] >= scaffold["passed"]
                     and candidate["average_prompt_tokens"] <= scaffold["average_prompt_tokens"] * .40)
        return {"workload": "change_triage", "split": split,
                "policy": {"exact_pass_rate": 1.0, "quality_at_least_scaffold": True,
                           "maximum_prompt_token_ratio": .40},
                "candidates": candidates, "qualified": qualified,
                "qualification_reason": ("candidate passed every exact case, matched or beat the scaffold, and used <=40% prompt tokens"
                                         if qualified else "candidate failed an exact-quality or prompt-efficiency gate")}

    def compare(self, candidate_path: str, *, split: str = "valid", workload: str = "pr_summary") -> dict[str, Any]:
        if split not in {"valid", "holdout"}:
            raise ValueError("evaluation split must be valid or holdout")
        if split == "holdout" and not self.allow_holdout:
            raise PermissionError("sealed holdout evaluation requires an explicitly authorized evaluator")
        if workload == "change_triage":
            return self._compare_triage(candidate_path, split)
        if workload == "pr_summary":
            return self._compare_pr(candidate_path, split)
        raise ValueError(f"unsupported evaluation workload: {workload}")
