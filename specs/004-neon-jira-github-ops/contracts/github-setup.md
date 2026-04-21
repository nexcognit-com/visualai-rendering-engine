# Contract: NexCognit GitHub Organization & Repository Setup

**Feature**: 004-neon-jira-github-ops
**Consumer**: the founder (or a designated operator) performing the one-time org + repo setup after Step 1 demo.
**Authority**: this document + [spec.md FR-016..022 + US3](../spec.md) + `OPERATIONS.md`.

This contract is a **runbook** executed once after the Step 1 demo signs off. It is idempotent: re-running after success is a no-op.

---

## Prerequisites before running

- Founder has a GitHub account with personal billing attached (or NexCognit Org already created by someone else).
- Founder is authenticated locally with `gh auth status` showing a token that has `admin:org` and `repo` scopes.
- Three local repos exist and are clean: the current clone of `MoneyPrinterTurbo` (Layer 3), `visualai-frontend` (Step 1 output), `visualai-orchestration` (may be empty scaffold).

---

## Step 1: Confirm or create the `nexcognit` organization

```sh
# Check if the org already exists
if gh api orgs/nexcognit >/dev/null 2>&1; then
  echo "nexcognit org exists"
else
  # If you're on a plan that allows org creation via API:
  gh api orgs --method POST -f login=nexcognit -f billing_email='<founder-email>'
fi

# Reconcile any legacy "nextcognit" typo artifact
if gh api orgs/nextcognit >/dev/null 2>&1; then
  echo "WARNING: nextcognit exists; please manually consolidate to nexcognit"
  echo "See OPERATIONS.md > Reconciliation procedures"
fi
```

GitHub may not allow org creation via the REST API on certain plans; in that case create via the web UI once and continue with the rest of this runbook.

### Org-level settings

Configure these once via `gh api -X PATCH orgs/nexcognit` or the web UI:

| Setting | Value |
|---|---|
| Require 2FA | yes |
| Members default permission | Read |
| Private forks allowed | yes |
| Dependabot alerts | enabled |
| Dependabot security updates | enabled |

---

## Step 2: Create `visualai-rendering-engine` as a fork of upstream MPT

**Critical**: this repo MUST preserve the fork parent relationship with `harry0703/MoneyPrinterTurbo` to enable git-native upstream rebases (constitution Principle II).

```sh
# From the local MoneyPrinterTurbo clone
cd ~/path/to/MoneyPrinterTurbo

# Verify current remote points at the upstream fork
git remote -v  # should show origin = <founder>/MoneyPrinterTurbo (if a personal fork)
               # or upstream = harry0703/MoneyPrinterTurbo

# Transfer ownership of the existing personal fork to the nexcognit org,
# or create a fresh fork under the org:

gh repo fork harry0703/MoneyPrinterTurbo \
  --org nexcognit \
  --fork-name visualai-rendering-engine \
  --clone=false

# Update local clone's remote to the new org-owned fork
git remote set-url origin git@github.com:nexcognit/visualai-rendering-engine.git

# Verify fork parent relationship is preserved
gh api repos/nexcognit/visualai-rendering-engine \
  --jq '.parent.full_name'
# Expected output: harry0703/MoneyPrinterTurbo

# Set the upstream remote for future rebases
git remote add upstream git@github.com:harry0703/MoneyPrinterTurbo.git
```

Push any NexCognit-specific commits (e.g., the `OPERATIONS.md`, `ops/`, `.specify/`, `.claude/` additions from this and prior features) to the new `origin main`.

---

## Step 3: Create `visualai-frontend` as a fresh repo

```sh
cd ~/path/to/visualai-frontend

gh repo create nexcognit/visualai-frontend \
  --private \
  --source=. \
  --remote=origin \
  --push \
  --description "VisualAI frontend (Next.js) — Layer 1 per SpecKit feature 001"
```

---

## Step 4: Create `visualai-orchestration` as an empty scaffold

```sh
# Create a temporary directory with initial scaffolding
TMP=$(mktemp -d)
cd "$TMP"
git init -b main
cat > README.md <<'EOF'
# VisualAI Orchestration API

Layer 2 of the VisualAI 5-layer architecture. Empty scaffold; real code lands with
the orchestration feature spec (to be created). Until then, this repo holds only
the OPERATIONS.md redirect and CODEOWNERS.

See [OPERATIONS.md in visualai-rendering-engine](https://github.com/nexcognit/visualai-rendering-engine/blob/main/OPERATIONS.md)
for the canonical ops policy.
EOF

cat > OPERATIONS.md <<'EOF'
# OPERATIONS

See the canonical document:
https://github.com/nexcognit/visualai-rendering-engine/blob/main/OPERATIONS.md
EOF

cat > CODEOWNERS <<'EOF'
* @<founder-github-handle>
EOF

git add .
git commit -m "chore: initialize empty orchestration scaffold"

gh repo create nexcognit/visualai-orchestration \
  --private \
  --source=. \
  --remote=origin \
  --push \
  --description "VisualAI orchestration API (empty scaffold) — Layer 2"
```

---

## Step 5: Apply branch protection to all three repos

The same rule is applied to `main` of each repo. A single helper shell function keeps them in sync:

```sh
protect_main() {
  local repo="$1"
  # One approving review (self-approval allowed in solo-founder phase)
  gh api -X PUT "repos/${repo}/branches/main/protection" \
    -H "Accept: application/vnd.github+json" \
    -f required_status_checks[strict]=true \
    -F required_status_checks[contexts][]="ops-guard" \
    -F enforce_admins=false \
    -F required_pull_request_reviews[required_approving_review_count]=1 \
    -F required_pull_request_reviews[dismiss_stale_reviews]=true \
    -F restrictions=null \
    -F allow_force_pushes=false \
    -F allow_deletions=false \
    -F required_linear_history=true \
    -F required_conversation_resolution=true
}

protect_main "nexcognit/visualai-rendering-engine"
protect_main "nexcognit/visualai-frontend"
protect_main "nexcognit/visualai-orchestration"
```

Note the `enforce_admins=false` line: this is the **solo-founder self-approval relaxation** (FR-019 + US4 edge-case). When hire #2 joins, this line flips to `enforce_admins=true` and a CODEOWNERS update adds required reviewer coverage.

---

## Step 6: Configure required status checks

Each repo's required status checks:

| Repo | Required checks |
|---|---|
| `visualai-rendering-engine` | `ops-guard`, `pytest` |
| `visualai-frontend` | `ops-guard`, `lint`, `typecheck`, `unit`, `e2e-smoke` |
| `visualai-orchestration` | `ops-guard` (others added when Step 2 delivers real code) |

The `ops-guard` check is the CI workflow introduced by this feature; the others come from the per-repo test suites already planned in specs 001, 002, 003.

---

## Step 7: Add CODEOWNERS to each repo

Start simple (solo founder):

```
# CODEOWNERS
* @<founder-github-handle>
```

Expand per-area when hire #2 joins:

```
# rendering engine
/app/                @backend-owner
/ops/                @founder
/specs/              @founder

# frontend (different repo)
/src/components/     @frontend-owner
/src/app/admin/      @founder
```

---

## Step 8: Write the initial `OPERATIONS.md` to `visualai-rendering-engine`

Copy the canonical content from `specs/004-neon-jira-github-ops/data-model.md` §"Artifact: `OPERATIONS.md`" into `OPERATIONS.md` at the repo root. Include all required sections. Commit with a conventional-commits subject:

```
docs(ops): add canonical OPERATIONS.md (feature 004)  VIS-### #done
```

---

## Step 9: Smoke-test the full chain

1. Push a PR to `visualai-rendering-engine` that edits `OPERATIONS.md`.
2. Verify `ops-guard` runs.
3. Add a typo to an `ops/` script; re-push.
4. Verify `ops-guard` fails and the PR is blocked.
5. Fix the typo; re-push.
6. Verify `ops-guard` passes and merge is allowed.
7. Confirm via `gh api repos/nexcognit/visualai-rendering-engine/branches/main/protection --jq .required_status_checks.contexts` that `ops-guard` appears.
8. In Jira, confirm the PR's Smart Commit transitioned the linked `VIS-###` ticket to `Done`.

---

## Post-setup checklist (founder reads `OPERATIONS.md` to confirm)

- [ ] `gh api orgs/nexcognit` returns 200.
- [ ] Three repos exist: `visualai-rendering-engine`, `visualai-frontend`, `visualai-orchestration`.
- [ ] `gh api repos/nexcognit/visualai-rendering-engine --jq .parent.full_name` returns `harry0703/MoneyPrinterTurbo`.
- [ ] Each repo's `main` branch-protection matches the table in [data-model.md](../data-model.md).
- [ ] `OPERATIONS.md` exists in the rendering engine with all required sections; stubs exist in the other two.
- [ ] `.github/workflows/ops-guard.yml` runs on at least one PR and blocks when expected.
- [ ] The Jira project `VIS` exists and a test Smart-Commit transition succeeds.
- [ ] The Neon project `visualai-prod` exists, accessible via MCP.

Once every box is checked, US3's acceptance criteria are satisfied.
