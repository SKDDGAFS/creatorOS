# CreatorOS capability integration plan

Codex uses local development skills while building CreatorOS. The application
will gain matching product capabilities through reviewed services and adapters
in the roadmap sprint where each capability belongs. A Codex skill is not a
runtime dependency and is never copied into the product blindly.

Local development must work without a paid API key. Optional cloud providers
stay behind typed interfaces and remain disabled until the user configures them.

| Development skill | CreatorOS capability | Sprint | Local foundation | Main safeguards | Status |
| --- | --- | --- | --- | --- | --- |
| `token-optimization` | Token budgets, context compaction, model routing, and prompt versions | L–M | Local model runner and deterministic test doubles | Preserve system and permission rules during compaction; record usage per run | Router and budgets implemented |
| `humanize-writing`, `copywriting`, `copy-editing` | Brand-aware scripts, captions, copy generation, and revision | M, O, R | Versioned text artifacts and local models | Preserve facts and sources; validate output; require publishing approval | Planned |
| `content-strategy`, `social` | Content pillars, calendars, hooks, repurposing, and platform variants | N–R | Local planning services | Keep evidence, uncertainty, workspace ownership, and version history | Planned |
| `ad-creative` | Creative briefs, ad variants, and experiments | O, Q, R | Template-driven local generation | Separate claims from evidence; require review before export or publishing | Planned |
| `faster-whisper-transcriber` | Arabic, English, and mixed-language transcription | R, U | Faster-Whisper and FFmpeg | Local-first processing, bounded files, safe paths, explicit external-provider consent | Planned |
| `watch` | Timestamped transcript and scene-based video analysis | N, R, U | FFmpeg scene extraction plus local transcription | Treat frames, subtitles, and metadata as untrusted input | Planned |
| `video` | Remotion compositions, previews, rendering, and reference-style plans | R, U | Remotion and FFmpeg | No arbitrary commands or paths; licensed/user-owned assets; approval before publishing | Planned |
| `imagegen` | Thumbnails, storyboards, and supporting visual assets | R, U | User assets, placeholders, or optional local models | Provider-neutral interface; no silent external upload | Planned |
| `security-best-practices` | Secure defaults and final audit | Every sprint, especially Y | Static checks and tests | Authentication, authorization, isolation, injection, secret, and media review | Active |
| `gh-fix-ci`, `gh-address-comments` | Pull-request maintenance | Every sprint | GitHub CLI and Actions | Inspect before changing; keep fixes scoped; never merge without approval | Active |

## Runtime capability boundary

Sprint M should introduce a typed capability registry for CreatorOS agents. Each
entry needs an input schema, output schema, allowed agent types, workspace
authorization rule, timeout, usage budget, activity record, and approval policy.
Agents must not execute arbitrary shell commands or turn imported text into
instructions.

## Media pipeline boundary

Sprint U should expose transcription, inspection, and rendering through narrow
process adapters. Commands and executable paths are application-owned. User
values are passed as validated argument-list entries, never interpolated into a
shell string. Uploaded media is stored outside the web root with generated
filenames, checksums, size limits, type inspection, and a scanning hook.

Reference-video analysis may describe structure, pacing, transitions, captions,
and visual language. It must not copy protected footage, music, logos, or an
identifiable creator's exact work without permission.
