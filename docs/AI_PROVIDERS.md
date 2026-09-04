# AI providers

CreatorOS can run its basic AI workflows without a paid API key. The default
local option is Ollama on the same computer. OpenAI-compatible servers are an
optional adapter, not a requirement.

No general-purpose “run this prompt” endpoint is exposed to the browser.
Trusted backend workers call the router with a named, versioned prompt and a
Pydantic output model. The router turns that model into JSON Schema and rejects
responses that do not validate.

## Local Ollama setup

1. Install Ollama from its official distribution.
2. Download a model that fits the computer, for example `ollama pull gemma3`.
3. Confirm Ollama is listening on `http://127.0.0.1:11434`.
4. Create a provider configuration through `POST /api/ai/providers`:

```json
{
  "name": "Local Ollama",
  "provider_kind": "ollama",
  "base_url": "http://127.0.0.1:11434",
  "model_name": "gemma3",
  "capability_tier": "lightweight",
  "priority": 100,
  "input_cost_per_million": 0,
  "output_cost_per_million": 0
}
```

Ollama configurations cannot include credentials and use loopback by default.
When the backend runs in Docker and Ollama runs on the host, add the exact host
bridge name (commonly `host.docker.internal`) to
`AI_ALLOWED_LOCAL_PROVIDER_HOSTS` before using its HTTP URL. Model downloads,
RAM, disk space, electricity, and hardware remain the user's responsibility
even though no API bill is involved.

The adapter uses Ollama's non-streaming chat endpoint, sends the required JSON
schema in `format`, and records `prompt_eval_count` and `eval_count` as input and
output usage. See the official [Ollama chat API](https://docs.ollama.com/api/chat)
and [usage fields](https://docs.ollama.com/api/usage).

## Optional OpenAI-compatible servers

The compatible adapter calls `<base_url>/chat/completions`, requests strict JSON
Schema output, and reads standard prompt and completion token counts. It can be
used with a local compatible server or an explicitly approved remote host.

- Loopback HTTP endpoints and names explicitly listed in
  `AI_ALLOWED_LOCAL_PROVIDER_HOSTS` are allowed for local development.
- Remote endpoints must use HTTPS and their hostname must appear in the
  comma-separated `AI_ALLOWED_PROVIDER_HOSTS` setting.
- An optional key is referenced as `env://VARIABLE_NAME`. Only the reference is
  stored in PostgreSQL; the environment value is loaded in the backend process
  and never returned by the API.
- Provider redirects are disabled.
- Environment proxy settings are ignored and provider response bodies are
  limited to 5 MB before JSON parsing.

The payload follows the documented OpenAI-compatible chat-completions shape,
including `response_format.type = json_schema`. Individual compatible servers
may support only a subset, so verify their documentation before enabling them.

## Routing and fallback

Enabled providers are ordered by descending priority and filtered by capability
tier. A request can use a provider at its requested tier or a stronger tier.
Retryable timeouts, rate limits, and server failures use the configured attempt
limit before the router tries the next eligible provider. Invalid output or a
permanent rejection moves directly to the next provider.

Provider response bodies and raw exception text are not saved. Failed
invocations store a fixed safe message. Successful structured output is stored
with the invocation because later agent runs need a reproducible result.

## Prompts and token control

Prompts are immutable versions. Adding a version deactivates the earlier active
version with the same name. Templates support simple `{variable_name}` fields;
attribute access, indexing, conversions, and format expressions are rejected.
Only prompt fingerprints—not the supplied variable values—are stored on the
invocation.

The router uses a conservative four-characters-per-token estimate before a
call. It combines that estimate with the requested output limit and the
provider's configured per-million-token prices. A workspace monthly token or
cost budget can block the request before provider access. Actual provider token
counts and cost estimates are recorded after a successful call.

## Operational limits

- Health checks are explicit API requests and may contact every enabled
  provider in the active workspace.
- Provider prices are administrator-supplied estimates; CreatorOS does not
  query billing systems.
- Local models are not bundled or downloaded automatically.
- Model output remains untrusted data. Agent runs validate a fixed output
  contract and can only recommend or prepare work; they cannot publish or run
  shell commands.
- Tests use mock transports and deterministic fake providers. They do not call a
  model or paid API.
