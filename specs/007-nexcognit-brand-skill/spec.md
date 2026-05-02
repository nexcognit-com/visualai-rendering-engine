# Feature Specification: NexCognit Brand Skill for UI

**Feature Branch**: `007-nexcognit-brand-skill`
**Created**: 2026-04-25
**Status**: Draft
**Input**: User description: "nexcognit-brand Skill for UI"

## Overview

A reusable Skill artifact that captures the NexCognit visual brand and design language defined in [Feature 001 — UI Style](../001-nexcognit-ui-style/spec.md), packaged in a form that AI coding assistants can load and apply directly when producing UI work. The Skill turns spec 001 from a passive reference document into an active tool: an agent that has the Skill loaded should generate brand-compliant interfaces on the first attempt, without re-deriving tokens, typography, components, or accessibility rules from the spec each session.

This is the AI-tooling counterpart to spec 001. Spec 001 is the human-readable design contract; this spec defines the agent-readable enforcement of that contract.

## Clarifications

### Session 2026-04-25

- Q: Which AI coding assistants must the Skill support at v1? → A: Claude Code only (Anthropic Skills format).
- Q: How is the Skill version linked to spec 001? → A: Independent Skill semver, with a manifest field that names the spec 001 version it tracks; Skill cadence is independent of spec cadence, drift is visible via the manifest.
- Q: Where is the Skill installed and how is it activated? → A: Repo-local at `.claude/skills/nexcognit-brand/` inside each consuming NexCognit web repo. Activation is automatic for that repo's Claude Code sessions; the Skill never activates outside a repo that has it installed.
- Q: When does the agent substitute vs refuse off-brand instructions? → A: Tiered policy. Color, spacing, radius, and shadow → substitute the nearest documented token and explain. Typography and accessibility violations → refuse with a one-line reason and name the documented alternative. No silent compliance in either tier.
- Q: How are SC-001 (≥95%) and SC-002 (≥80%) measured? → A: Side-by-side comparison runs. A fixed prompt set of representative UI requests (button, card, dialog, form, layout) is executed twice — once with the Skill loaded, once without — and each output is scored against the spec 001 brand checklist and timed to acceptance. The deltas yield the SC-001 / SC-002 numbers. No telemetry plumbing is required at v1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent produces brand-compliant UI on first attempt (Priority: P1)

A developer working in a NexCognit web frontend asks an AI coding assistant to add a new screen, dialog, or component (e.g., "add a confirmation modal for the delete-asset action"). The agent has the NexCognit Brand Skill loaded. The output uses the correct color tokens, the correct typography pairing, the correct radii and spacing, the correct component shape language, and meets accessibility contrast requirements — all without the developer having to point the agent at spec 001 or copy-paste tokens into the prompt.

**Why this priority**: This is the entire reason the Skill exists. Today, every fresh AI session that touches UI in a NexCognit repo starts from a blank slate and re-derives brand decisions, often poorly. The Skill collapses that ramp from minutes-to-hours of correction to zero. Without P1, the Skill has no value.

**Independent Test**: Open a fresh session in any NexCognit web repo, load the Skill, ask the agent to produce a representative UI element (button, card, dialog, form). Compare the generated code against the spec 001 brand checklist. P1 passes if the generated element scores ≥ 95% on the brand checklist with no follow-up correction prompts.

**Acceptance Scenarios**:

1. **Given** a fresh agent session in a NexCognit web frontend with the Skill loaded, **When** the developer asks for a primary CTA button, **Then** the agent emits code using the documented accent token, border radius, font family, hover/active states, and accessible focus ring without being prompted on any of those details.
2. **Given** an agent session with the Skill loaded, **When** the developer asks for a card-based grid layout, **Then** the agent uses the documented card surface, border, shadow, and gap tokens — not arbitrary values it invented.
3. **Given** an agent session with the Skill loaded, **When** the developer asks for a destructive action confirmation dialog, **Then** the agent emits a dialog using the documented dialog shell, the destructive accent treatment, the documented spacing scale, and an accessible focus trap.

---

### User Story 2 — Skill flags or auto-corrects off-brand output (Priority: P2)

A developer asks the agent to make a change that, if implemented naively, would introduce off-brand styling — for example, hardcoding a hex color, picking a font outside the approved pair, using a non-standard radius, or producing text that fails contrast. The Skill causes the agent to either refuse the off-brand value, substitute it with the closest documented token, or surface the conflict to the developer with a one-line explanation.

**Why this priority**: Real-world prompts rarely come pre-cleaned. Developers paste hex codes from screenshots, ask for "make it blue," or copy code from outside sources. P2 makes the Skill robust to those messy inputs. Without P2, P1 holds only for ideal prompts and silently drifts under realistic ones.

**Independent Test**: With the Skill loaded, prompt the agent with off-brand instructions ("use #FF5733 for the button," "use Comic Sans," "remove the focus ring"). The agent must either refuse and explain, or substitute the nearest documented token and explain the substitution. Hidden silent acceptance is a failure.

**Acceptance Scenarios**:

1. **Given** the Skill is loaded, **When** the developer asks for an arbitrary hex color, **Then** the agent substitutes the closest documented brand token, names the token used, and notes the substitution in one line.
2. **Given** the Skill is loaded, **When** the developer asks for a typeface outside the approved pair, **Then** the agent declines, names the approved pair, and asks the developer to pick from it.
3. **Given** the Skill is loaded, **When** the developer asks for a UI change that would violate a documented accessibility rule (e.g., contrast, missing focus state, non-semantic markup), **Then** the agent flags the violation and offers the compliant alternative.

---

### User Story 3 — Skill stays in sync with spec 001 (Priority: P3)

The design system evolves. A new accent color is added, a component pattern is retired, the type scale shifts. The Skill must be versioned, must declare which spec 001 revision it tracks, and must have a documented update path so that "what the Skill enforces" never silently diverges from "what the spec says." A single source-of-truth violation between spec 001 and the Skill is a bug, not a tolerable drift.

**Why this priority**: Without versioning, the Skill becomes a stale liability the moment spec 001 changes. P3 turns a one-shot artifact into a maintainable one. It is P3 (not P1) because at v1 the Skill and spec 001 are necessarily aligned; the cost of skipping P3 is paid only at the first design-system update.

**Independent Test**: Inspect the Skill artifact for an explicit version, an explicit spec-001-revision pointer, and a documented update procedure. After a hypothetical spec 001 change, follow the update procedure and confirm the new Skill version emits the new tokens.

**Acceptance Scenarios**:

1. **Given** the Skill artifact, **When** an operator inspects it, **Then** the artifact declares its own version and the spec 001 revision it tracks.
2. **Given** spec 001 ships a new accent token, **When** the operator follows the update procedure, **Then** the new Skill version exposes the new token to agents and the changelog records the addition.
3. **Given** an agent loads a Skill version older than the spec 001 revision currently in the repo, **When** the agent attempts to apply the Skill, **Then** the agent surfaces the version mismatch as a warning rather than silently using stale guidance.

---

### Edge Cases

- **Out-of-scope UI element requested**: Developer asks for a UI element the Skill does not cover (e.g., a calendar widget, a charting library, a marketing illustration). The Skill must say so explicitly rather than improvise off-brand defaults; the agent falls back to "no opinion, please check spec 001 for guidance or escalate to design."
- **Non-NexCognit repo loads the Skill by mistake**: The Skill is loaded in a repo that is not a NexCognit surface. The agent should detect this (per the activation rule) and either decline to apply the brand or warn that the Skill is being applied outside its declared scope.
- **Conflicting brand directives in the same session**: The developer pastes a brand-board screenshot from a different brand into the same session. The agent must continue to follow the loaded Skill, not the screenshot, and explain why.
- **Skill loaded but spec 001 has not yet been merged**: A repo references the Skill before the design language is finalized. The Skill must declare a "draft" status when its tracked spec 001 revision is itself in draft, and the agent must surface that draft status to the developer on first use in a session.
- **Two NexCognit surfaces with intentionally different sub-themes**: A future surface (e.g., an admin-only panel) needs a slightly different accent treatment from the marketing-facing surfaces. The Skill must accommodate sub-theming via documented variants rather than forcing a fork.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Skill MUST encode the complete brand token set from spec 001 — at minimum: color palette, typography pair and scale, spacing scale, border-radius scale, shadow/elevation scale, and motion/transition scale — in a form an AI agent can apply directly without consulting the source spec.
- **FR-002**: The Skill MUST encode the documented component patterns from spec 001 — at minimum: buttons (primary/secondary/destructive), cards, inputs (text/select/textarea), dialogs, navigation (sidebar, tabs), and progress indicators — including their states (default/hover/active/disabled/focus).
- **FR-003**: The Skill MUST encode the documented accessibility rules — at minimum: minimum contrast ratios per surface, required focus-state treatments, semantic-markup expectations, and keyboard-navigation requirements — and the agent MUST apply them as enforcement, not as suggestions.
- **FR-004**: The Skill MUST be installed repo-locally at `.claude/skills/nexcognit-brand/` inside each consuming NexCognit web repo, and MUST rely on Claude Code's project-level Skill auto-discovery for activation. The Skill MUST NOT be installed at the user-global level (`~/.claude/skills/`) at v1, ensuring it cannot bleed brand opinions onto unrelated work simply by being installed once. The Manifest MUST also declare the activation scope textually so the boundary remains documented even when the artifact is copied between repos.
- **FR-005**: The Skill MUST carry an independent semantic version (MAJOR.MINOR.PATCH) and the Skill Manifest MUST declare a `tracks_spec_001` field naming the spec 001 version the Skill is aligned to. Skill version cadence is independent of spec 001 cadence: a Skill PATCH bump for a clearer worked example MUST NOT require a spec 001 change, and a spec 001 change MUST trigger at least a Skill MINOR bump with the manifest field updated to the new spec version.
- **FR-006**: When given an off-brand instruction, the agent loaded with the Skill MUST apply a tiered response policy and MUST never silently comply:
  - **Substitute tier** (color, spacing, border-radius, shadow/elevation): the agent picks the nearest documented brand token, applies it, and emits a one-line explanation naming the substitute. Example: "Substituted `#FF5733` with the documented destructive accent token."
  - **Refuse tier** (typography outside the approved pair, any accessibility violation — contrast minimum, focus-state removal, semantic-markup downgrade, keyboard-reachability loss): the agent refuses the instruction with a one-line reason and names the documented alternative the developer should pick from. The agent does not invent a "closest font" or weaken an a11y rule under any framing.
- **FR-007**: The Skill MUST include at least one canonical worked example for each documented component pattern, so that an agent has a reference shape to anchor its output.
- **FR-008**: The Skill MUST be packaged in Anthropic's Skills format and load correctly inside Claude Code (the only assistant supported at v1). Support for additional AI coding assistants is explicitly deferred to a follow-up version per the update procedure (FR-009); v1 makes no compatibility claim beyond Claude Code.
- **FR-009**: The Skill MUST document its own update procedure: how a designer or maintainer brings the Skill in line with a new spec 001 revision, including the changelog entry format and the version-bump rules.
- **FR-010**: The Skill MUST gracefully degrade when asked about UI elements outside its documented scope: it states the gap and points the developer at spec 001 / design escalation rather than improvising.
- **FR-011**: The Skill MUST make its loaded-and-active status visible to the developer at the start of the session (so the developer knows whether the agent is about to produce brand-compliant work or vanilla output).

### Key Entities

- **Brand Token Set**: The canonical color, typography, spacing, radius, shadow, and motion values defined by spec 001. The atomic unit of brand decisions; everything else composes from these.
- **Component Pattern**: A named, reusable UI shape (e.g., "primary button," "asset card," "destructive dialog") with its states, content slots, and accessibility expectations. Composed from Brand Tokens.
- **Accessibility Rule**: A non-negotiable contract on output (contrast minimum, focus visible, semantic markup, keyboard reachability). Enforced regardless of token choice.
- **Activation Scope**: The declared boundary of where the Skill applies — what kinds of repos, what kinds of tasks, what surfaces. Prevents bleed onto out-of-scope work.
- **Skill Manifest**: Metadata describing the Skill — name, independent Skill semver (MAJOR.MINOR.PATCH), the `tracks_spec_001` version pointer, declared activation scope, declared tool compatibility (Claude Code only at v1), changelog. Loaded first when the Skill activates.
- **Worked Example**: A canonical reference implementation for a Component Pattern, used by the agent as an anchor when generating new instances.
- **Brand Compliance Check**: The set of validation rules the agent applies to its own output before returning it, derived from Tokens + Patterns + Accessibility Rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer working with the Skill loaded in a fresh session generates brand-compliant UI on the first attempt for ≥ 95% of representative component requests (buttons, cards, dialogs, forms, layouts), measured against the spec 001 brand checklist via side-by-side comparison runs (with-Skill vs without-Skill on the same prompt set).
- **SC-002**: Time from "ask the agent for a UI element" to "developer accepts the output without a brand-correction follow-up prompt" drops by at least 80% compared to a baseline session without the Skill loaded, measured by timing the same fixed prompt set under both conditions in the side-by-side comparison runs used for SC-001.
- **SC-003**: 100% of off-brand instructions (arbitrary hex, off-palette font, missing focus, contrast-failing combination) submitted to an agent with the Skill loaded receive either a substitution-with-explanation or a refusal-with-reason — zero silent acceptances.
- **SC-004**: The Skill artifact, when loaded, fits within the practical context budget of every supported AI coding assistant such that the developer never has to choose between "load the Skill" and "give the agent enough room to work" — measured by load size never exceeding the platform-published recommended limits for system instructions.
- **SC-005**: After a spec 001 revision ships, a maintainer can produce an updated Skill version that reflects the change in under 30 minutes by following the documented update procedure — measured by the time from spec 001 merge to Skill version-bump merge.
- **SC-006**: A developer can identify whether the Skill is currently loaded-and-active in their session within 5 seconds of starting the session, without inspecting tool internals — measured by the visibility cue defined in FR-011.

## Assumptions

- **Spec 001 is the single design source of truth.** The Skill never invents brand opinions; it only encodes what spec 001 already documents. If spec 001 is silent on a topic, the Skill is silent too.
- **AI coding assistants used by the NexCognit team support a "skill" / instruction-pack loading mechanism.** The exact mechanism (Skills, custom instructions, rules files, MCP-loaded resources) is an implementation choice for the planning phase; the spec assumes at least one such mechanism exists in every supported tool.
- **The Skill's audience is AI agents and the developers driving them, not end users.** End users never see the Skill directly; they see its effect on the UI the agent produces.
- **v1 targets Claude Code exclusively.** The Skill is packaged in Anthropic's Skills format. Cross-tool support (Cursor, Codex, Copilot, others) is intentionally out of scope for v1 and is reintroduced through the update procedure (FR-009) when the team adopts another assistant in earnest. This is a deliberate scope contraction to avoid building per-tool packaging machinery before there is a second consumer to justify it.
- **Visual assets (illustrations, photography, custom iconography beyond the documented icon set) are out of scope for v1.** The Skill covers structural UI (HTML, CSS, component shapes, layout, motion); standalone visual-asset production remains a design-team handoff.
- **Sub-theming is anticipated but not delivered at v1.** v1 covers a single active theme. Sub-themes (admin variant, marketing-page variant, dark-vs-light variant if added) are deferred to a follow-up version that introduces the variant mechanism cleanly.
- **The Skill is consumed by every NexCognit web surface that ships UI** — at v1 this is `visualai-frontend`; future surfaces (Layer 2 admin panels, marketing pages, agency white-label dashboards) inherit by the same activation rule.
- **The "this repo is a NexCognit surface" signal is the presence of the Skill itself at `.claude/skills/nexcognit-brand/`.** No additional marker file or repo-name heuristic is needed: a repo that has installed the Skill has, by definition, opted in. This makes activation deterministic and removes false-positive risk on repos that happen to share naming patterns.
