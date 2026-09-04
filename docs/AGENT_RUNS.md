# Agent runs

CreatorOS agents are durable, bounded recommendation jobs. They use the AI
router and therefore work with a free local Ollama provider; paid API keys are
not required for basic local development.

## Capability boundary

The registry exposes five closed capabilities: `content_strategist`,
`copywriter`, `social_planner`, `video_analyst`, and `token_optimizer`. Every
capability is `recommendations_only`. Registry validation rejects any entry
that can publish or execute a shell command.

An agent run records its workspace, requester, objective, typed input
references, exact prompt-version ID, durable-job ID, selected model, lifecycle
timestamps, estimated cost, validated output, overall confidence, safe errors,
and activity events. References may identify a channel, video, or platform
connection and must resolve inside the active workspace. Imported references
are serialized as data; they do not grant tools or change permissions.

All agents return the same strict structure:

- a summary;
- one to twenty recommendations with rationale and confidence;
- optional assumptions and next steps;
- an overall confidence from zero to one.

Output is advisory. A successful run does not create, approve, schedule, or
publish a platform action.

## Prompt setup

Create an active prompt whose name matches the capability:

```text
agent.content_strategist
agent.copywriter
agent.social_planner
agent.video_analyst
agent.token_optimizer
```

Templates may use only these bounded fields:

```text
{agent_type}
{objective}
{input_references}
{output_contract}
```

Scheduling captures the active prompt version. If a newer version is created
before the worker starts, the run still executes the captured version.

## API and worker

`POST /api/agent-runs` requires write access, CSRF validation, and an
`Idempotency-Key` header. Reads are workspace scoped. Cancellation requires an
owner or administrator. `GET /api/agent-runs/capabilities` describes the
registry without executing a model.

The worker process creates a `JobRegistry`, calls `register_agent_jobs`, and
then uses the existing durable `run_once` loop. Durable payloads contain the
bounded run request and no credentials. Provider errors are normalized before
they reach run, job, or activity records.

Tests use deterministic fake providers. No real model, account, publishing
endpoint, or paid API is contacted.
