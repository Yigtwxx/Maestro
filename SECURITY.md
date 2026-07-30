# Security Policy

Maestro asks users to paste an API key — a bearer credential that can spend their money —
into a web form. We take that seriously, and we would rather be believed than impressive.

## Supported versions

Maestro is pre-1.0 and under active development. Only the `main` branch receives security
fixes. There are no maintained release branches, and no backports to tagged versions.

| Version | Supported |
| --- | --- |
| `main` | ✅ |
| Anything else | ❌ |

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for a security vulnerability.**

Report it privately, one of two ways:

1. **GitHub private vulnerability reporting** — use the *Report a vulnerability* button
   under the repository's **Security** tab. This is the preferred channel.
2. **Email** — <yigiterdogan023@gmail.com>, with enough detail to reproduce the issue.

Please include the affected component, reproduction steps, the impact you believe it has,
and any proof-of-concept you have. If you can, tell us which commit you tested against.

### What to expect

Maestro is maintained by one person in their own time, so please calibrate accordingly:

- We aim to acknowledge a report within **7 days**.
- We aim to give you an assessment and a remediation plan within **30 days**.
- We will tell you when a fix ships, and credit you in the release notes unless you would
  rather stay anonymous.

Please give us a reasonable chance to fix the issue before disclosing it publicly.

## Safe harbor

We will not pursue legal action against anyone who researches in good faith, stays within
their own account, avoids degrading the service for others, and does not access or destroy
another user's data.

## What we do not claim

So that no one reports a bug expecting something we do not offer:

- We hold **no** security certification — no SOC 2, no ISO 27001. We are not audited.
- We have not commissioned an external penetration test.
- **We run no bug bounty programme.** There is no payment for a report.
- Billing currently runs through a **mock payment provider** (`BILLING_LIVE = false`).
  **Do not enter a real card number**, in production or in development. Card-handling
  code is not yet PCI-scoped, and a real PAN entered against the mock provider is a real
  risk you take on yourself — not a vulnerability to report.

No system is perfectly secure, and a small project is no exception.

## Out of scope

The following are known, documented, and not vulnerabilities:

- Missing rate limiting on non-authentication endpoints (Redis-based limiting is on the
  roadmap).
- The mock payment provider accepting any Luhn-valid card number. That is what a mock does.
- Findings from automated scanners with no demonstrated exploit path.
- Reports that require a compromised host, a compromised database, or physical access.
- Social engineering of the maintainer.

## What we protect and how

The short version:

- **BYOK API keys** are encrypted with AES-256-GCM before they touch a disk, never
  returned to the browser, never written to a log — not even at debug level — and never
  exposed to Marketplace agents.
- **Passwords** are hashed with Argon2. Sessions use short-lived JWT access tokens with
  separate refresh tokens. The refresh token is delivered as an `HttpOnly`, `Secure`,
  `SameSite` cookie and never appears in a response body; the access token is held in
  memory by the page and never persisted. Neither reaches `localStorage`, so an XSS
  foothold cannot exfiltrate a durable session. WebSocket connections require the same
  authentication as the HTTP API.
- **User data is isolated by user id** at the query layer in all three stores: PostgreSQL,
  MongoDB, and Qdrant. A retrieval cannot surface another account's memories, by
  construction rather than by convention.
- **Agents are contained** by iteration ceilings, review-loop ceilings, and a per-task
  wall-clock timeout. Untrusted content fetched from the web or read from a document is
  delimited and marked as data. Marketplace submissions are scanned for prompt-injection
  patterns before they go live — treat that as a safety net, not a guarantee.
- **Card PANs are never stored, logged, or returned.** Only brand, last four digits, and
  expiry persist.

The full policy lives in [`CLAUDE.md`](https://github.com/Yigtwxx/Maestro/blob/main/CLAUDE.md) §9, and the user-facing version — with
the reasoning behind each decision — is on the platform's `/security` page.

## Commit provenance

If you are auditing this repository rather than using it, you will want to know how much
the commit history can be trusted. Precisely this much:

- **History is not squashed or collapsed.** Squash merging is disabled repository-wide, so
  a pull request lands as its own commits and none are rewritten into a single one. `merge`
  and `rebase` are the only merge methods `main` accepts.
- **`main` has been protected since 2026-07-12.** Force-pushes and branch deletion are
  blocked, and every change lands through a pull request with required review and status
  checks. **Commits dated before 2026-07-12 were made on an unprotected branch** — nothing
  attests that they were not rewritten before that date, so treat them as the maintainer's
  word rather than as evidence.
- **Commits authored from 2026-07-28 onward are SSH-signed** and show as *Verified* on
  GitHub; release tags from `v0.1.3` onward are signed too. **Everything before that date is
  unsigned**, which means the author name on those commits is asserted, not proven. Verify
  for yourself with `git log --show-signature`.
- **Signatures are not yet enforced by a branch rule.** An unsigned commit on `main` is
  therefore still possible; check rather than assume. Requiring signatures is on the
  roadmap and will be announced here when it lands.

We would rather write this down than let a clean-looking log imply a guarantee it does not
carry.
