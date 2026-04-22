# Feature Specification: Settings Menu — runtime-configurable APIs, providers, and defaults

**Feature Branch**: `005-settings-menu`
**Created**: 2026-04-21
**Status**: Draft
**Input**: User description: "all API , settings etc.. meeds to be in a settings menue not hardwired"

## Overview

Every configuration value in VisualAI — provider API keys, default voices, model routing preferences, rate limits, brand defaults, webhook URLs — MUST be manageable from a Settings surface inside the app, not hardcoded in source files or edited via flat config files like `config.toml`.

This feature replaces the current `config.toml`-based configuration with a database-backed Settings store that is:
- **Edited via a UI** (Settings menu in the frontend) by authorized users.
- **Encrypted at rest** for every secret value.
- **Scoped by audience**: system-level (NexCognit internal only), tenant-level (brand + routing defaults per customer), and user-level (personal preferences).
- **Injected per-request** into the rendering engine at Layer 3 — no secrets land in Layer 3's filesystem or source.
- **Auditable**: every write produces an audit entry showing who changed what, when, and why.
- **Testable**: every provider credential has a "Test Connection" action before save.

The `config.toml` file remains supported as a seed/fallback during transition (Step 1 → Step 2) but becomes read-only once the Settings store ships. Post-migration, editing `config.toml` at runtime has no effect.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Internal admin configures provider credentials through the UI (Priority: P1)

A NexCognit engineer needs to update the OpenAI API key after a rotation. They open the VisualAI frontend, navigate to Settings → Providers, paste the new `sk-…` value into the OpenAI field, click **Test Connection** (which hits a trivial OpenAI endpoint and reports success or the exact error), then click **Save**. Live generations immediately start using the new key. No deploy, no SSH, no file edit, no service restart.

**Why this priority**: Today, every credential change requires editing `config.toml` on the host and restarting the backend. This is the #1 friction for testing-phase operations and the #1 risk for production (a sleepy 3 AM rotation that forgets a file edit takes the service down). Removing this friction is foundational for every later step.

**Independent Test**: An internal admin rotates the OpenAI key via the UI and immediately starts a new generation. The generation succeeds with the new key. The old key, if used, now fails. The audit log shows who changed the key, when, and which field.

**Acceptance Scenarios**:

1. **Given** an internal admin is signed in, **When** they open Settings → Providers, **Then** every configurable provider (LLM, TTS, image, video, stock media, subtitle) is listed with its current configured state and a masked value (`sk-…●●●●7Q2`) for any secret field.
2. **Given** the admin pastes a new OpenAI key, **When** they click **Test Connection**, **Then** the system makes one cheap test call (e.g., models list) and shows the result within 10 seconds as either green success + model name, or red error + the exact provider response.
3. **Given** the admin clicks **Save** with a new key, **When** the save completes, **Then** the new value is persisted encrypted at rest, every subsequent generation uses the new key within 60 seconds, and the audit log gains a row with field name, old-value hash, new-value hash, actor, timestamp, and reason note.
4. **Given** the admin tries to save without a reason note, **When** they submit, **Then** the form rejects with "Reason note is required (min 10 characters)."
5. **Given** the Settings store lacks a given provider entry (feature never configured), **When** a generation requires it, **Then** the generation fails with a structured error naming the missing provider and linking to the Settings page — NOT a generic 500.

---

### User Story 2 — Tenant admin customizes brand defaults and routing preferences (Priority: P1)

A marketing agency signs up as a NexCognit tenant. Their brand prefers a specific English voice (e.g., Aria UK), wants Mode 2 videos defaulted to 22 seconds, and wants the Dodger-Blue accent overridden with their client's brand color. The tenant admin opens Settings → Brand + Defaults, picks those values, and saves. Every user in that tenant sees the new defaults on their next generation attempt. The internal-admin-level provider keys remain hidden from tenant admins.

**Why this priority**: Multi-tenancy is a first-class architectural commitment. Tenant admins must be able to customize their experience without touching NexCognit operational settings. The split between system settings (internal admin) and tenant settings (tenant admin) is the main authorization boundary.

**Independent Test**: Two tenants configure different defaults (voice A vs voice B, 22 s vs 45 s). A user in each tenant starts a generation with no overrides. The system applies the correct tenant defaults. Neither tenant sees or can edit the other's settings, nor the system-level provider keys.

**Acceptance Scenarios**:

1. **Given** a tenant admin is signed in, **When** they open Settings, **Then** they see tenant-scoped sections (Brand, Defaults, Notifications) and do NOT see any system-level sections (Providers, Rate Limits, Internal Admins).
2. **Given** a tenant admin changes the default voice, **When** they save, **Then** all future generations in that tenant inherit the new default unless a user or a per-generation override is set.
3. **Given** User A in Tenant 1 and User B in Tenant 2 submit the same subject at the same time, **When** both jobs run, **Then** each uses its own tenant's default voice — no cross-contamination.

---

### User Story 3 — End user overrides per-user preferences where permitted (Priority: P2)

An end user in a tenant wants to pick a different voice than the tenant default, purely for their own generations. They open Settings → My Preferences, pick the override, and save. Only non-secret, non-privileged settings are editable at user level (voice, language, subtitle preference). Provider keys and routing are invisible.

**Why this priority**: Without a user-level layer, every per-user customization becomes a tenant-wide change, which is wrong for agencies managing multiple clients.

**Independent Test**: User A and User B in the same tenant pick different voices. Both submit generations; each gets their chosen voice. The tenant default is unchanged.

**Acceptance Scenarios**:

1. **Given** a user is signed in, **When** they open Settings, **Then** they see only My Preferences (not Brand, not Providers).
2. **Given** a user sets a voice override, **When** they submit a generation, **Then** their user-level voice wins over the tenant default.
3. **Given** a user clears their override, **When** they submit next time, **Then** the tenant default applies again.

---

### User Story 4 — Any admin rotates a credential with a zero-downtime confidence check (Priority: P2)

An admin must rotate a provider credential before an external deadline. They paste the new value, click **Test Connection** (SUCCESS), then **Save**. The system atomically swaps the in-memory cache so in-flight and new requests both see the new key. Old and new keys can both be valid briefly (grace window) if the provider allows; otherwise the swap is instant. The admin can revert to the previous value from an audit-log entry (if they still have it) within 24 hours.

**Why this priority**: Zero-downtime rotation is table stakes for ops maturity. P2 because the basic "paste + save" path (US1) already works; this story adds the reversibility and confidence guarantees.

**Acceptance Scenarios**:

1. **Given** a live generation is mid-flight, **When** an admin rotates the underlying credential, **Then** the live job completes using whichever value was current when it was dispatched; no mid-job swap corrupts the render.
2. **Given** a save succeeded, **When** the admin clicks **Revert** on the previous audit-log row within 24 hours, **Then** the old value is restored (if still decryptable) and a new audit row is written noting the revert.
3. **Given** a save failed the Test Connection, **When** the admin tries to save anyway, **Then** the UI warns them and requires explicit "save without testing" checkbox (audited separately).

---

### Edge Cases

- **Concurrent saves**: Two admins save the same field within the same second. Both audit entries are written in order; the later save wins; the earlier is flagged "superseded by ca-…" in the audit view.
- **Missing required setting at render time**: Generation fails fast with a clear error naming the missing setting and linking to the Settings page. No half-finished render.
- **Provider returns invalid-key on Test Connection but admin saves anyway**: allowed, but requires a "save without valid test" checkbox and produces a WARN-level audit entry.
- **Settings store is briefly unreachable (DB outage)**: the running rendering engine continues using the last values it had cached (≤ 60 seconds old); the Settings UI shows a "Temporarily read-only" banner.
- **Rotating a key while a paid user is mid-generation**: the job completes with the value it had when dispatched; subsequent retries use the new value.
- **Admin tries to set a user-level override for a privileged setting** (e.g., LLM provider): the UI does not present the field; the API also rejects it with 403 if called directly.
- **Legacy `config.toml` still present after migration**: the system ignores it for managed keys and logs a one-time WARN on boot saying "config.toml is deprecated for managed keys — use the Settings menu."
- **Secret value appears in an error message or log line**: redaction is centralized; any write of a known-secret value to logs substitutes a `[REDACTED]` marker.
- **Key copied from password manager includes surrounding whitespace**: saved values are trimmed; no silent mismatch errors.
- **Exporting / backing up settings**: full export is allowed only for internal admins; tenant admins export only their own scope; secrets are exported with a per-export passphrase, never in cleartext.

## Requirements *(mandatory)*

### Functional Requirements

#### Scope + Authorization

- **FR-001**: Settings MUST be organized into three scopes: **system** (visible only to internal admins), **tenant** (visible to tenant admins + internal admins), **user** (visible to the authenticated user + their tenant admin).
- **FR-002**: Every settings field MUST belong to exactly one scope. Fields that affect system-wide behavior (e.g., provider API keys, global rate limits) MUST be system-scoped. Fields that affect a tenant's defaults (e.g., default voice, brand color) MUST be tenant-scoped. Fields for per-user preferences MUST be user-scoped.
- **FR-003**: A user MUST NOT see or write any setting outside their allowed scopes, verified by server-side authorization on every request.

#### Provider Configuration

- **FR-004**: Settings MUST cover, at minimum: LLM provider(s) + API key(s); TTS provider(s) + API key(s); image provider(s) + API key(s); video provider(s) + API key(s); stock-media provider(s) + API key(s); subtitle provider.
- **FR-005**: Every provider entry MUST support **Test Connection** — a cheap provider-specific call — with a result returned within 10 seconds.
- **FR-006**: Provider entries MUST support activation/deactivation without deleting the credentials; deactivated providers are not selected by the router.
- **FR-007**: The primary provider per category MUST be designated by the admin; the router falls back in a documented order when the primary is unavailable.

#### Defaults & Preferences

- **FR-008**: Tenant-scope settings MUST include at minimum: default voice, default Agent Mode, default aspect ratio, default language, default music preference, brand accent color (for frontend theming overrides per tenant).
- **FR-009**: User-scope settings MUST include at minimum: voice override, language override, subtitle on/off override.
- **FR-010**: A generation request MUST resolve its effective settings by a documented precedence: explicit per-request value > user override > tenant default > system default.

#### Secret Handling

- **FR-011**: Every secret value (API key, webhook secret, integration token) MUST be encrypted at rest using a key managed by a secret-management mechanism (e.g., Neon `pgcrypto` with a key from environment, or an external KMS).
- **FR-012**: Secrets MUST be masked by default in the UI; revealing a value requires an explicit click with an audit entry. The cleartext value MUST NOT transit in server logs, frontend logs, or telemetry.
- **FR-013**: A saved secret MUST only ever be modified by replacement; the read path for admins returns a masked value (`last 4 chars`). Full cleartext exists only in the in-memory decrypt step for outgoing provider calls and in the explicit "reveal" flow.
- **FR-014**: Secrets stored in Settings MUST be redacted from stack traces, error messages, and audit-log display fields.

#### Layer 3 Integration (this repo's constraint)

- **FR-015**: The rendering engine (Layer 3, this repo) MUST NOT read settings from the Neon database directly. Secrets and configuration values MUST arrive at Layer 3 via either (a) environment variables injected at process boot, or (b) per-request headers/body fields populated by the Orchestration API (Layer 2).
- **FR-016**: During the transition from Step 1 (`config.toml`) to Step 3+ (Settings-store-backed), the rendering engine MUST fall back to `config.toml` values ONLY for settings that have not been migrated, and MUST log a WARN-level event noting the fallback.
- **FR-017**: Once all settings are migrated, `config.toml` MUST be reduced to a minimal bootstrap file (DB connection string, port, listen host); all user-configurable values MUST live in the Settings store.

#### UX + Editability

- **FR-018**: Every write operation MUST require a reason note of ≥ 10 characters, enforced both client-side (form validation) and server-side (API validation).
- **FR-019**: The Settings surface MUST provide **Test Connection** for every provider credential, with a clear success/failure result within 10 seconds.
- **FR-020**: Changes MUST take effect within 60 seconds of Save (accounting for a bounded in-memory cache refresh). The UI MUST surface the "effective from" timestamp.
- **FR-021**: A Settings change MUST NOT require a service restart or redeploy to take effect.

#### Audit & Change History

- **FR-022**: Every write to any setting MUST produce an immutable audit entry with: actor (user ID + email), timestamp (UTC, ms precision), scope, field name, hashed old value, hashed new value, reason note, source (UI / API / migration), result (success / failed validation / failed save).
- **FR-023**: Audit entries MUST be viewable by admins in the same scope as the setting (tenant admins see tenant writes; internal admins see all).
- **FR-024**: Revealing a secret value in the UI MUST produce an audit entry with WARN-level visibility.
- **FR-025**: Attempts to write out-of-scope MUST be audited as security events.

#### Operational / Migration

- **FR-026**: The feature MUST ship with a migration script that reads the current `config.toml` and seeds the Settings store with matching system-level values on first run, producing a one-shot audit row per seed.
- **FR-027**: Post-migration, the system MUST emit a boot WARN if `config.toml` still contains managed values other than bootstrap.
- **FR-028**: The Settings store MUST export to a JSON document (redacted by default; secrets require passphrase-wrapped export) so backups and environment-to-environment migrations are possible.

### Key Entities

- **Setting**: A single configuration value. Attributes: id, scope (system/tenant/user), scope_ref (tenant_id or user_id; null for system), field_key, is_secret (boolean), value_encrypted (text), value_hash (text; for audit without decryption), updated_at, updated_by_user_id, is_active.
- **Provider Config**: A grouping of settings for one external provider (LLM/TTS/image/video/stock/subtitle). Attributes: id, category, provider_name, priority_order, is_primary, is_active, associated Setting IDs for its credentials.
- **Settings Audit Entry**: Immutable row. Attributes per FR-022.
- **Test Connection Result**: Transient record (not persisted). Attributes: provider, timestamp, success boolean, latency_ms, error_message (on failure), model_or_account_identifier (on success).
- **Effective Setting**: Derived, not stored — the resolved value for a given (user, tenant, field_key) tuple per the precedence in FR-010.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of previously hardcoded configuration values present in `config.toml` (as of the migration) are editable via the Settings UI within the first week of the feature's launch.
- **SC-002**: An internal admin can rotate any provider API key end-to-end (open Settings → Test → Save → verify new key is used) in under 90 seconds for 95% of rotations.
- **SC-003**: 100% of settings writes produce an audit entry; verified by a reconciliation query on every deploy.
- **SC-004**: 0 incidents of a secret value appearing in application logs, error messages, or telemetry across the first 90 days, verified by a continuous log-redaction scanner.
- **SC-005**: A tenant admin configuring their tenant defaults cannot read, write, or enumerate any system-scoped settings or any other tenant's settings, verified by an automated authorization test matrix on every deploy.
- **SC-006**: After a credential rotation with Save, ≥ 95% of new generation requests use the new credential within 60 seconds; 100% within 5 minutes.
- **SC-007**: 0 service restarts required to apply any managed-settings change across the first 90 days.
- **SC-008**: `config.toml` at the repo root contains ONLY bootstrap values (DB URL, listen port/host) and documentation after migration; grep for any managed-key pattern (`*_api_key`, `*_base_url`, etc.) in the migrated `config.toml` returns zero results.

## Assumptions

- The Settings store is a **new database table set** owned by a future Settings-feature implementation in Layer 4 (Neon PostgreSQL), fronted by Layer 2 (Orchestration API) endpoints. Layer 3 (this repository, per constitution Principle I) does NOT host the store, does NOT perform CRUD on it, and only receives resolved effective values at request time.
- "Internal admin" is the same role defined in spec 003 (admin-credit-panel) — a distinct `admin_users` registry separate from tenant-level admin.
- The first iteration does not require a Key Management Service (KMS). Encryption at rest uses Neon's `pgcrypto` extension with a key stored in the Layer 2 environment (rotatable). KMS adoption is a later feature; the interface is designed so swapping from pgcrypto to a KMS is one implementation swap without Settings data changes.
- Legacy `config.toml` remains supported during Step 1 → Step 3 transition. Once Step 3 migration runs, `config.toml` is shrunk to bootstrap-only; a boot-time linter flags any managed keys still present.
- The Settings UI reuses the design tokens + component catalog established in spec 001 (`nexcognit-ui-style`): `ContentCard`, `Input`, `Select`, `Button`, and state banners.
- Settings scopes (system, tenant, user) align with the multi-tenant model from VisualAI Master Spec §6: system settings apply to all; tenant settings override defaults for that tenant only; user settings override tenant defaults for that user only.
- "Test Connection" for each provider uses the cheapest available provider endpoint (e.g., `models.list` for OpenAI, `/v1/voices` for ElevenLabs); the exact endpoint per provider is a planning-phase detail.
- Audit entries for Settings writes live in the same ledger table as admin-credit-panel audit entries (spec 003) OR a dedicated `settings_audit` table — decided at plan time; the user-visible behavior is identical either way.
- User-scope preferences are NOT required for feature parity with the current `config.toml`. They land in a follow-up milestone after system + tenant scopes ship. US3 is explicitly P2 for this reason.
- For Step 1 (the Mode 2 MVP currently running), `config.toml` remains the configuration source. This spec defines the Step 3+ target; it is NOT a blocker for tonight's demo.
- The Settings UI is implemented in the existing VisualAI frontend repository (spec 001 tokens), NOT in the Streamlit WebUI, which continues to be a deprecated transitional surface.
- Environment variables retain a role for machine-level configuration that cannot live in the DB (e.g., the DB connection string itself, the encryption key). Settings covers everything else.
