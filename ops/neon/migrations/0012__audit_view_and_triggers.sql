-- Migration: 0012__audit_view_and_triggers.sql
-- Author: amraeid  |  Date: 2026-04-21  |  Spec: specs/003-admin-credit-panel
-- Depends on: 0010__admin_users.sql
--             0011__credit_adjustments.sql
--             00NN__credit_transactions.sql  [future credit-ledger-core spec]
-- Reverse-by: see rollback block at end of file.
--
-- Purpose:
--   1. `audit_entries` VIEW unifying system events (credit_transactions) and
--       manual adjustments (credit_adjustments) chronologically (FR-017).
--   2. `user_credit_balance(uuid)` function that derives balance from the
--       signed sum across both tables (FR-016, SC-003).
--   3. Deferred non-negative-balance constraint triggers on BOTH ledger
--       tables (FR-012, SC-008).
--   4. Immutability triggers on BOTH ledger tables (FR-019).

-- =========================================================================
-- 1. Unified audit view
-- =========================================================================

CREATE OR REPLACE VIEW audit_entries AS
SELECT
    'system'::text          AS source,
    ct.id                   AS id,
    ct.user_id              AS user_id,
    ct.tenant_id            AS tenant_id,
    ct.event_type::text     AS action,
    ct.amount               AS amount,
    NULL::uuid              AS admin_user_id,
    ct.related_job_id       AS reference,
    NULL::text              AS reason,
    FALSE                   AS is_self_grant,
    FALSE                   AS is_cross_tenant,
    ct.created_at           AS created_at
FROM credit_transactions ct

UNION ALL

SELECT
    'admin'::text           AS source,
    ca.id                   AS id,
    ca.target_user_id       AS user_id,
    ca.target_tenant_id     AS tenant_id,
    ca.action               AS action,
    ca.amount               AS amount,
    ca.admin_user_id        AS admin_user_id,
    ca.related_hold_id      AS reference,
    ca.reason               AS reason,
    ca.is_self_grant        AS is_self_grant,
    ca.is_cross_tenant      AS is_cross_tenant,
    ca.created_at           AS created_at
FROM credit_adjustments ca;

COMMENT ON VIEW audit_entries IS
    'Unified chronological audit trail combining system-originated credit_transactions with manual credit_adjustments. Read-only by construction.';

-- =========================================================================
-- 2. Derived-balance function
-- =========================================================================

CREATE OR REPLACE FUNCTION user_credit_balance(p_user_id UUID)
RETURNS INTEGER
LANGUAGE sql
STABLE
AS $$
    SELECT
        COALESCE((SELECT SUM(amount)::int FROM credit_transactions WHERE user_id        = p_user_id), 0)
      +
        COALESCE((SELECT SUM(amount)::int FROM credit_adjustments   WHERE target_user_id = p_user_id), 0)
$$;

COMMENT ON FUNCTION user_credit_balance(UUID) IS
    'Signed sum of credit_transactions.amount + credit_adjustments.amount for a user. Authoritative balance source.';

-- =========================================================================
-- 3. Non-negative-balance enforcement (deferred constraint triggers)
-- =========================================================================

CREATE OR REPLACE FUNCTION enforce_non_negative_balance()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target UUID;
BEGIN
    -- NEW.user_id for credit_transactions; NEW.target_user_id for credit_adjustments.
    target := COALESCE(NEW.user_id, NEW.target_user_id);
    IF user_credit_balance(target) < 0 THEN
        RAISE EXCEPTION 'non-negative balance violation for user %', target
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

-- Deferred so holds + debits inside a single transaction settle atomically
-- (see spec 002's preview-gate credit lifecycle).
DROP TRIGGER IF EXISTS non_negative_balance_ct ON credit_transactions;
CREATE CONSTRAINT TRIGGER non_negative_balance_ct
    AFTER INSERT ON credit_transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION enforce_non_negative_balance();

DROP TRIGGER IF EXISTS non_negative_balance_ca ON credit_adjustments;
CREATE CONSTRAINT TRIGGER non_negative_balance_ca
    AFTER INSERT ON credit_adjustments
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION enforce_non_negative_balance();

-- =========================================================================
-- 4. Immutability enforcement (FR-019)
-- =========================================================================

CREATE OR REPLACE FUNCTION raise_immutable_violation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit ledger row % on table % is immutable',
            COALESCE(OLD.id::text, '<unknown>'),
            TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

DROP TRIGGER IF EXISTS credit_adjustments_immutable ON credit_adjustments;
CREATE TRIGGER credit_adjustments_immutable
    BEFORE UPDATE OR DELETE ON credit_adjustments
    FOR EACH ROW
    EXECUTE FUNCTION raise_immutable_violation();

DROP TRIGGER IF EXISTS credit_transactions_immutable ON credit_transactions;
CREATE TRIGGER credit_transactions_immutable
    BEFORE UPDATE OR DELETE ON credit_transactions
    FOR EACH ROW
    EXECUTE FUNCTION raise_immutable_violation();

-- =========================================================================
-- Rollback (manual; comment-only)
-- =========================================================================
--   DROP TRIGGER IF EXISTS credit_transactions_immutable ON credit_transactions;
--   DROP TRIGGER IF EXISTS credit_adjustments_immutable  ON credit_adjustments;
--   DROP FUNCTION IF EXISTS raise_immutable_violation();
--   DROP TRIGGER IF EXISTS non_negative_balance_ca ON credit_adjustments;
--   DROP TRIGGER IF EXISTS non_negative_balance_ct ON credit_transactions;
--   DROP FUNCTION IF EXISTS enforce_non_negative_balance();
--   DROP FUNCTION IF EXISTS user_credit_balance(UUID);
--   DROP VIEW     IF EXISTS audit_entries;
