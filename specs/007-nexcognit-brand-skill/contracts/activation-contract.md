# Contract: Activation Behavior

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 5](../data-model.md)

This contract defines exactly when the Skill activates, what the agent emits when it does, and what it MUST NOT do outside its declared scope.

## Activation matrix

| Trigger | Skill loads? | Agent emits visibility cue? | Agent applies brand? |
|---|---|---|---|
| Claude Code session opens in repo with `.claude/skills/nexcognit-brand/` present, first prompt is UI-related | yes | yes (one-line cue at first UI prompt) | yes |
| Same session, subsequent UI prompts | already loaded | no (cue is once-per-session) | yes |
| Same session, non-UI prompt (Python bug, infra, data analysis) | already loaded | no | no |
| Claude Code session opens in repo without the Skill installed | no | n/a | no — agent operates with no brand opinions |
| Developer types `/nexcognit-brand` explicitly | yes (manual) | yes | yes — applies to that turn |
| Skill present but `metadata.tracks_spec_001` lags the current spec 001 version | yes | yes, with **mismatch warning** appended | yes — using the older guidance, with explicit note |
| Skill present but a referenced file (e.g., `tokens.md`) is missing or empty | partial — see graceful-degradation below | yes, with **load-failure warning** | no — agent falls back to no-Skill behavior |

## The visibility cue (FR-011 + SC-006)

When the Skill activates for the first UI prompt of a session, the agent MUST emit a one-line notice **before** producing any UI output:

> NexCognit Brand Skill v{skill_version} (tracking spec 001 {tracks_spec_001}) loaded. Applying NexCognit visual brand to this UI request.

Substitution rules for `{skill_version}` and `{tracks_spec_001}`: pulled directly from `metadata` in `SKILL.md`. The agent MUST NOT invent values; if the manifest is unreadable, fall through to the load-failure path.

The cue is emitted at most **once per session**, on the first UI prompt where the Skill applies. Repeating it on every UI prompt would add noise without value.

## Mismatch warning

When `metadata.tracks_spec_001` does not match the current spec 001 version available to the maintainer (a state the Skill itself cannot detect at runtime — only the maintainer can confirm during the update procedure), the manifest MUST be updated. At runtime, if the maintainer has annotated the manifest's `description` with a `(stale)` suffix, the cue becomes:

> NexCognit Brand Skill v{skill_version} (tracking spec 001 {tracks_spec_001} — stale; spec 001 has advanced) loaded. Applying older brand guidance; ask the maintainer to update the Skill.

This satisfies spec.md P3 acceptance scenario #3 ("agent surfaces version mismatch as a warning rather than silently using stale guidance").

## Graceful degradation on load failure (R7 of research.md)

If the agent attempts to read a referenced file (e.g., the activation hook says "see `tokens.md`") and finds it missing, empty, or unparseable, the agent MUST:

1. Emit a one-line load-failure warning:
   > NexCognit Brand Skill failed to load: `{filename}` is missing or unreadable. Falling back to no-Skill behavior. Ask the maintainer to repair the Skill artifact.
2. Refuse to fabricate brand opinions for the rest of the session.
3. Continue answering the developer's question using vanilla Claude Code behavior (i.e., as if no Skill were installed).

This prevents a corrupt Skill from silently producing off-brand output the developer believes is brand-compliant.

## Out-of-scope handling (FR-010)

When asked about a UI element NOT in the Component Pattern catalog (calendar widget, charting library, marketing illustration, custom iconography beyond Lucide):

1. The agent MUST explicitly state that the Skill does not cover the requested element.
2. The agent MUST NOT improvise off-brand defaults.
3. The agent SHOULD point the developer at spec 001 (`specs/001-nexcognit-ui-style/spec.md` in the upstream repo) and suggest design escalation.

Example response shape:
> NexCognit Brand Skill does not cover calendar widgets. Spec 001 doesn't define this pattern. Either pick a third-party component and the design team can review it, or escalate to design for a brand-aligned spec addition.

## Cross-tool refusal

If the Skill is somehow loaded by a tool other than Claude Code (a future Cursor / Codex / Copilot integration that hasn't been validated), the agent MUST:

1. Refuse to apply the Skill.
2. Emit a one-line message:
   > NexCognit Brand Skill v{skill_version} is verified for Claude Code only at v1. This tool is not supported. Refusing to apply brand guidance.
3. Continue with vanilla behavior.

This protects the v1 scope contraction made in clarification Q1 — the Skill MUST NOT silently produce output in an unsupported tool that may misinterpret its rules.

## What the Skill MUST NOT do

- **MUST NOT activate in repos without the install directory.** Bleed prevention is the entire point of clarification Q3.
- **MUST NOT silently substitute or refuse.** Every Substitute or Refuse action MUST emit the one-line explanation defined in the Compliance Check contract.
- **MUST NOT call out to the network.** The Skill is static markdown; it does not fetch the current spec 001 version, telemetry endpoints, or anything else.
- **MUST NOT apply brand opinions to non-UI prompts.** Even when the Skill is loaded, asking about Python or infra MUST receive vanilla output.
- **MUST NOT persist state across sessions.** Every session is fresh; the visibility cue fires once per session because the agent has no memory of prior sessions.

## Verification (drives task design)

Each row of the activation matrix MUST become an acceptance test in the side-by-side harness (or in the harness's "edge case" suite):

| Test ID | Setup | Expected behavior |
|---|---|---|
| ACT-1 | Repo with Skill installed; UI prompt | Visibility cue + brand-compliant output |
| ACT-2 | Repo with Skill installed; second UI prompt in same session | Brand-compliant output, no second cue |
| ACT-3 | Repo with Skill installed; non-UI prompt | Vanilla output, no cue |
| ACT-4 | Repo WITHOUT Skill; UI prompt | Vanilla output, no cue |
| ACT-5 | Manual `/nexcognit-brand` invocation | Cue + brand-compliant output |
| ACT-6 | Skill installed; `tokens.md` deleted | Load-failure warning + vanilla output |
| ACT-7 | Skill installed; `metadata.tracks_spec_001` annotated `(stale)` in description | Cue with mismatch warning |
| ACT-8 | Skill installed; out-of-scope UI request (calendar) | Explicit non-coverage statement, no improvisation |

These eight tests are the contract surface for `/speckit.tasks` to schedule.
