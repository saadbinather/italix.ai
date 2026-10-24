# `adapter-v3` PR-summary failure analysis

## Conclusion

`adapter-v3` is correctly marked `experimental_failed`. On the frozen six-case `pr_summary` validation split, it passed 4/6 cases while the base model with the production scaffold passed 5/6. The qualification gate requires the candidate to pass every case and outperform the scaffold baseline, so `adapter-v3` satisfies neither condition.

The candidate failed cases 2 and 4:

| Case | File | Candidate result | Scaffold result | Decisive gate failure |
|---|---|---:|---:|---|
| 2 | `logs/redact.ts` | Fail | Fail | Unsupported claim: `renamed` |
| 4 | `links/target.rb` | Fail | Pass | Repetition ratio `0.1867` exceeds `0.12` |

All other candidate cases passed. Evaluation used deterministic generation with 160 maximum tokens, temperature 0, repetition penalty 1.05, minimum content recall 0.32, minimum identifier recall 0.60, and the exact testing line `- Not run (not shown in diff).`

## Failed case 2: log-field redaction

### Input diff

```diff
diff --git a/logs/redact.ts b/logs/redact.ts
--- a/logs/redact.ts
+++ b/logs/redact.ts
@@ -5,2 +5,3 @@ export function redact(data) {
+  return omit(data, ['session_id', 'device_id']);
 }
```

### Expected output

```markdown
## Summary
Remove device identifiers from log data.
## Changes
- Omit session_id and device_id from returned log data.
## Testing
- Not run (not shown in diff).
## Risk
Low — logs no longer include the named device identifiers.
```

### `adapter-v3` output

```markdown
## Summary
- Update the `redact` function to remove sensitive fields from the data object.

## Changes
- Renamed the `redact` function to `omit`.
- Added a new field `['session_id', 'device_id']` to be omitted from the data.
- The updated code is now more concise and follows best practices.

## Testing
- Not run (not shown in diff).

## Risk
- Low: This change is straightforward and aligns with security best practices.
```

### Scoring evidence

- Format: pass
- Testing statement: pass
- Content recall: `0.60` (minimum `0.32`)
- Identifier recall: `1.00` (`session_id`, `device_id` both present)
- Repetition ratio: `0.0169` (maximum `0.12`)
- Unsupported phrase: `renamed`
- Overall: fail

### Root cause

The response misread a function call as a function rename. The added line calls `omit(...)` from inside the existing `redact` function; it does not rename `redact`. It also describes the identifiers as a “new field,” although they are keys being omitted, and adds unsupported quality language (“more concise” and “best practices”).

The scaffold baseline produced the same response and failed the same gate. This indicates the selected adapter did not correct an existing scaffold-conditioned hallucination pattern. The model preserved names well but did not preserve the syntactic relationship between the enclosing function and the called helper.

## Failed case 4: target fallback

### Input diff

```diff
diff --git a/links/target.rb b/links/target.rb
--- a/links/target.rb
+++ b/links/target.rb
@@ -4,2 +4,3 @@ def target(name)
+  TARGETS.fetch(name, TARGETS['overview'])
 end
```

### Expected output

```markdown
## Summary
Use the overview target for unknown link names.
## Changes
- Resolve known names from TARGETS.
- Fall back to TARGETS['overview'] when a name is unknown.
## Testing
- Not run (not shown in diff).
## Risk
Low — unsupported links now open the overview target.
```

### `adapter-v3` output

```markdown
## Summary
- Added a fallback value to the `TARGETS` hash in `target.rb`.
+ Corrected the `TARGETS` hash to use `fetch` instead of `merge!`, ensuring that
+ `name` is not `nil` or undefined.

## Changes
- Updated the `TARGETS` hash to use `fetch` instead of `merge!`.
+ Ensured that `name` is not `nil` or undefined by using `fetch`.

## Testing
- Not run (not shown in diff).

## Risk
- Low
- This change ensures that `name` is not `nil` or undefined, which is a small but necessary improvement.
```

### Scoring evidence

- Format: pass
- Testing statement: pass
- Content recall: `0.4783` (minimum `0.32`)
- Identifier recall: `0.6667` (hits `fetch` and `targets`; misses `overview`)
- Repetition ratio: `0.1867` (maximum `0.12`)
- Unsupported-phrase hits recorded by evaluator: none
- Overall: fail

### Root cause

The immediate scored failure is excessive repetition: the response repeats the same `fetch`/`merge!` and nil-check claims across Summary, Changes, and Risk. The stray leading `+` markers also make the answer look like a generated patch instead of a summary.

The deeper semantic failure is worse than the recorded gate suggests. The diff contains no `merge!`, does not establish a nil/undefined guard, and explicitly supplies `TARGETS['overview']` as the fallback. The response invents the first two behaviors and fails to state the actual fallback precisely. It barely passes identifier recall because two of three identifiers are present, even though the omitted identifier—`overview`—is the central behavior.

The scaffold baseline passed this case with a repetition ratio of `0.1039` and identifier recall of `0.6667`, despite also mentioning unsupported `merge!` and nil/undefined behavior. This exposes an evaluator blind spot: the fixed unsupported-phrase list detects `renamed` but does not include `merge!`, nil/undefined claims, or stray diff markers. `adapter-v3` was rejected by the repetition gate, but the scaffold's nominal pass should not be interpreted as a semantically clean answer.

## Cross-case diagnosis

1. **Syntactic-role confusion.** The model confuses calling a helper with renaming a function in case 2.
2. **Unsupported transformation narratives.** It invents prior operations such as `merge!` and claims about nil handling in case 4.
3. **Weak fallback-value fidelity.** The prompt explicitly requires preserving fallback values, yet the candidate omits `overview` from case 4.
4. **Verbose template leakage.** Repeated “corrected,” “ensuring,” and generic quality/risk language increases repetition without adding diff-grounded facts.
5. **Incomplete automated hallucination coverage.** The evaluator catches a small fixed set of unsupported phrases. It correctly rejects both candidate failures, but case 4 demonstrates that a response can contain material hallucinations not represented in `unsupported_hits`.

## Qualification decision

The failure status should remain unchanged:

- Candidate: 4/6
- Scaffold baseline: 5/6
- Required: candidate passes 6/6 and exceeds the scaffold
- Result: not qualified; `adapter-v3` must remain undeployable

This audit does not recommend changing the recorded score. It explains why the two failures are real and why case 4's semantic problems are broader than its decisive repetition metric.
