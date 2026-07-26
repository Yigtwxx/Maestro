import { LEGAL_ENTITY } from './config';

const { brand, privacyEmail } = LEGAL_ENTITY;

export const COOKIES = `
## The short version

${brand} sets **no cookies at all**, and runs no advertising and no third-party
tracking scripts.

We store a short list of things in your browser's local storage, almost all of
them strictly necessary to do what you asked us to do. The one optional thing —
anonymous, self-hosted visit counting on our public pages — never runs unless
you say yes first, and not every deployment of ${brand} enables it at all.

## What we actually store

| Key | What it is | Why | Lifetime |
| --- | --- | --- | --- |
| Access token | A short-lived signed token proving you are signed in | Without it every request would ask for your password again | Until it expires or you sign out |
| Refresh token | A longer-lived token used to get a new access token | Keeps you signed in across reloads | Until you sign out |
| Active task | The id of the task you were last watching | Restores the Architect view after a reload | Until you clear it |
| Consent record | Your analytics choice, and that you answered the notice | So analytics respects your decision and we stop asking | Until you clear your browser storage |

That is the complete list.

## What we ask consent for

Under the EU ePrivacy Directive, the GDPR, and Turkish law, consent is required
before storing information on your device or tracking you — **unless** it is
strictly necessary to provide a service you explicitly requested.

Keeping you signed in is strictly necessary to provide the service you requested
by signing in. So the exemption applies, and asking you to "accept" it would be
theatre: there is no alternative, and refusing would simply mean you cannot use
your account.

Counting visits to our public pages is **not** necessary. So on deployments that
enable it, the notice asks you a real question before anything runs, with
Reject exactly as easy as Accept — and if you say nothing, the answer is no.

## Analytics, when enabled

Some deployments of ${brand} run [Umami](https://umami.is), an open-source
analytics tool, **self-hosted on the same server as the platform itself**. When
it is enabled and you have consented, here is exactly what that means:

- **Cookieless and anonymous.** It sets no cookies and stores no identifier in
  your browser. Visitors are distinguished by a salted, regularly rotating
  hash, so even we cannot recognise you over time. IP addresses are not stored.
- **First-party only.** The data lives on our own server and never leaves it.
  No third party receives it, and nothing is ever sold.
- **Public pages only.** It counts visits to the marketing pages — the landing
  page, pricing, docs, and pages like this one. It never runs inside the app:
  nothing you do after signing in is measured.
- **What it records.** The page you viewed, the page that referred you, your
  browser, operating system, device type, country, and screen size. No names,
  no emails, no content.
- **Consent-first.** The script does not load — not even to decide whether to
  run — until you accept. Withdrawing consent stops it immediately.

You can change your mind at any time using the control at the bottom of this
page. The change takes effect the moment you make it.

## Clearing it

Signing out removes your tokens. Clearing site data in your browser removes
everything listed above, including your consent record — after which you will
see the notice once more.

## Related

Our [Privacy Policy](/privacy) covers everything we hold on the server side.

Questions: ${privacyEmail}
`.trim();
