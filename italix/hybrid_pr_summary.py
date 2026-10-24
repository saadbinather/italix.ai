"""Evidence-first PR summaries with bounded local-model wording.

This module is intentionally separate from adapter qualification and routing.
It extracts literal diff facts, lets the existing local engine propose one
bounded summary sentence, and falls back to deterministic rendering whenever
that wording cannot be proven safe.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import time
from typing import Any

from italix.engines import Engine
from italix.evaluation import (
    HEADINGS,
    invented_code_identifiers,
    invented_rename_claims,
    repetition_ratio,
    unsupported_behavior_claims,
)


HYBRID_PROMPT = """You write one short PR-summary sentence from verified facts.
Return exactly one plain sentence. Use only facts and exact identifiers present
in the JSON. Do not infer tests, risk, motivation, impact, safety, or behavior.
Do not mention a rename unless it appears in explicit_renames."""

GENERIC_WORDS = {
    "add", "added", "and", "change", "changes", "constant", "constants",
    "fallback", "fallbacks", "file", "files", "from", "identifier",
    "identifiers", "in", "remove", "removed", "rename", "renames", "to",
    "update", "updates", "use", "uses", "value", "values", "with",
}


@dataclass(frozen=True)
class Rename:
    before: str
    after: str


@dataclass(frozen=True)
class ConstantChange:
    name: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class FileFacts:
    path: str
    previous_path: str | None
    metadata_rename: Rename | None
    added_identifiers: tuple[str, ...]
    removed_identifiers: tuple[str, ...]
    added_numeric_values: tuple[str, ...]
    removed_numeric_values: tuple[str, ...]
    explicit_renames: tuple[Rename, ...]
    constants: tuple[ConstantChange, ...]
    fallback_values: tuple[str, ...]
    test_code_added: bool
    abstention_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DiffFacts:
    files: tuple[str, ...]
    added_lines: tuple[str, ...]
    removed_lines: tuple[str, ...]
    added_identifiers: tuple[str, ...]
    removed_identifiers: tuple[str, ...]
    added_numeric_values: tuple[str, ...]
    removed_numeric_values: tuple[str, ...]
    explicit_renames: tuple[Rename, ...]
    constants: tuple[ConstantChange, ...]
    fallback_values: tuple[str, ...]
    uncertain_behavior: bool
    file_facts: tuple[FileFacts, ...]
    tests_added: tuple[str, ...]
    abstention_reasons: tuple[str, ...]

    def structured(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HybridResult:
    summary: str
    facts: DiffFacts
    generated_wording: str | None
    used_fallback: bool
    validation: dict[str, Any]
    latency_ms: float
    model: str


_DECLARATION_PATTERNS = (
    re.compile(r"\b(?:def|function)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)"),
)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGNMENT = re.compile(
    r"(?:\b(?:const|let|var)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*([^,;}]+)"
)
_WORDS_IGNORED = {
    "def", "end", "export", "false", "func", "function", "int", "return",
    "string", "true", "const", "let", "var", "or", "and", "assert",
}

_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")


def _changed_lines(diff: str, prefix: str) -> tuple[str, ...]:
    header = "+++" if prefix == "+" else "---"
    return tuple(
        line[1:].strip()
        for line in diff.splitlines()
        if line.startswith(prefix) and not line.startswith(header) and line[1:].strip()
    )


def _code_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Exclude comment/prose-only lines from code fact extraction."""
    return tuple(line for line in lines if not line.lstrip().startswith(_COMMENT_PREFIXES))


def _declaration(line: str) -> str | None:
    for pattern in _DECLARATION_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None


def _identifiers(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({
        value for line in lines for value in _IDENTIFIER.findall(line)
        if value.lower() not in _WORDS_IGNORED
    }))


def _constant_map(lines: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        for match in _ASSIGNMENT.finditer(line):
            values[match.group(1)] = match.group(2).strip()
    compact = " ".join(lines)
    for match in re.finditer(
        r"\b([A-Z][A-Z0-9_]*)\s*=\s*\(\s*(['\"]?[^()\s,;]+['\"]?)\s*\)", compact
    ):
        values[match.group(1)] = match.group(2)
    return values


def _numeric_values(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({value for line in lines for value in re.findall(r"\b\d+(?:\.\d+)?\b", line)}))


def _fallbacks(added: tuple[str, ...]) -> tuple[str, ...]:
    values: set[str] = set()
    text = " ".join(added)
    patterns = (
        r"\b(?:fetch|get)\([^,]+,\s*[^)]*?(?:\[['\"]([^'\"]+)['\"]\]|['\"]([^'\"]+)['\"])",
        r"(?:\?\?|\bor\b)\s*.*?(?:\[['\"]([^'\"]+)['\"]\]|['\"]([^'\"]+)['\"])",
        r"\b(?:Coalesce|FirstNonEmpty)\([^,]+,\s*[^)]*?(?:\[['\"]([^'\"]+)['\"]\]|['\"]([^'\"]+)['\"])",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            values.update(value for value in match.groups() if value)
    return tuple(sorted(values))


def _diff_blocks(diff: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"^diff --git ", diff, re.MULTILINE)]
    return [diff[start : starts[index + 1] if index + 1 < len(starts) else len(diff)]
            for index, start in enumerate(starts)]


def _file_facts(block: str) -> FileFacts:
    header = re.search(r"^diff --git a/(\S+) b/(\S+)$", block, re.MULTILINE)
    previous_path, path = (header.group(1), header.group(2)) if header else (None, "unknown")
    rename_from = re.search(r"^rename from (.+)$", block, re.MULTILINE)
    rename_to = re.search(r"^rename to (.+)$", block, re.MULTILINE)
    metadata_rename = (
        Rename(rename_from.group(1), rename_to.group(1))
        if rename_from and rename_to else None
    )
    raw_added, raw_removed = _changed_lines(block, "+"), _changed_lines(block, "-")
    added, removed = _code_lines(raw_added), _code_lines(raw_removed)
    added_declarations = [name for line in added if (name := _declaration(line))]
    removed_declarations = [name for line in removed if (name := _declaration(line))]
    renames: list[Rename] = []
    if len(added_declarations) == 1 and len(removed_declarations) == 1:
        before, after = removed_declarations[0], added_declarations[0]
        if before != after:
            renames.append(Rename(before, after))
    before_constants, after_constants = _constant_map(removed), _constant_map(added)
    constants = tuple(
        ConstantChange(name, before_constants.get(name), after_constants.get(name))
        for name in sorted(before_constants.keys() | after_constants.keys())
    )
    fallbacks = _fallbacks(added)
    test_path = bool(re.search(r"(?:^|/)(?:tests?|specs?)(?:/|$)|(?:^|/)test_[^/]+$|_test\.", path))
    test_code = test_path and bool(added)
    reasons: list[str] = []
    if "Binary files " in block or "GIT binary patch" in block:
        reasons.append("binary content is not inspected")
    if (raw_added or raw_removed) and not (added or removed):
        reasons.append("comment-only change has no verified runtime behavior")
    supported = bool(metadata_rename or renames or constants or fallbacks or added or removed)
    if not supported and not reasons:
        reasons.append("no supported textual code facts were extracted")
    return FileFacts(
        path=path,
        previous_path=previous_path if previous_path != path else None,
        metadata_rename=metadata_rename,
        added_identifiers=_identifiers(added),
        removed_identifiers=_identifiers(removed),
        added_numeric_values=_numeric_values(added),
        removed_numeric_values=_numeric_values(removed),
        explicit_renames=tuple(renames),
        constants=constants,
        fallback_values=fallbacks,
        test_code_added=test_code,
        abstention_reasons=tuple(dict.fromkeys(reasons)),
    )


def extract_diff_facts(diff: str) -> DiffFacts:
    per_file = tuple(_file_facts(block) for block in _diff_blocks(diff))
    files = tuple(item.path for item in per_file)
    added = _changed_lines(diff, "+")
    removed = _changed_lines(diff, "-")
    code_added, code_removed = _code_lines(added), _code_lines(removed)
    renames = tuple(rename for item in per_file for rename in item.explicit_renames)
    constants = tuple(change for item in per_file for change in item.constants)
    fallbacks = tuple(sorted({value for item in per_file for value in item.fallback_values}))
    reasons = tuple(reason for item in per_file for reason in item.abstention_reasons)
    return DiffFacts(
        files=files,
        added_lines=added,
        removed_lines=removed,
        added_identifiers=_identifiers(code_added),
        removed_identifiers=_identifiers(code_removed),
        added_numeric_values=_numeric_values(code_added),
        removed_numeric_values=_numeric_values(code_removed),
        explicit_renames=renames,
        constants=constants,
        fallback_values=fallbacks,
        uncertain_behavior=bool(reasons) or not bool(renames or constants or fallbacks),
        file_facts=per_file,
        tests_added=tuple(item.path for item in per_file if item.test_code_added),
        abstention_reasons=tuple(dict.fromkeys(reasons)),
    )


def _changes(facts: DiffFacts) -> list[str]:
    bullets: list[str] = []
    multiple = len(facts.file_facts) > 1
    for file in facts.file_facts:
        prefix = f"{file.path}: " if multiple else ""
        if file.metadata_rename:
            bullets.append(
                f"Rename file {file.metadata_rename.before} to {file.metadata_rename.after}."
            )
        for rename in file.explicit_renames:
            bullets.append(f"{prefix}Rename {rename.before} to {rename.after}.")
        for item in file.constants:
            if item.before is not None and item.after is not None:
                bullets.append(f"{prefix}Set {item.name} to {item.after} instead of {item.before}.")
            elif item.after is not None:
                bullets.append(f"{prefix}Add {item.name} with value {item.after}.")
            else:
                bullets.append(f"{prefix}Remove {item.name} with previous value {item.before}.")
        if file.fallback_values:
            bullets.append(
                f"{prefix}Use explicit fallback value(s): {', '.join(file.fallback_values)}."
            )
        described_names = {x.before for x in file.explicit_renames} | {
            x.after for x in file.explicit_renames
        } | {x.name for x in file.constants}
        identifiers = [x for x in file.added_identifiers if x not in described_names]
        if identifiers:
            bullets.append(f"{prefix}Added code identifiers: {', '.join(identifiers)}.")
        removed_identifiers = [x for x in file.removed_identifiers if x not in described_names]
        if removed_identifiers:
            bullets.append(f"{prefix}Removed code identifiers: {', '.join(removed_identifiers)}.")
        if file.added_numeric_values and not file.constants:
            bullets.append(f"{prefix}Added numeric values: {', '.join(file.added_numeric_values)}.")
        if file.removed_numeric_values and not file.constants:
            bullets.append(f"{prefix}Removed numeric values: {', '.join(file.removed_numeric_values)}.")
        for reason in file.abstention_reasons:
            bullets.append(f"{prefix}Semantic interpretation abstained: {reason}.")
    if not bullets:
        bullets.append("Semantic interpretation abstained: no supported facts were extracted.")
    return bullets


def deterministic_summary(facts: DiffFacts, wording: str | None = None) -> str:
    files = ", ".join(facts.files) if facts.files else "the changed file"
    if wording:
        summary = wording
    elif facts.abstention_reasons:
        summary = f"Report verified metadata for {files}; unsupported details are explicitly omitted."
    elif len(facts.files) == 1:
        summary = f"Summarize verified changes in {files} without inferring behavior."
    else:
        summary = f"Summarize verified changes in {len(facts.files)} files without mixing file-specific facts."
    bullets = "\n".join(f"- {item}" for item in _changes(facts))
    testing = (
        "- Test code added in " + ", ".join(facts.tests_added) + "; execution not shown."
        if facts.tests_added else "- Not run (not shown in diff)."
    )
    return (
        f"## Summary\n{summary}\n## Changes\n{bullets}\n"
        f"## Testing\n{testing}\n"
        "## Risk\nReview required — risk level cannot be verified from the diff."
    )


def validate_hybrid(summary: str, facts: DiffFacts, diff: str) -> dict[str, Any]:
    counts = {heading: summary.count(heading) for heading in HEADINGS}
    positions = [summary.find(heading) for heading in HEADINGS]
    format_ok = all(value == 1 for value in counts.values()) and positions == sorted(positions)
    testing = summary.partition("## Testing")[2].partition("## Risk")[0].strip()
    expected_testing = (
        "- Test code added in " + ", ".join(facts.tests_added) + "; execution not shown."
        if facts.tests_added else "- Not run (not shown in diff)."
    )
    lowered = summary.lower()
    required = {
        value.lower()
        for value in (*facts.added_identifiers, *facts.added_numeric_values)
    }
    identifier_consistent = all(value in lowered for value in required)
    fallback_consistent = all(value.lower() in lowered for value in facts.fallback_values)
    rename_errors = invented_rename_claims(summary, "", diff)
    identifier_errors = invented_code_identifiers(summary, "", diff)
    behavior_errors = unsupported_behavior_claims(summary, "", diff)
    contradiction_errors = []
    if re.search(r"\btests? (?:passed|ran|were run)\b", lowered):
        contradiction_errors.append("unsupported test claim")
    if "no new code" in lowered and facts.added_lines:
        contradiction_errors.append("denies added code")
    if "no code removed" in lowered and facts.removed_lines:
        contradiction_errors.append("denies removed code")
    repeated = repetition_ratio(summary)
    valid = (
        format_ok and testing == expected_testing
        and identifier_consistent and fallback_consistent and repeated <= 0.12
        and not rename_errors and not identifier_errors and not behavior_errors
        and not contradiction_errors
    )
    return {
        "valid": valid,
        "format_ok": format_ok,
        "testing_ok": testing == expected_testing,
        "identifier_consistent": identifier_consistent,
        "fallback_consistent": fallback_consistent,
        "repetition_ratio": repeated,
        "invented_rename_claims": rename_errors,
        "invented_identifiers": identifier_errors,
        "unsupported_behavior_claims": behavior_errors,
        "factual_contradictions": contradiction_errors,
    }


def _wording_supported(wording: str, facts: DiffFacts) -> bool:
    if not wording or "\n" in wording or len(wording) > 240:
        return False
    evidence = " ".join((*facts.files, *facts.added_lines, *facts.removed_lines)).lower()
    allowed = set(re.findall(r"[a-z0-9_]+", evidence)) | GENERIC_WORDS
    content = set(re.findall(r"[a-z0-9_]+", wording.lower()))
    return content <= allowed and not re.search(
        r"\b(?:test|risk|safe|secure|improve|ensure|because|impact|support)\w*\b",
        wording,
        re.IGNORECASE,
    )


class HybridPRSummarizer:
    def __init__(self, engine: Engine):
        self.engine = engine

    def summarize(self, diff: str) -> HybridResult:
        started = time.perf_counter()
        facts = extract_diff_facts(diff)
        generation = self.engine.generate(
            [
                {"role": "system", "content": HYBRID_PROMPT},
                {"role": "user", "content": json.dumps(facts.structured(), sort_keys=True)},
            ],
            max_tokens=48,
            temperature=0.0,
            adapter_path=None,
        )
        wording = generation.text.strip()
        candidate = deterministic_summary(facts, wording if _wording_supported(wording, facts) else None)
        validation = validate_hybrid(candidate, facts, diff)
        used_fallback = not _wording_supported(wording, facts) or not validation["valid"]
        if not validation["valid"]:
            candidate = deterministic_summary(facts)
            validation = validate_hybrid(candidate, facts, diff)
        return HybridResult(
            summary=candidate,
            facts=facts,
            generated_wording=wording,
            used_fallback=used_fallback,
            validation=validation,
            latency_ms=(time.perf_counter() - started) * 1000,
            model=generation.model,
        )
