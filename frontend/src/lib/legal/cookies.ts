import { LEGAL_ENTITY } from './config';

const { brand, privacyEmail } = LEGAL_ENTITY;

export const COOKIES = `
## The short version

${brand} sets **no cookies at all**, and runs no analytics, no advertising, and no
third-party tracking scripts.

We store two things in your browser's local storage, both of them strictly
necessary to do what you asked us to do. There is nothing here to opt out of,
because there is nothing here that tracks you.

## What we actually store

| Key | What it is | Why | Lifetime |
| --- | --- | --- | --- |
| Access token | A short-lived signed token proving you are signed in | Without it every request would ask for your password again | Until it expires or you sign out |
| Refresh token | A longer-lived token used to get a new access token | Keeps you signed in across reloads | Until you sign out |
| Active task | The id of the task you were last watching | Restores the Architect view after a reload | Until you clear it |
| Cookie notice acknowledgement | A flag recording that you dismissed the notice | So we stop showing it | Until you clear your browser storage |

That is the complete list.

## Why there is no consent banner asking you to accept

Under the EU ePrivacy Directive, the GDPR, and Turkish law, consent is required
before storing information on your device — **unless** that storage is strictly
necessary to provide a service the user explicitly requested.

Keeping you signed in is strictly necessary to provide the service you requested
by signing in. So the exemption applies, and asking you to "accept" it would be
theatre: there is no alternative, and refusing would simply mean you cannot use
your account.

What we show instead is a notice, once, telling you what is stored and why. It has
a dismiss button, not an accept button, because you are not being asked to agree
to anything.

## If that ever changes

If we ever add analytics, product telemetry, or anything else that is not strictly
necessary, we will ask for your consent **before** it runs, with a real choice to
decline and a way to change your mind later. That is a promise about how we will
behave, and it is the reason the consent record in your browser already has a slot
for a decision you have not been asked to make.

## Clearing it

Signing out removes your tokens. Clearing site data in your browser removes
everything listed above, including the notice acknowledgement — after which you
will see the notice once more.

## Related

Our [Privacy Policy](/privacy) covers everything we hold on the server side.

Questions: ${privacyEmail}
`.trim();
