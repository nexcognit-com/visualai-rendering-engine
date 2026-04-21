# Contract: Frontend Components

**Feature**: 003-admin-credit-panel
**Layer**: 1 — Frontend at `../visualai-frontend/`
**Consumer**: engineers implementing the panel; downstream features that embed pieces of it.

All components live under `src/components/admin/` in the frontend repo and compose from the design system in spec 001.

---

## `<UserSearch />`

**Purpose**: search box for finding a target user by email prefix, exact email, or UUID.

```ts
export interface UserSearchProps {
  onSelect: (user: AdminUserSearchResult) => void;
  className?: string;
  placeholder?: string;     // default: "Search by email or user ID…"
}

export interface AdminUserSearchResult {
  userId: string;
  email: string;
  tenantId: string;
  tenantName: string;
  role: "Admin" | "Editor" | "Viewer";
  isInternalAdmin: boolean;
  createdAt: string;
  balanceCredits: number;
  activeHoldsCount: number;
}
```

Behavior:
- 300 ms debounce on input changes.
- Backed by `useQuery` to `GET /api/v2/admin/users/search?q=<term>`.
- Shows up to 20 results in a dropdown; each item uses `OptionCard` (spec 001) styling, collapsed layout (no icon; balance as a small badge on the right).
- Keyboard: up/down arrows move focus; Enter selects; Escape closes.

---

## `<BalancePanel />`

**Purpose**: display a single user's balance + metadata + quick-action CTAs.

```ts
export interface BalancePanelProps {
  userId: string;         // drives data fetch
  onAdjustClick: (action: "grant" | "deduct" | "set") => void;
}
```

Renders (uses `ContentCard` from spec 001):
- Header: email, tenant name, internal-admin badge if applicable.
- Big number: `balanceCredits`.
- Sub-line: `availableCredits` / `heldCredits`.
- Three CTAs (primary/secondary buttons): `Grant`, `Deduct`, `Set absolute`.
- Banner if `currentMode = read_only`: shows `<ModeBanner />` on top; CTAs disabled.

Data: `useQuery` to `GET /api/v2/admin/users/{userId}/credits` with 5-second stale time.

---

## `<CreditAdjustmentForm />`

**Purpose**: modal/dialog form for grant / deduct / set-absolute.

```ts
export interface CreditAdjustmentFormProps {
  userId: string;
  action: "grant" | "deduct" | "set";
  currentBalance: number;
  open: boolean;
  onClose: () => void;
  onSuccess: (newBalance: number) => void;
}
```

Form fields:
- Amount (numeric input; grant/deduct ≥ 1; set ≥ 0).
- Reason (textarea; min 10 characters; live character count).
- Preview line: "Balance: 150 → 250 (+100)" computed as user types.
- Primary CTA: `Apply`; secondary: `Cancel`.

Behavior:
- Submit hits `POST /api/v2/admin/users/{userId}/credits/adjust`.
- Large-delta flow: if result delta > 100,000, first submit returns 409 `confirmation_required`; component then shows a second dialog "Are you sure? You're about to grant 500,000 credits" with a manual "Yes, I understand" checkbox. Second submit sends `confirm_large_grant: true`.
- Self-grant guard: if current signed-in admin's user_id matches target user_id, render a red info box `"This is a self-grant. It will be flagged in the audit log."` before Apply is enabled.
- Cross-tenant guard: if admin's tenant differs from target's, render an orange info box with the same intent.
- On success: close dialog, fire `onSuccess`, toast the new balance.
- On 403 `panel_is_read_only`: render an error toast "Panel is in read-only mode. Writes are disabled."

Accessibility:
- Dialog built on Radix `Dialog` primitive.
- Escape closes.
- Initial focus on amount field.
- Error messages announced via `aria-live="assertive"`.

---

## `<HoldReleaseList />`

**Purpose**: show active holds for the target user and allow releasing stuck ones.

```ts
export interface HoldReleaseListProps {
  userId: string;
  onRelease?: (holdId: string, releasedAmount: number) => void;
}

export interface ActiveHold {
  holdId: string;
  amount: number;
  relatedJobId: string;
  createdAt: string;
  expiresAt: string;
  ageSeconds: number;
}
```

Behavior:
- Backed by the same `GET /api/v2/admin/users/{userId}/credits` endpoint; reads `active_holds`.
- Table columns: Hold ID (truncated), Amount, Job Link, Age, Actions.
- Release button opens a confirmation dialog with a reason textarea (10 char min).
- Submitting fires `POST /api/v2/admin/users/{userId}/holds/{holdId}/release`.
- On success: remove row, toast "Released {amount} credits."

---

## `<AuditLogTable />`

**Purpose**: paginated audit log view with filters.

```ts
export interface AuditLogTableProps {
  userId: string;
  pageSize?: number;             // default 50
  initialFilters?: AuditFilters;
}

export interface AuditFilters {
  since?: Date;
  until?: Date;
  actions?: Array<"grant" | "deduct" | "set" | "release_hold" | "hold" | "debit" | "release" | "expire">;
  actor?: "admin" | "system" | string;   // string = specific admin_user_id
}
```

Implementation:
- Built on TanStack Table.
- Columns: Timestamp, Source (admin/system), Action, Amount (colored: green positive, red negative), Resulting Balance, Actor, Reason/Reference, Flags (self-grant, cross-tenant).
- Flagged rows (self-grant, cross-tenant) render with a warning icon in the first column (Lucide `AlertTriangle`).
- Reference column links to related job when `source = system` and `reference` is a job id; to admin user page when `source = admin`.
- Pagination: cursor-based via `GET /api/v2/admin/users/{userId}/audit?cursor=...&limit=...`.
- Filter UI: date range picker, action multi-select, actor select — all collapse into a `ContentCard` above the table.

Accessibility:
- Table has `<caption>` summarizing filters.
- Keyboard navigation: arrow keys for row focus; Enter on a row opens the detail drawer (future enhancement).
- Empty state: `<ContentCard>` with "No audit entries match these filters."

---

## `<ModeBanner />`

**Purpose**: explains the current feature-flag mode at the top of the admin panel.

```ts
export interface ModeBannerProps {
  mode: "full" | "read_only" | "disabled";
}
```

Visual:
- `full` → not rendered.
- `read_only` → yellow/accent-adjacent color banner: "The admin credit panel is in **read-only** mode. Write operations are disabled. Credits now flow through Stripe billing."
- `disabled` → red/destructive banner: "The admin credit panel is **disabled**. This surface will return 404 for non-admins." (Rendered only if an admin somehow reaches the route during the `disabled` state, which is prevented by middleware but defensible in depth.)

---

## Middleware guard (`src/middleware.ts`)

Pre-route check for `/admin/**` routes:

```ts
export async function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/admin/")) {
    const mode = await fetchPanelMode();   // 60 s-cached via TanStack Query equivalent at the edge
    if (mode === "disabled") {
      return NextResponse.rewrite(new URL("/404", request.url));
    }
  }
  return NextResponse.next();
}
```

When `mode === "disabled"`, the middleware rewrites to the 404 page instead of letting the route serve at all. Combined with Layer 2's 404 on `/api/v2/admin/*`, the entire admin panel surface disappears from an outsider's perspective.

---

## Data-fetch hooks summary

| Hook | Endpoint | Stale time |
|---|---|---|
| `useAdminUserSearch(q)` | `GET /api/v2/admin/users/search` | 2 min |
| `useAdminUserCredits(userId)` | `GET /api/v2/admin/users/{userId}/credits` | 5 s |
| `useAdminUserAudit(userId, filters)` | `GET /api/v2/admin/users/{userId}/audit` | 60 s |
| `usePanelMode()` | `GET /api/v2/config/panel-mode` | 60 s |
| `useCreditAdjust()` (mutation) | `POST /api/v2/admin/users/{userId}/credits/adjust` | — |
| `useHoldRelease()` (mutation) | `POST /api/v2/admin/users/{userId}/holds/{holdId}/release` | — |

All mutations invalidate the relevant `useAdminUserCredits` + `useAdminUserAudit` queries on success.

---

## Route map

| Route | Component tree | Auth requirement |
|---|---|---|
| `/admin/credits` | `AdminLayout > UserSearch + (selected user) > BalancePanel + HoldReleaseList + AuditLogTable` | Internal admin only |
| `/admin/credits/user/[id]` | `AdminLayout > BalancePanel + HoldReleaseList + AuditLogTable` (deep-link) | Internal admin only |
| `/404` (on `disabled` mode) | stock Next.js 404 | public |
