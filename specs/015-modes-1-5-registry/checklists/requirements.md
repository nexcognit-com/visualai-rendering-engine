# Specification Quality Checklist: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-03
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs) — except where the deliverable IS architecture (e.g., the modes registry as `app/services/modes/`, Layer 2.5 as a new package). The build plan + constitution explicitly mandate these locations; spec 015 inherits rather than re-decides.
- [X] Focused on user value and business needs (US1 + US2 are user-visible; US3 + US4 are non-regression / future-proofing).
- [X] Written for non-technical stakeholders — engineering jargon limited to the architecture sections where it's load-bearing.
- [X] All mandatory sections completed.

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain (4 inline clarifications were resolved as documented assumptions per the spec template guidance).
- [X] Requirements are testable and unambiguous.
- [X] Success criteria are measurable.
- [X] Success criteria are technology-agnostic (no specific framework names in success measures; concrete numeric metrics only).
- [X] All acceptance scenarios are defined.
- [X] Edge cases are identified (10 edge cases enumerated).
- [X] Scope is clearly bounded — Modes 3 + 4 explicitly out, Veo / Kling / Luma video generation explicitly out, Layer 4 signed-URL CDN explicitly out.
- [X] Dependencies and assumptions identified (12 assumptions documented).

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria.
- [X] User scenarios cover primary flows (Mode 5 + Mode 1 + Mode 2 non-regression + extensibility test).
- [X] Feature meets measurable outcomes defined in Success Criteria.
- [X] No implementation details leak into specification beyond what the architecture deliverable inherently requires.

## Notes

- Spec 015 is genuinely large — 4 user stories, 31 functional requirements, 8 success criteria, 12 assumptions. Two reasons:
  1. Step 3 of the build plan is itself multi-deliverable (2 new modes + 2 architectural debt burndowns + Layer 2.5 introduction).
  2. Each deliverable has its own user-facing or contract-facing acceptance criteria.
- Plan phase MAY decide to slice this into multiple smaller PRs (e.g., Mode 5 + registry + material.py rewrite as PR-A, Mode 1 + Layer 2.5 as PR-B). The spec captures the unified intent; the plan defines the landing strategy.
- The Mode 2 hybrid debt-#3 carve-out is intentionally split: `Auto` path retires (routes through Layer 2 pre-signed URLs), Mode 5 path is the constitution's permitted exception, hybrid path remains in Layer 3 awaiting a Step 3.5 follow-up. This is documented in FR-024 + assumption #3.
- 4 [NEEDS CLARIFICATION]-worthy decisions surfaced during drafting and were resolved with documented assumptions: (a) image-gen provider = NanoBanana Pro with provider-agnostic contract, (b) Layer 2's "pre-signed URLs" = local file mount in Step 3 with Step-4 path open, (c) per-tenant cost tracking = log-only Step 3, (d) NanoBanana response shape = either 3×2 contact sheet or 6 individual images, normalize at the contract boundary.
