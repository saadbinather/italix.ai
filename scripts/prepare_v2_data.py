"""Create ignored Step 4 data with the explicit system contract and no test set."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from italix.pr_summary import SYSTEM_PROMPT

SOURCE = Path("data")
DESTINATION = Path("artifacts/v2_data")
DESTINATION.mkdir(parents=True, exist_ok=True)


def evidence_only_target(content: str) -> str:
    """Replace unsupported test claims while preserving the approved summary."""
    before, separator, remainder = content.partition("## Testing")
    if not separator:
        raise ValueError("approved target is missing ## Testing")
    _, risk_separator, risk = remainder.partition("## Risk")
    if not risk_separator:
        raise ValueError("approved target is missing ## Risk")
    return f"{before}## Testing\n- Not run (not shown in diff).\n## Risk{risk}"

for split in ("train", "valid"):
    output = []
    source_lines = (SOURCE / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    if split == "train":
        source_lines += (SOURCE / "step4_extra_train.jsonl").read_text(encoding="utf-8").splitlines()
        source_lines += (SOURCE / "step4_redaction_train.jsonl").read_text(encoding="utf-8").splitlines()
    for line in source_lines:
        record = json.loads(line)
        record["messages"].insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        record["messages"][-1]["content"] = evidence_only_target(
            record["messages"][-1]["content"]
        )
        output.append(json.dumps(record, ensure_ascii=False))
    (DESTINATION / f"{split}.jsonl").write_text(
        "\n".join(output) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(output)} {split} examples")

assert not (DESTINATION / "test.jsonl").exists()
print("No test split was staged.")
