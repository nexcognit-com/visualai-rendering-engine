# Contract: SpecKit ↔ Jira Sync

**Feature**: 004-neon-jira-github-ops
**Consumer**: Engineers + agents running SpecKit commands; PR authors linking work to Jira.
**Authority**: this document + [spec.md FR-008..015](../spec.md) + `OPERATIONS.md`.

---

## Project identifiers

| Thing | Value |
|---|---|
| Atlassian site URL | `https://nexcognit.atlassian.net` |
| Jira project key | `VIS` |
| Jira project name | `VisualAI` |
| Confluence space (optional) | `VIS` — mirrors Jira project key |

---

## 1:1 mappings

| SpecKit artifact | Jira issue type | Summary format | Labels | Parent |
|---|---|---|---|---|
| `specs/NNN-short-name/` (the directory) | Epic | `Feature NNN — <title>` | `speckit`, `feature-NNN` | (no parent) |
| User Story US**k** in the feature's `spec.md` | Story | `US<k> — <story title>` | `priority-P<k>`, `feature-NNN` | Epic for feature NNN |
| Row T**###** in the feature's `tasks.md` | Task | exact SpecKit task description (trim to 255 chars) | `spec-task:T###`, `feature-NNN`, `[P]` if parallelizable | Story if the task is labeled with `[US<k>]`, else Epic |
| Bug discovered during review | Bug | `Bug: <summary>` | `bug`, `feature-NNN` | Epic, optionally linked to Story |

Custom field attached to the Epic only: `spec_feature_dir = "NNN-short-name"` — the single queryable link back to SpecKit.

---

## When each issue is created

| Trigger | MCP tool used | Issue created |
|---|---|---|
| `/speckit-specify` writes `specs/NNN-*/spec.md` | `mcp__claude_ai_Atlassian__createJiraIssue` | Epic |
| `/speckit-specify` finalizes user stories | same | Story per user story |
| `/speckit-tasks` writes `specs/NNN-*/tasks.md` | same | Task per row in tasks.md |
| Developer opens a PR with `VIS-### #in-review` in the title | Smart Commits (built-in) | Task transitions to `In Review` |
| PR is merged | Smart Commits | Task → `Done` |
| Bug found in review | Manual via MCP | Bug |

Creation latency target: ≤ 30 min for Epics (SC-003), ≤ 60 min for Tasks (SC-004). Agents should create Epics synchronously after `/speckit-specify` completes; Tasks in a batch call after `/speckit-tasks`.

---

## Creation request shapes

### Create an Epic for a new SpecKit feature

```
Tool: mcp__claude_ai_Atlassian__createJiraIssue
Inputs:
  cloudId:  <from getAccessibleAtlassianResources>
  projectKey: "VIS"
  issueTypeName: "Epic"
  summary: "Feature 002 — Video Duration Range, Variations, and Preview Gate for Long Videos"
  description: "SpecKit feature: specs/002-video-duration-variations/spec.md\n\n(Imports from spec.md Overview section...)"
  labels: ["speckit", "feature-002"]
  customFields: {"spec_feature_dir": "002-video-duration-variations"}
```

### Create a Story under the Epic

```
Tool: mcp__claude_ai_Atlassian__createJiraIssue
Inputs:
  cloudId: <same>
  projectKey: "VIS"
  issueTypeName: "Story"
  summary: "US1 — Creator picks a precise video length"
  description: "(body of User Story 1 from spec.md)"
  parent: "<Epic key>"
  labels: ["priority-P1", "feature-002"]
```

### Create a Task under a Story

```
Tool: mcp__claude_ai_Atlassian__createJiraIssue
Inputs:
  cloudId: <same>
  projectKey: "VIS"
  issueTypeName: "Task"
  summary: "Add total_duration_seconds + variation_count + render_mode + seed fields to VideoParams in app/models/schema.py"
  parent: "<Story key>"   # OR "<Epic key>" if task has no [US] label
  labels: ["spec-task:T014", "feature-002"]
```

---

## PR → Jira state transitions (Smart Commits)

Smart Commits is a built-in Jira Cloud feature. No custom webhook required.

| When | Required PR/commit text | Effect |
|---|---|---|
| PR opened | Title contains `VIS-### #in-review` | Issue transitions to `In Review` |
| PR merged (squash, rebase, or merge-commit) | Merge message contains `VIS-### #done` | Issue transitions to `Done` |
| Comment reference | Commit message includes `VIS-### #comment <text>` | Text appended as a Jira comment |
| Time-tracking | `VIS-### #time 2h` | Logs 2 hours to the issue |

**PR title convention** (enforced by a PR-title commitlint rule in `ops-guard`):

```
<conventional-commit-type>(<spec-feature>): <summary>  VIS-### #in-review

Examples:
  feat(002): add duration slider + variation stepper to wizard  VIS-142 #in-review
  fix(003): prevent negative balance on admin deduct            VIS-187 #in-review
  docs(ops): clarify break-glass incident template              VIS-201 #in-review
```

Merge-commit convention (squash-merge default, so the merge commit body inherits PR description):

```
<PR title>

Closes VIS-### #done
```

---

## Agent behavior

When an agent runs `/speckit-specify`, after writing the spec, it MUST:

1. Call `getAccessibleAtlassianResources` once per session to cache the cloudId.
2. Call `createJiraIssue` for the Epic.
3. For each user story in the spec, call `createJiraIssue` for the Story.
4. Append to the spec file's header:
   ```
   **Jira Epic**: [VIS-### — Feature NNN](https://nexcognit.atlassian.net/browse/VIS-###)
   ```
5. If Atlassian is unreachable, write `**Jira Epic**: (sync failed, retry via /speckit-sync-jira)` and do NOT fail the spec write — the spec is more important than the sync.

When an agent runs `/speckit-tasks`, after writing `tasks.md`, it MUST:

1. Create Jira Tasks in a single batched-feel loop (sequential calls are fine; avoid inventing a batch API).
2. Insert the Jira issue key into a right-column of the tasks.md table, updating the checklist lines in-place once known.

---

## Exception: small work

Work smaller than ~30 minutes (typo fixes, doc tweaks, config nudges, dependency bumps) MAY skip Jira (FR-015). Such PRs MUST:

- Use a Conventional Commit subject with no `VIS-###` token.
- Use the `no-jira` PR label so the `ops-guard` PR-title rule allows the missing key.

The `no-jira` escape hatch is audited: a monthly report lists all `no-jira`-labeled PRs. If the count trends > 20 % of PRs, the 30-minute threshold is re-calibrated.

---

## Failure modes and fallbacks

| Failure | Fallback |
|---|---|
| Atlassian MCP unavailable | Agent writes the spec/tasks to disk; appends `(sync failed, retry via /speckit-sync-jira)` to the spec header; no retry loop on-failure. |
| `createJiraIssue` returns 400 (invalid fields) | Agent surfaces the error verbatim; engineer fixes the inputs (usually a stale cloudId) and re-runs. |
| Smart Commits transition doesn't fire | Engineer manually transitions via Jira web UI; adds the PR URL as a comment. |
| PR merged without a `VIS-###` reference and not `no-jira`-labeled | `ops-guard` blocks the PR from merging. |
