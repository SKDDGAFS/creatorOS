# Research worker

CreatorOS research is local-first and evidence-bound. It does not crawl sites,
bypass access controls, evade platform rules, or require a paid API key. Users
and trusted official-platform adapters register small, dated evidence excerpts;
the worker analyzes those records through the existing AI router, including the
free local Ollama path.

## Source policy

Sources are classified as `official_api`, `public_web`, `first_party`, or
`manual`. Public-web and official-API records require a credential-free HTTPS
evidence link. CreatorOS stores the submitted excerpt, source date, retrieval
time, publisher, small metadata object, freshness window, and content hash. It
does not fetch the URL.

Duplicate source content is reused within a workspace. Source excerpts are
limited to 5,000 characters; a run accepts at most ten sources. A source becomes
stale after its configured window. Scheduling rejects stale evidence unless the
caller explicitly sets `include_stale_sources=true`, and the resulting run and
findings retain their freshness state.

## Prompt-injection boundary

The required `research.analyze` prompt must include `{safety_contract}` in the
system template and `{objective}`, `{sources_json}`, and `{competitors_json}` in
the user template. The worker labels every excerpt and competitor note as
untrusted data. The safety contract says
to ignore embedded instructions, use only approved source IDs, distinguish
evidence from inference, and never browse, publish, message, or run commands.

Model output must satisfy `ResearchOutput`. Every finding has one or more
evidence records, and every finding, hook, and content idea may cite only source
IDs captured by that run. An invented or cross-run citation fails the run and
persists no research artifact.

## Results and deduplication

The worker creates:

- trend and content-pattern findings with confidence, source date, freshness,
  and direct evidence links;
- candidate hooks with rationale, confidence, and source IDs;
- content ideas with suggested platforms, optional hook, confidence, and
  source IDs.

Normalized fingerprints deduplicate exact repeated artifacts per workspace.
Records keep first-seen and last-seen run IDs/timestamps, so repeated evidence
strengthens history without producing duplicate rows.

## API

```text
POST /api/research/sources
GET  /api/research/sources
POST /api/research/competitors
GET  /api/research/competitors
POST /api/research/runs
GET  /api/research/runs
GET  /api/research/runs/{run_id}
POST /api/research/runs/{run_id}/cancel
GET  /api/research/findings
GET  /api/research/hooks
GET  /api/research/content-ideas
```

Writes require a writable workspace membership and CSRF validation. Run
scheduling additionally requires an `Idempotency-Key`; cancellation requires an
owner or administrator. Every read and model join is scoped to the active
workspace.

The worker process registers `register_research_jobs` with the shared durable
job registry. Tests use a deterministic fake provider and make no network or
platform calls.
