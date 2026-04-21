-- Migration: 0011__credit_adjustments.sql
-- Author: amraeid  |  Date: 2026-04-21  |  Spec: specs/003-admin-credit-panel
-- Depends on: 0010__admin_users.sql (admin_users.id)
--             00NN__users_and_tenants.sql (users.id, tenants.id)
--             00NN__credit_holds.sql (credit_holds.id)   [future credit-ledger-core spec]
-- Reverse-by: DROP TABLE credit_adjustments;
--
-- Purpose: append-only audit trail for every manual credit-affecting action
-- performed by an internal admin. Writes enter the ledger alongside the
-- system-originated credit_transactions rows; balance is derived from the
-- signed sum of both (see 0012). Immutability triggers are installed in 0012.
--
-- Note: role/privilege separation (REVOKE UPDATE/DELETE from visualai_app) is
-- performed by 0001__create-roles.sql. This migration adds no grants; the
-- immutability trigger (0012) is the defense-in-depth backstop.

CREATE TABLE IF NOT EXISTS credit_adjustments (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id      UUID        NOT NULL REFERENCES admin_users(id)  ON DELETE RESTRICT,
    target_user_id     UUID        NOT NULL REFERENCES users(id)        ON DELETE RESTRICT,
    target_tenant_id   UUID        NOT NULL REFERENCES tenants(id)      ON DELETE RESTRICT,

    -- Text-typed enum with CHECK — simpler to reverse than a CREATE TYPE AS ENUM
    -- and avoids coupling to the future credit-ledger-core event_type enum.
    action             TEXT        NOT NULL,
    CONSTRAINT credit_adjustments_action_valid
        CHECK (action IN ('grant', 'deduct', 'set', 'release_hold')),

    -- Signed: + for grant/release_hold, - for deduct, (final − previous) for set.
    amount             INTEGER     NOT NULL,
    CONSTRAINT credit_adjustments_amount_nonzero
        CHECK (amount <> 0),

    reason             TEXT        NOT NULL,
    CONSTRAINT credit_adjustments_reason_min_length
        CHECK (char_length(reason) >= 10),

    -- Non-null only when action = 'release_hold'. FK points at the future
    -- credit_holds table (owned by credit-ledger-core spec).
    related_hold_id    UUID        NULL REFERENCES credit_holds(id) ON DELETE SET NULL,
    CONSTRAINT credit_adjustments_release_hold_has_ref
        CHECK ((action = 'release_hold') = (related_hold_id IS NOT NULL)),

    is_self_grant      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_cross_tenant    BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Pre-computed at write time. Server-side non-negative-balance triggers
    -- (0012) independently verify derived balance across BOTH ledger tables.
    resulting_balance  INTEGER     NOT NULL,
    CONSTRAINT credit_adjustments_resulting_balance_nonnegative
        CHECK (resulting_balance >= 0),

    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-user history queries (US2): newest first.
CREATE INDEX IF NOT EXISTS credit_adjustments_target_user_created_idx
    ON credit_adjustments (target_user_id, created_at DESC);

-- Per-admin activity audits (FR-020, FR-021).
CREATE INDEX IF NOT EXISTS credit_adjustments_admin_user_created_idx
    ON credit_adjustments (admin_user_id, created_at DESC);

-- Fast lookup of flagged rows (self-grant / cross-tenant) for weekly reports.
CREATE INDEX IF NOT EXISTS credit_adjustments_flagged_created_idx
    ON credit_adjustments (created_at DESC)
    WHERE is_self_grant = TRUE OR is_cross_tenant = TRUE;

COMMENT ON TABLE credit_adjustments IS
    'Append-only manual credit-adjustment ledger. Immutability triggers installed in migration 0012.';
COMMENT ON COLUMN credit_adjustments.action IS
    'One of: grant, deduct, set, release_hold. CHECK-constrained; not a native enum for simpler reversal.';
COMMENT ON COLUMN credit_adjustments.amount IS
    'Signed credit delta. Positive for grant/release_hold; negative for deduct; (final − previous) for set.';
COMMENT ON COLUMN credit_adjustments.related_hold_id IS
    'Only populated for action = release_hold. Enforced by check constraint.';
