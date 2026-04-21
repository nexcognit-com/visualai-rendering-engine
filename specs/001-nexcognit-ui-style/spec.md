# Feature Specification: VisualAI UI Style — Nexcognit Design Language

**Feature Branch**: `001-nexcognit-ui-style`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "use the UI style of https://www.figma.com/design/vCRMMVtCGSvNrL95dBEPQA/Onboarding-Nexcognit-Agent-Wise--AEID-Changes-?node-id=1-110&t=uycMozzqaiNIiWzK-0"

## Overview

This feature adopts the visual design language used in the referenced Nexcognit "AI Agent Onboarding" Figma frame as the official UI style for the VisualAI product frontend. The feature delivers a design-system foundation (color palette, typography scale, surface hierarchy, and a small set of reusable component patterns: stepper, card, button, input) that every VisualAI screen — Dashboard, Creation Wizard, Asset Library, Billing, Onboarding — consumes.

This spec **replaces** the color and typography choices previously stated in §7.1 of the VisualAI Master Product Specification (dark-navy + neon-yellow + Syne/Inter). The Figma is the authoritative visual source of truth from this point forward.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-time user recognizes VisualAI as a coherent premium product (Priority: P1)

A marketing lead who has never seen VisualAI before opens the app. Within the first three seconds, the combination of dark slate canvas, elevated cards, blue accent, and clean Roboto typography signals that this is a modern, professional, enterprise-grade tool — not a generic open-source video utility. They feel confident spending money here.

**Why this priority**: First-impression credibility is the entire reason to invest in a design system. Without a consistent premium feel, the conversion from free trial to paid plan drops sharply. Every downstream screen leans on these tokens.

**Independent Test**: Recruit 5 people who have never seen VisualAI. Show them a screenshot of the Dashboard for 3 seconds. Ask them to rate trustworthiness on a 1–10 scale. Average score MUST be ≥ 7 to pass.

**Acceptance Scenarios**:

1. **Given** a user loads any VisualAI page, **When** the page renders, **Then** the background is a near-black dark slate (`#020617`), cards sit on a slightly-lighter slate (`#0F172A`), and the primary action uses Dodger Blue (`#3B82F6`).
2. **Given** a user scans the Dashboard, **When** they look at the headings, **Then** all headings use Roboto Bold at 30 px (H1) or Roboto SemiBold at 20 px (H3) with white text; body copy uses Roboto Regular 14 px in a muted slate-grey (`#94A3B8`).
3. **Given** a user compares three different screens in VisualAI, **When** they note the visual treatment, **Then** the same color tokens, border radius (8 px for buttons, 12 px for large cards), border color (`#334155`), and 1 px border weight appear consistently on every surface.

---

### User Story 2 - User completes a multi-step flow with clear progress feedback (Priority: P1)

A user starts any multi-step flow (Creation Wizard for a short marketing video, onboarding sign-up, or agent configuration). At the top of the flow they see a numbered stepper showing all steps with clear visual distinction between the completed, current, and upcoming states, plus a thin progress bar underneath.

**Why this priority**: Multi-step flows are the product's core interaction — every Agent Mode wizard uses one. Users abandoning mid-flow because they lose track of "where am I?" directly costs revenue.

**Independent Test**: Show a user a stepper at state 3-of-7. Ask: "Which step are you on, which have you completed, and how many remain?" 100% of users MUST answer correctly without hesitation.

**Acceptance Scenarios**:

1. **Given** a user enters a flow of N steps, **When** the stepper renders, **Then** a row of N circles appears, each circle 44 px diameter, evenly spaced, with the step number inside and a short label beneath.
2. **Given** the user is on step K, **When** they look at the stepper, **Then** circle K has a Dodger Blue fill with a blue-glow shadow and its label is bold white; circles 1..K-1 show a completed state (filled with check or blue fill retained); circles K+1..N show a dark-slate fill (`#1E293B`) with a slate border (`#475569`), white number, and muted slate-400 label.
3. **Given** the user advances to step K+1, **When** the transition occurs, **Then** the thin progress bar below the stepper animates its blue fill to `(K / (N-1)) × 100%` of full width over ≤ 250 ms.

---

### User Story 3 - User picks one option from a grid of choices (Priority: P2)

A user faces a grid of mutually-exclusive options (e.g., "Select Your Business Type", "Choose an Agent Mode", "Pick a voice"). Each option is a tappable card with an icon, a bold title, and a short description line. Hovering a card shows a subtle elevation and border highlight. Clicking selects it and visibly marks the selection.

**Why this priority**: Option-grid is the second most-used interaction pattern after the stepper. Every mode-selector, voice-picker, music-picker, and template-picker in VisualAI uses this. Scanning a grid of 6–12 options should take ≤ 5 seconds.

**Independent Test**: Present a user with a grid of 10 options and ask them to pick one matching a verbal description. Time-to-selection MUST be ≤ 5 seconds for 80% of users.

**Acceptance Scenarios**:

1. **Given** a 2-column grid of option cards renders, **When** the user looks at it, **Then** each card has an 8 px radius, 1 px slate border (`#334155`), a centered icon (32 px) on top, a SemiBold 14 px title, and a Regular 12 px description in muted slate-grey, with 8 px vertical spacing between icon, title, and description.
2. **Given** the user hovers a card, **When** the hover fires, **Then** the border color shifts from `#334155` to Dodger Blue within 150 ms and an optional subtle drop shadow appears.
3. **Given** the user clicks a card, **When** selection commits, **Then** the card's border becomes Dodger Blue, its background lightens to `#1E293B`, and its title text becomes white. Only one card in the group shows the selected state at a time.

---

### Edge Cases

- **Long option labels**: Card titles up to 30 characters MUST wrap to two lines without shifting neighboring cards' heights; a 10-card grid MUST keep uniform row heights.
- **Small viewports (≤ 768 px wide)**: The 2-column option grid collapses to a single column; the stepper collapses to a horizontally-scrollable strip or a compact "Step K of N" indicator with the current step label only.
- **Step overflow**: Flows with more than 7 steps MUST either chunk into sections or switch to a compact numeric "Step K of N" indicator to avoid cramping the row.
- **Reduced-motion preference**: Progress-bar animation and hover transitions MUST be disabled when the user's OS reports `prefers-reduced-motion: reduce`.
- **Color-blind users**: Selected-vs-unselected state MUST NOT rely on blue color alone; a visible border-width change or a check glyph MUST also appear.
- **Hard-to-read text on mid-slate backgrounds**: All body text on `#1E293B` or `#0F172A` surfaces MUST pass WCAG AA contrast (≥ 4.5:1 for body, ≥ 3:1 for large text).

## Requirements *(mandatory)*

### Functional Requirements

#### Design Tokens

- **FR-001**: System MUST define a color palette with exactly these named tokens and values:
  - Page background: `#020617`
  - Card background: `#0F172A`
  - Elevated / hover surface: `#1E293B`
  - Divider / subtle border: `#334155`
  - Strong border: `#475569`
  - Primary text: `#FFFFFF`
  - Muted text: `#94A3B8`
  - Primary accent: `#3B82F6`
  - Primary accent at 20 % opacity (for progress-bar track, subtle highlights): `#3B82F633`
- **FR-002**: System MUST use Roboto as the sole UI typeface, loaded with weights 400 (Regular), 500 (Medium), 600 (SemiBold), and 700 (Bold). No secondary or display typeface.
- **FR-003**: System MUST define a typography scale with exactly these semantic tokens:
  - H1: 30 px, Bold, 36 px line height
  - H3: 20 px, SemiBold, 28 px line height
  - Section title: 16 px, SemiBold, 16 px line height, letter-spacing −0.4 px
  - Body: 14 px, Regular, 20 px line height
  - Small / hint: 12 px, Regular, 16 px line height
  - Button label: 14 px, SemiBold, 20 px line height
- **FR-004**: System MUST define spacing tokens at 4, 8, 16, 24 px and a single 1 px stroke weight for all borders.
- **FR-005**: System MUST use these border-radius tokens: 8 px for buttons and option cards, 12 px for large content cards, and a fully-rounded pill (≥ 999 px) for stepper circles and progress bars.

#### Component Patterns

- **FR-006**: System MUST provide a **Stepper** component supporting 2–7 steps with: numbered circles, labels underneath, three visual states (upcoming, current, completed), and a thin animated progress bar below the row indicating `(currentStep / (totalSteps - 1))` of total width.
- **FR-007**: System MUST provide a **Content Card** (large container) with 12 px radius, 1 px subtle border, subtle drop shadow, and 24 px internal padding on all sides.
- **FR-008**: System MUST provide an **Option Card** (grid item) with icon + title + description, hover and selected states per User Story 3, and uniform sizing across a grid.
- **FR-009**: System MUST provide a **Primary Button** with Dodger Blue fill, white SemiBold label, 8 px radius, and a visible focus ring for keyboard users.
- **FR-010**: System MUST provide a **Secondary / Ghost Button** with transparent fill, 1 px subtle border, muted label, and a hover state that shifts to elevated-slate background.
- **FR-011**: System MUST provide **Text Input** and **Textarea** with dark-slate fill, 1 px subtle border, white text, muted placeholder, and a blue border + subtle blue glow on focus.
- **FR-012**: System MUST provide a **Select / Dropdown** with visual parity to text input at rest, and an open state that mirrors option-card styling.
- **FR-013**: System MUST use the Lucide icon set exclusively; icon default stroke width 1.5–2, size 16/20/24/32 px depending on context. **No emojis anywhere in the UI.**

#### Accessibility & Responsiveness

- **FR-014**: All interactive elements MUST expose a visible focus ring (2 px Dodger Blue outline with 2 px offset) that appears on keyboard focus.
- **FR-015**: Every text-on-background pair used in the UI MUST meet WCAG 2.1 AA contrast.
- **FR-016**: All hover and transition animations MUST respect `prefers-reduced-motion: reduce`.
- **FR-017**: The design system MUST render correctly on viewports from 360 px to 1920 px wide; specific responsive behaviors for the Stepper and Option Grid are defined in Edge Cases above.
- **FR-018**: The design system MUST NOT depend on a light-mode variant for initial rollout. Dark mode is the sole supported theme.

### Key Entities

- **Design Token**: A named, semantically-purposed visual value (color, type, spacing, radius, stroke). Consumed by every component; single source of truth for the entire frontend.
- **Component Pattern**: A reusable UI building block defined by its token set, interaction states (default / hover / focus / active / disabled / selected), and layout rules. The seven component patterns listed in FR-006 through FR-013 are the initial catalog.
- **Screen Composition**: A page assembled from component patterns — e.g., the Dashboard composes a Sidebar + Content Card + Option Card grid; the Creation Wizard composes a Stepper + Content Card + form inputs + Primary Button. Screen compositions live downstream of this spec.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user rates the product ≥ 7 / 10 on "looks trustworthy and professional" within 3 seconds of first page load (validated in User Story 1 test).
- **SC-002**: Any two VisualAI screens placed side-by-side pass a visual-consistency review: same palette, same typography, same radius, same spacing rhythm. Review passes if a design reviewer cannot identify more than 1 inconsistency per screen pair.
- **SC-003**: 100 % of text on the app passes WCAG 2.1 AA contrast, verified by an automated accessibility scan on every deployed preview.
- **SC-004**: Users complete a 4-step wizard in ≤ 90 seconds on average, and do not report confusion about their position in the flow in post-task interviews (0 / 5 users flag "I lost track of where I was").
- **SC-005**: Users locate and select a target option from a 10-card grid in ≤ 5 seconds (80 % of users), validated in User Story 3 test.
- **SC-006**: A keyboard-only user can complete any primary flow (Dashboard → Mode selection → Wizard → Generate) without visual confusion about focus state on any element.
- **SC-007**: Every token and component pattern is used in at least one shipped screen within two sprints of this spec landing; unused tokens or patterns are removed (avoiding dead design).

## Assumptions

- The Figma frame at node `1:110` is the authoritative reference. If the Figma file is updated, this spec MUST be updated in the same PR and re-ratified.
- Roboto is permitted by the VisualAI product (Apache 2.0 license); no custom font procurement is required.
- Dark mode only: a light-theme variant is out of scope for this spec and will be covered by a separate future spec if demanded by customers.
- This spec governs the VisualAI frontend application (Layer 1 per Master Spec §4). The rendering-engine repo (this repo, Layer 3) does not consume these tokens directly; the Streamlit WebUI, if retained during transition, is NOT required to adopt this style and may be deprecated after the Next.js frontend ships.
- Replacement of Master Spec §7.1 is intentional and approved by the feature author. The Master Spec document MUST be updated (in a separate PR) to cite this spec as the authoritative visual reference.
- Lucide icon set is permitted (ISC license) and is the sole icon source for the VisualAI frontend.
- The Figma's 7-step "Nexcognit AI Agent Onboarding" flow is a REFERENCE for visual style only. VisualAI's own step sequences (Creation Wizard for Mode 2 has 4 steps; Sign-up onboarding has TBD steps) are independent and will be defined by their own feature specs.
