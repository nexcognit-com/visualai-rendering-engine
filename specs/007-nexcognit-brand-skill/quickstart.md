# Quickstart: NexCognit Brand Skill for UI

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Audience**: maintainers installing the Skill into a new consuming repo, and developers verifying it activated correctly.

---

## Part 1 — Install the Skill in a NexCognit web frontend

Run from the consuming repo's root (e.g., `visualai-frontend/`).

### Prerequisites

- The consuming repo is a NexCognit web surface (frontend, admin panel, marketing site).
- Claude Code is the AI coding assistant in use (v1 only supports Claude Code per FR-008).
- A copy of the Skill artifact (initially produced as part of `/speckit.tasks` work for this feature) is available — in v1 the canonical source lives in this MPT repo's `specs/007-nexcognit-brand-skill/skill-source/` (created during implementation tasks); future versions may publish to a Skill registry.

### Install

```sh
mkdir -p .claude/skills/nexcognit-brand
cp -R <path-to-skill-source>/. .claude/skills/nexcognit-brand/
git add .claude/skills/nexcognit-brand/
git commit -m "chore: install nexcognit-brand Skill v1.0.0 (tracking spec 001 v1.0)"
```

The Skill is now opt-in for this repo. Claude Code's project-level Skill auto-discovery picks it up on the next session start.

### Verify install

Open a fresh Claude Code session in the consuming repo and ask a UI question, e.g.:

> Add a primary CTA button labelled "Continue".

The agent's response MUST begin with:

> NexCognit Brand Skill v1.0.0 (tracking spec 001 v1.0) loaded. Applying NexCognit visual brand to this UI request.

If the cue is missing, see "Troubleshooting" below.

---

## Part 2 — Run the side-by-side acceptance harness (SC-001 + SC-002)

This is how a maintainer measures the Skill's success metrics. Manual at v1 per clarification Q5.

### Prepare

1. Pick a target consuming repo (`visualai-frontend` is the v1 default).
2. Make a list of the 10 fixed prompts from [research.md §R4](./research.md):
   1. "Add a primary CTA button that says 'Continue'."
   2. "Add a secondary/ghost button that says 'Cancel'."
   3. "Render a 7-step stepper at state 3-of-7 with appropriate labels."
   4. "Render a 2-column option grid of 4 mode cards (Product Shoot, Short Marketing, Long-Form, UGC)."
   5. "Render a content card containing a small H3 title, body text, and a primary button."
   6. "Render a labelled text input with placeholder 'Enter product URL'."
   7. "Render a select dropdown listing voice options (3 items)."
   8. "Render a confirmation dialog for a destructive 'Delete asset' action."
   9. "Render the Dashboard layout: dark canvas, sidebar, content area with H1, two cards."
   10. "Render a small 'Loading…' state for the asset list."
3. Have spec 001's FR-001 through FR-018 open as the scoring rubric.

### Run A (no-Skill baseline)

```sh
# Temporarily remove the Skill
mv .claude/skills/nexcognit-brand .claude/skills/nexcognit-brand.disabled
```

Open a fresh Claude Code session. Submit each of the 10 prompts; for each:
- Save the agent's output verbatim.
- Time the prompt-submission-to-acceptance interval (a human judgement: "would I accept this without follow-up correction?"). Stop the clock the moment the developer would accept.
- Score the output against spec 001 FR-001..FR-018 (1 point per FR satisfied; max ~18 per output).

Restore:

```sh
mv .claude/skills/nexcognit-brand.disabled .claude/skills/nexcognit-brand
```

### Run B (with-Skill)

Open a fresh Claude Code session. Submit the same 10 prompts; for each:
- Save the agent's output verbatim.
- Time the same interval.
- Score against the same rubric.

### Compute SCs

| Metric | Formula | Pass threshold |
|---|---|---|
| **SC-001** (≥ 95% first-attempt brand compliance) | `sum(Run B scores) / (10 × 18)` | ≥ 0.95 |
| **SC-002** (≥ 80% time reduction vs baseline) | `median(Run B times) / median(Run A times)` | ≤ 0.20 |
| **SC-003** (zero silent acceptance of off-brand) | inspect Run B for any output where an off-brand input was accepted without a substitute/refuse note | exactly 0 silent acceptances |
| **SC-004** (size budget) | `du -sb .claude/skills/nexcognit-brand/ --exclude=examples` | ≤ 30 KB target, ≤ 60 KB hard cap |
| **SC-006** (visibility cue ≤ 5 s) | timer from session start to first sight of cue line | ≤ 5 seconds |

For SC-003, also run the 8 Compliance Check tests defined in [contracts/compliance-check-contract.md](./contracts/compliance-check-contract.md) with explicit off-brand prompts; every one MUST emit a substitute or refuse note.

For activation tests (SC behavior coverage), run the 8 tests defined in [contracts/activation-contract.md](./contracts/activation-contract.md).

### Record results

Append a section to `.claude/skills/nexcognit-brand/CHANGELOG.md`:

```markdown
## v1.0.0 — 2026-XX-XX

**Side-by-side run (operator: <name>):**
- SC-001 score: <ratio> (target ≥ 0.95)
- SC-002 ratio: <ratio> (target ≤ 0.20)
- SC-003: <pass/fail> with zero silent acceptances
- SC-004 size: <bytes> (≤ 30 KB target)
- SC-006 cue latency: <seconds>
```

If any SC fails, the Skill version is NOT cleared for use in the consuming repo; the maintainer reverts the install and opens a follow-up issue.

---

## Part 3 — Update the Skill after spec 001 changes (FR-009)

Target time: ≤ 30 minutes (SC-005).

1. Pull the latest spec 001 from `nexcognit-com/visualai-rendering-engine` (this MPT repo).
2. Read the spec 001 changelog (or the diff vs the version named in the Skill's `metadata.tracks_spec_001`).
3. Identify which Skill files are affected:
   - Color / typography / spacing / radius / shadow / motion change → `tokens.md`.
   - Component pattern change → `components.md` and the matching file in `examples/`.
   - Accessibility rule change → `accessibility.md`.
4. Edit the affected files. Cite the spec 001 FR you implemented.
5. Bump `metadata.skill_version` per FR-005 rules (PATCH = no token change, MINOR = additive, MAJOR = breaking).
6. Update `metadata.tracks_spec_001` to the new spec 001 version.
7. Append a `CHANGELOG.md` entry naming the spec 001 revision and the affected files.
8. Re-run Part 2's side-by-side harness on at least the prompts touching the changed area; record results in the new CHANGELOG entry.
9. Commit and open a PR in the consuming repo. PR title: `chore(skill): update nexcognit-brand to vX.Y.Z (spec 001 vA.B)`.

If the change spans many consuming repos, repeat steps 4–9 in each. Future versions may centralize the source-of-truth Skill in this MPT repo with a sync script; v1 is repo-local copy.

---

## Part 4 — Author a new consuming repo

When a new NexCognit web surface is created (e.g., a Layer 2 admin panel, a marketing site), follow Part 1 to install the Skill, then verify with Part 2.

The Skill MUST NOT be installed at the user-global level (`~/.claude/skills/`) at v1, even if the user owns multiple NexCognit repos. Repo-local install is the v1 contract per clarification Q3.

---

## Troubleshooting

### The visibility cue doesn't appear

- Confirm the directory exists at exactly `.claude/skills/nexcognit-brand/` (not `.claude/skill/` or under another name).
- Confirm `SKILL.md` is the entry filename (not `skill.md`, not `README.md`).
- Confirm Claude Code recognizes the project-level Skills directory; `claude --list-skills` (or equivalent) should include `nexcognit-brand`.
- Open a truly fresh session — Skills load at session start, not mid-session.

### Output is brand-compliant but no substitution/refusal notes appear

- The agent may have correctly produced compliant output with no off-brand input to refuse — this is normal.
- To test the substitute/refuse path explicitly, prompt with an off-brand value: "Use `#FF5733` for the button." Expect a one-line substitution note.

### Output uses tokens correctly but skips a11y rules

- This is a v1 bug. Capture the prompt, the response, and which rule was missed; file an issue against `specs/007-nexcognit-brand-skill/`.

### Skill is loaded in a non-NexCognit repo by mistake

- Remove the directory: `rm -rf .claude/skills/nexcognit-brand/`.
- The Skill cannot self-detect non-NexCognit repos (clarification Q3 made the Skill's presence the opt-in signal); accidental installs are the developer's responsibility to undo.

### `metadata.tracks_spec_001` is stale (spec 001 has advanced)

- Follow Part 3 to update the Skill.
- Until updated, the agent emits the mismatch warning per the activation contract; this is informative, not an error.

---

## Related contracts

- [contracts/skill-manifest-schema.md](./contracts/skill-manifest-schema.md) — frontmatter schema
- [contracts/activation-contract.md](./contracts/activation-contract.md) — when and how the Skill activates
- [contracts/compliance-check-contract.md](./contracts/compliance-check-contract.md) — substitute/refuse rules
