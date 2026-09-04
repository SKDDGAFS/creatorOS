# Strategy recommendations

CreatorOS recommendations are evidence-scored proposals, not autonomous
actions. Creating one requires a workspace growth-signal profile and one or
more unique metric observations. The existing configurable weights determine
confidence from coverage, minimum/full sample thresholds, and source quality.

Each recommendation records the proposed action, rationale, supporting metric
rows, total sample size, confidence, expected effect, uncertainty, expected
impact, effort, risk, a goal label, and status. Evidence can optionally link to
a workspace research finding. Cross-workspace profiles and findings are
rejected.

The lifecycle is `proposed -> accepted -> in_progress -> completed`, with
`dismissed` available before completion. Results can be attached only while a
recommendation is in progress or completed. A result records metric, baseline,
observed value, sample size, measurement window, author, and notes.

Outcome evaluation calculates sample-weighted relative change for non-zero
baselines and tempers recommendation confidence by observed sample volume. It
returns `supported`, `inconclusive`, or `not_supported`; those labels describe
association only and never prove causation. Validation rejects common absolute
causal claims, and every API response repeats the correlational warning.

The goal label is intentionally textual in Sprint O. Sprint P will introduce
first-class goals and migrate this link without inventing a goal record.

```text
POST /api/recommendations
GET  /api/recommendations
GET  /api/recommendations/{id}
POST /api/recommendations/{id}/status
POST /api/recommendations/{id}/results
POST /api/recommendations/{id}/evaluate
```

All writes require CSRF and workspace write access. Reads, evidence joins,
scoring profiles, results, and evaluations are workspace scoped. The engine
does not publish, contact a platform, or require an AI/API key.
