# Contract: Skill Manifest Schema

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 1](../data-model.md)

This contract defines the YAML frontmatter that MUST appear at the top of `.claude/skills/nexcognit-brand/SKILL.md` in every consuming repo. Claude Code's Skills loader reads this frontmatter to register the Skill, decide relevance, and surface the Skill to the agent's tool list.

## Required schema

```yaml
---
name: "nexcognit-brand"
description: <string, ≤ 1024 chars>
argument-hint: <string>
compatibility: <string>
metadata:
  author: <string>
  source: <string>
  skill_version: <semver string>           # MAJOR.MINOR.PATCH
  tracks_spec_001: <spec 001 version string>
  activation_scope: <string>
user-invocable: true
disable-model-invocation: false
---
```

## Field-by-field contract

| Field | Type | Required | Constraints | Source of truth |
|---|---|---|---|---|
| `name` | string | yes | Exact value `"nexcognit-brand"`. Renaming would orphan every consuming repo. | data-model.md Entity 1 |
| `description` | string | yes | ≤ 1024 chars; MUST mention "NexCognit", "UI", "brand", "design language" so the loader's relevance match fires for UI prompts and not for unrelated work. | research.md R1 |
| `argument-hint` | string | yes | At v1: `"(no arguments — Skill activates on relevance)"` | data-model.md Entity 1 |
| `compatibility` | string | yes | MUST state Claude Code only at v1. MUST NOT claim Cursor / Codex / Copilot support. | spec.md FR-008 |
| `metadata.author` | string | yes | `"NexCognit (Amr Eid)"` — owner of the Skill. | data-model.md Entity 1 |
| `metadata.source` | string | yes | Pointer to this SpecKit feature: `"specs/007-nexcognit-brand-skill (in nexcognit-com/visualai-rendering-engine)"` | plan.md |
| `metadata.skill_version` | string | yes | Regex `^\d+\.\d+\.\d+$`. Independent semver per FR-005. Bumps follow R6 of research.md (PATCH non-semantic, MINOR additive, MAJOR breaking). | spec.md FR-005 |
| `metadata.tracks_spec_001` | string | yes | The spec 001 version string this Skill is aligned to. Mismatch with current spec 001 triggers the visibility cue described in spec.md P3-AS3. | spec.md FR-005, clarification Q2 |
| `metadata.activation_scope` | string | yes | Free text: `"NexCognit web frontends — repo-local only"` (or equivalent that conveys the same scope). | spec.md FR-004, clarification Q3 |
| `user-invocable` | boolean | yes | `true` — allows `/nexcognit-brand` explicit invocation. | research.md R1 |
| `disable-model-invocation` | boolean | yes | `false` — allows agent self-invocation when relevance is detected. | research.md R3 |

## Validation rules

These are the rules a maintainer MUST verify before merging a manifest change:

1. **Semver well-formedness**: `metadata.skill_version` matches `^\d+\.\d+\.\d+$`. Pre-release / build-metadata suffixes are forbidden at v1 to keep the version string trivially comparable.
2. **Description size**: total `description` length ≤ 1024 characters (counted as UTF-8). Oversize descriptions degrade the loader's relevance match.
3. **Description content**: `description` MUST contain the literal substrings `"NexCognit"`, `"brand"`, and either `"UI"` or `"design language"`. This is what the loader keys on to fire the Skill for UI prompts.
4. **Compatibility honesty**: the `compatibility` field MUST NOT claim support for any tool the Skill has not been verified against. v1 lists only Claude Code.
5. **Spec-version pointer presence**: `metadata.tracks_spec_001` MUST be non-empty. An empty value defeats the drift-detection purpose of FR-005.
6. **Author stability**: `metadata.author` SHOULD remain stable across bumps so consumers can trust the artifact's provenance. Author changes are allowed but should be flagged in `CHANGELOG.md`.

## Example (v1.0.0 manifest)

```yaml
---
name: "nexcognit-brand"
description: "NexCognit visual brand and design language enforcement for UI work in NexCognit web frontends. Applies the spec 001 token catalog (color, typography, spacing, radius, shadow, motion), the documented component patterns (Stepper, Content Card, Option Card, Buttons, Inputs, Select), and the WCAG-AA accessibility rules. Activates when an agent is producing UI code in a repo that has this Skill installed at .claude/skills/nexcognit-brand/."
argument-hint: "(no arguments — Skill activates on relevance)"
compatibility: "Claude Code only at v1. Cursor / Codex / Copilot deferred. Repo-local install at .claude/skills/nexcognit-brand/ — never user-global."
metadata:
  author: "NexCognit (Amr Eid)"
  source: "specs/007-nexcognit-brand-skill (in nexcognit-com/visualai-rendering-engine)"
  skill_version: "1.0.0"
  tracks_spec_001: "v1.0"
  activation_scope: "NexCognit web frontends — repo-local only"
user-invocable: true
disable-model-invocation: false
---
```

## What changes between versions

| Bump kind | Triggers | Manifest field deltas |
|---|---|---|
| PATCH | Typo fix, clearer wording, new worked example, no token changes | `metadata.skill_version` PATCH increments; `metadata.tracks_spec_001` unchanged. |
| MINOR | New token, new component pattern, new a11y rule | `metadata.skill_version` MINOR increments; if change was driven by a spec 001 update, `metadata.tracks_spec_001` advances too. |
| MAJOR | Token removal, component removal, breaking renaming, change of activation scope or compatibility | `metadata.skill_version` MAJOR increments; `metadata.tracks_spec_001` advances if spec 001 itself shipped a MAJOR; otherwise unchanged. |

## Out of contract (v1)

- No `metadata.experimental` flag — every shipped version is production-ready or it doesn't ship.
- No multi-locale `description` variants — English only at v1 (spec.md assumption: English-only audience).
- No telemetry endpoints — clarification Q5 ruled out telemetry; the manifest carries no observer URLs or event-name fields.
