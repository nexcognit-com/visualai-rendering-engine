# Contract: SSRF Protection

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 6](../data-model.md)

The exhaustive refusal rules for `assertSafeUrl(url)` plus the acceptance test set that verifies SC-006 ("100% of attempts to fetch loopback / private-IP / non-HTTP scheme targets are refused").

This contract is non-negotiable — it's a security floor, not a configuration option. NO override toggle.

## Refusal rules

The function `assertSafeUrl(url: string): Promise<void>` lives in `visualai-frontend/src/lib/ssrf.ts`. It throws `SsrfError(code, ...details)` on any blocked target. The full rule set:

### Rule 1 — URL parseable

| Trigger | Throws |
|---|---|
| `new URL(input)` throws (invalid format, missing scheme, etc.) | `SsrfError("url_invalid", input)` |

### Rule 2 — Scheme allowlist

| Allowed schemes | `http:`, `https:` |
| Blocked schemes (examples; everything not allowed is blocked) | `file:`, `data:`, `javascript:`, `gopher:`, `ftp:`, `chrome:`, `chrome-extension:`, `view-source:`, `blob:`, `about:` |
| Throws | `SsrfError("scheme_blocked", scheme)` |

### Rule 3 — Hostname literal IP check

If hostname is an IP literal (IPv4 or IPv6), check it directly without DNS lookup:

| Range | CIDR | Throws |
|---|---|---|
| IPv4 loopback | `127.0.0.0/8` | `SsrfError("loopback")` |
| IPv6 loopback | `::1/128` | `SsrfError("loopback")` |
| IPv4 link-local | `169.254.0.0/16` | `SsrfError("link_local")` |
| IPv6 link-local | `fe80::/10` | `SsrfError("link_local")` |
| IPv4 private (10.x) | `10.0.0.0/8` | `SsrfError("private_range")` |
| IPv4 private (172.16-31) | `172.16.0.0/12` | `SsrfError("private_range")` |
| IPv4 private (192.168.x) | `192.168.0.0/16` | `SsrfError("private_range")` |
| IPv6 unique-local | `fc00::/7` | `SsrfError("private_range")` |
| IPv4 multicast | `224.0.0.0/4` | `SsrfError("reserved_range")` |
| IPv6 multicast | `ff00::/8` | `SsrfError("reserved_range")` |
| IPv4 unspecified | `0.0.0.0/8` | `SsrfError("reserved_range")` |
| IPv6 unspecified | `::/128` | `SsrfError("reserved_range")` |
| IPv4 reserved | `240.0.0.0/4` | `SsrfError("reserved_range")` |

### Rule 4 — Hostname DNS resolution

If hostname is a domain (not an IP literal):

1. Resolve via `dns.promises.lookup(host, { all: true })`.
2. For EVERY resolved IP, run Rule 3.
3. If ANY resolved IP fails Rule 3 → throw the same `SsrfError`.

This defends against:
- IPv6/IPv4 DNS pinning (attacker resolves a public AAAA + a private A; both must be safe).
- DNS rebinding (we're called once per request; subsequent rebinding doesn't help an attacker because the fetch happens immediately after this check, before the rebind can take effect).

| Trigger | Throws |
|---|---|
| `dns.lookup` rejects (NXDOMAIN, network error) | `SsrfError("dns_failed", host)` |

### Rule 5 — Re-check after redirect

The fetch uses `redirect: 'manual'`. On each `Location` header:

1. Resolve relative URLs against the current URL.
2. Run `assertSafeUrl()` again on the resolved target.
3. Refuse to follow if it throws.

This defends against redirect-to-private-IP attacks where the initial URL is a public domain that 302s to `http://169.254.169.254/...`.

## SsrfError type

```ts
type SsrfErrorCode =
  | "url_invalid"
  | "scheme_blocked"
  | "loopback"
  | "link_local"
  | "private_range"
  | "reserved_range"
  | "dns_failed";

export class SsrfError extends Error {
  constructor(public code: SsrfErrorCode, public details?: string) {
    super(`SSRF blocked: ${code}${details ? ` (${details})` : ''}`);
    this.name = "SsrfError";
  }
}
```

The route handler catches `SsrfError` and returns HTTP 400 with `error_code: "ssrf_blocked"` and a generic detail message. The internal `code` and `details` are logged server-side but NOT returned to the browser (info-leakage protection — don't tell attackers which rule they hit).

## Test fixture set (SC-006 acceptance)

These tests live in `visualai-frontend/tests/ssrf.test.ts`. ALL must throw `SsrfError`:

| Test ID | Input URL | Expected `SsrfError.code` |
|---|---|---|
| SP-1 | `http://localhost` | `loopback` |
| SP-2 | `http://localhost:8080/admin` | `loopback` |
| SP-3 | `http://127.0.0.1` | `loopback` |
| SP-4 | `http://127.0.0.1:5432/` | `loopback` |
| SP-5 | `http://[::1]/` | `loopback` |
| SP-6 | `http://192.168.1.1` | `private_range` |
| SP-7 | `http://10.0.0.1` | `private_range` |
| SP-8 | `http://172.16.0.1` | `private_range` |
| SP-9 | `http://172.31.255.255` | `private_range` |
| SP-10 | `http://169.254.169.254` | `link_local` (the AWS metadata endpoint — most famous SSRF target) |
| SP-11 | `http://[fe80::1]` | `link_local` |
| SP-12 | `http://0.0.0.0` | `reserved_range` |
| SP-13 | `http://255.255.255.255` | `reserved_range` |
| SP-14 | `http://224.0.0.1` | `reserved_range` |
| SP-15 | `file:///etc/passwd` | `scheme_blocked` |
| SP-16 | `data:text/html,<script>alert(1)</script>` | `scheme_blocked` |
| SP-17 | `javascript:alert(1)` | `scheme_blocked` |
| SP-18 | `gopher://example.com/_smtp` | `scheme_blocked` |
| SP-19 | `ftp://example.com/file` | `scheme_blocked` |
| SP-20 | `not a url at all` | `url_invalid` |
| SP-21 | `http://` (no host) | `url_invalid` |

These 21 tests verify SC-006's "100% refusal" criterion.

## Tests for happy-path passes

These MUST NOT throw:

| Test ID | Input URL | Expected |
|---|---|---|
| SP-22 | `https://example.com/` | resolves; passes |
| SP-23 | `https://acmebrew.com/products/cold-brew-kit?utm_source=test` | resolves; passes |
| SP-24 | `http://example.com/` (plain http) | resolves; passes (http is allowed; only blocked-IPs / blocked-schemes refuse) |

## Tests for redirect re-check

| Test ID | Setup | Expected |
|---|---|---|
| SP-25 | URL `https://public.example.com/redirect` returns `302 Location: http://localhost/admin` | `assertSafeUrl(localhost)` throws `loopback` after the first hop; route handler returns `redirect_loop` (or a more specific code at impl phase) |
| SP-26 | URL chain has 6+ public hops | route handler returns `redirect_loop` (separately from SSRF) |

## What this contract does NOT cover

- **Domain blocklists** (e.g., never scrape `competitor.com`) — out of scope. Add per-tenant in Step 2 if needed.
- **TLS verification policy** — handled by Node's default; route returns `tls_error` on cert failure. Same for everyone.
- **HTTP/3 / QUIC** — not in scope; v1 uses Node's default HTTP/1.1 + HTTP/2.
- **WebSocket scraping** — not a thing; we only do HTTP GET.

## Verification

Tests SP-1 through SP-26 are scheduled in `tasks.md` for the implementation phase. They run as part of the Vitest suite — pure unit tests, no external network, fast (<200 ms total).
