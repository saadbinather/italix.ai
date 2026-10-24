# Step 4 quality report

## Diagnosis

MLX-LM 0.30.6 applies the Qwen chat template correctly. With prompt masking,
the loss begins at the assistant response. Training and validation sequences are
167–227 tokens, so the 512-token limit does not truncate any example.

V1's failure came from overfitting 2.64 million adapter parameters to 18 highly
regular examples for 54 steps at a `1e-4` learning rate. A second data problem
was more important for factual quality: approved targets claimed tests that were
not present in their diffs, teaching the model to invent verification.

## Frozen validation gates

Before v2 training, `validation_rubric.json` fixed these requirements:

- all four headings exactly once and in order;
- repeated four-gram ratio no greater than 0.12;
- all example-specific factual concepts present;
- no predefined unsupported claims;
- target content-word recall of at least 0.35.

All comparisons use greedy decoding, 160 generated tokens, repetition penalty
1.05, context size 64, and the same system prompt.

## Attempts

1. A smaller rank-4, four-layer adapter trained for 18 steps at `2e-5`. It
   passed at most one of three validation examples.
2. V1 was refined for nine steps at `1e-5` on evidence-only targets. It passed
   two of three examples but missed required deep-link fallback detail.
3. Twelve training-only fallback examples were added, followed by 12 updates
   from v1. This enabled the deep-link case but exposed weak exact-field recall.
4. Six training-only redaction examples were added, followed by six updates at
   `5e-6`. The selected experimental v2 passes two of three automatic cases.

The selected v2 still fails analytics: it omits the exact `ip_address` identifier
and contradicts itself by saying both that events are sent without sanitization
and that fields are sanitized. It is therefore **not deployable**.

The untouched test split was not used because no candidate passed validation.

## Smallest recommended correction

Add more diverse, independently reviewed diff-to-summary pairs that require
literal identifier retention and distinguish added behavior from removed
behavior. Include explicit negative examples for contradictory summaries. Then
restart from the base model (not v1), use the conservative rank-4 configuration,
and select only on the frozen quality gates. A larger base model is not yet
necessary; the immediate bottleneck is supervised data quality and coverage.
