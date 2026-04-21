-- Migration: 0010__admin_users.sql
-- Author: amraeid  |  Date: 2026-04-21  |  Spec: specs/003-admin-credit-panel
-- Depends on: 00NN__users_and_tenants.sql (from future credit-ledger-core spec)
--             — requires `users.id UUID PK` to exist.
-- Reverse-by: DROP TABLE admin_users;
--
-- Purpose: registry of internal NexCognit staff authorized to operate the
-- Admin Credit Panel. Orthogonal to users.role (tenant-level roles:
-- Admin/Editor/Viewer). A row here grants panel access; NO row here means
-- no panel access, regardless of tenant role. See spec 003 FR-001.

CREATE TABLE IF NOT EXISTS admin_users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID        NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    granted_by     UUID        NULL     REFERENCES users(id) ON DELETE SET NULL,
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grant_reason   TEXT        NOT NULL,

    -- FR-011(a)+(b): grant_reason ≥ 10 chars. Bootstrap/seed rows MAY use
    -- a documented system tag (e.g. "bootstrap_initial_admin") per data-model.md;
    -- all such tags satisfy the length check by convention.
    CONSTRAINT admin_users_grant_reason_min_length
        CHECK (char_length(grant_reason) >= 10),

    -- Research Q1: granted_by != user_id for non-bootstrap rows.
    -- Bootstrap rows use granted_by = NULL, so allow NULL OR distinct.
    CONSTRAINT admin_users_not_self_granted
        CHECK (granted_by IS NULL OR granted_by <> user_id)
);

-- Fast auth check: lookup active admin row by user_id in O(log n).
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_user_id_active_idx
    ON admin_users (user_id)
    WHERE is_active = TRUE;

-- Per-admin activity audit queries.
CREATE INDEX IF NOT EXISTS admin_users_granted_by_idx
    ON admin_users (granted_by)
    WHERE granted_by IS NOT NULL;

COMMENT ON TABLE admin_users IS
    'Internal NexCognit staff authorized to operate the Admin Credit Panel. Orthogonal to users.role. See spec 003.';
COMMENT ON COLUMN admin_users.granted_by IS
    'User who elevated this admin. NULL only for bootstrap rows seeded via migration.';
COMMENT ON COLUMN admin_users.grant_reason IS
    'Justification text (min 10 chars) OR a documented system tag (e.g. "bootstrap_initial_admin") for migration-seed rows.';
