import { LEGAL_ENTITY } from './config';

const { brand, operatorName, country, contactEmail, governingLaw, jurisdiction } = LEGAL_ENTITY;

export const TERMS = `
## 1. Who we are and what this is

${brand} is an AI agent orchestration platform operated by ${operatorName}, an
individual developer based in ${country} ("we", "us").
These Terms of Service govern your access to and use of ${brand} (the "Service").
By creating an account you accept these Terms. If you do not accept them, do not
use the Service.

We may update these Terms. Material changes will be announced in the product or
by email before they take effect. Continuing to use the Service after a change
means you accept the revised Terms.

## 2. Your account

You must be at least 18 years old, or the age of majority where you live, to
create an account. You are responsible for everything that happens under your
account, including keeping your password secret. Tell us immediately at
${contactEmail} if you believe your account has been compromised.

One person or organisation, one account. Do not share credentials, and do not
create accounts to evade a suspension or to reclaim a promotion you have already
used.

## 3. Bring Your Own Key (BYOK)

${brand} does not resell model inference. You connect your own API keys — OpenAI,
Anthropic, Google, or others — and the Service calls those providers on your
behalf, as your agent.

That means:

- **You pay your providers directly.** Any charges those providers bill you for
  tokens the agents consume are between you and them. We do not mark them up and
  we do not refund them.
- **You accept their terms.** Using a provider through ${brand} does not exempt
  you from that provider's own terms and acceptable use policies.
- **You are responsible for your keys.** We encrypt them at rest with AES-256-GCM
  and never return them to the browser (see the [Security](/security) page), but
  a key you paste into ${brand} is a key you have chosen to entrust to us. Revoke
  it with your provider if you stop using the Service.

A local model is available. It runs a locally hosted open model and calls no
third-party provider, so it adds no provider cost beyond your own compute. On the
hosted Service, running any task — including one driven by the local model —
requires an active subscription.

## 4. Subscriptions, renewals, cancellation and refunds

### 4.1 Plans

The Service is offered on paid monthly plans. There is no free plan and no trial:
you must subscribe to a plan before you can start any task. Current prices and
token quotas are shown on the [pricing page](/pricing) and are authoritative
there.

### 4.3 Renewal and cancellation

Subscriptions renew automatically at the end of each billing period until you
cancel. You may cancel at any time from your billing settings. Cancellation stops
the next renewal; it does not retroactively refund the period you are in.

### 4.4 Refunds

Because access and token quota are made available immediately, subscription fees
are generally non-refundable once a billing period has begun. We will refund a
period in full where:

- we terminated your account without cause; or
- a technical fault on our side made the Service substantially unusable for that
  period and we could not remedy it; or
- the law where you live grants you a withdrawal right that we cannot exclude.

Contact ${contactEmail} to request a refund. Charges billed to you directly by a
model provider under BYOK are never refundable by us — we never received them.

### 4.5 Quota

Each plan carries a monthly token quota. Tokens spent by every layer of the agent
hierarchy count against it, including tasks that fail, time out, or that you
cancel — the work was performed and the tokens were consumed. When you reach your
quota you cannot start new tasks until the period rolls over or you upgrade.

## 5. Acceptable use

Your use of ${brand} is governed by our [Acceptable Use Policy](/acceptable-use),
which forms part of these Terms. In short: do not use agents to break the law,
harm people, attack systems, or abuse the platform's compute.

We may suspend or terminate an account that violates that policy, with notice
where practicable and immediately where the violation is severe or ongoing.

## 6. Your content and your agents

You keep every right you already have in the prompts you write, the documents you
upload, and the agent configurations you build. You grant us only the licence we
need to operate the Service for you: to store your content, transmit it to the
model providers you have configured, index it for retrieval, and display it back
to you.

We do not train models on your content.

### 6.1 Publishing to the Marketplace

If you publish an agent team to the Marketplace, you grant every other user a
perpetual, worldwide, royalty-free licence to install, use, and modify it. That
licence survives the deletion of your account: other people will have built on
your work, and we will not break their setups to unpublish yours. What we do on
deletion is sever the link between the published item and you — see the
[Privacy Policy](/privacy).

Do not publish anything you do not have the right to publish, and do not put
secrets, personal data, or credentials into a system prompt. Published items are
scanned for prompt-injection patterns before they go live, but that scan is a
safety net, not a guarantee.

### 6.2 Content you install

Agent teams published by other users are third-party content. We scan them, but
we do not endorse them and we do not warrant that they are correct, safe, or fit
for anything. Installed agents cannot read your API keys directly; all provider
calls are brokered by our service layer.

## 7. Agent output

${brand} orchestrates language models. Language models produce output that can be
wrong, biased, outdated, or fabricated, and an agent hierarchy does not eliminate
this — it can amplify it.

**Do not rely on agent output for decisions that carry legal, financial, medical,
or safety consequences without independent human review.** The optional Reviewer
agent improves quality; it does not make output correct.

You are responsible for what you do with agent output, including anything an
agent executes on your behalf.

## 8. Availability

We aim to keep the Service running but we do not promise any particular uptime.
We may change, suspend, or discontinue features, and we may impose limits, with
notice where we reasonably can.

## 9. Termination

You may stop using the Service at any time and may delete your account from your
profile settings. Deletion is subject to a grace period described in the
[Privacy Policy](/privacy).

We may suspend or terminate your access if you materially breach these Terms, if
required by law, or if continuing to serve you would expose us or other users to
real risk. Where we terminate without cause we will refund the unused portion of
your current billing period.

## 10. Disclaimers

To the fullest extent permitted by law, the Service is provided **"as is" and "as
available"**, without warranties of any kind, whether express, implied, or
statutory, including any implied warranty of merchantability, fitness for a
particular purpose, or non-infringement.

Nothing in these Terms excludes liability that cannot lawfully be excluded,
including liability for death or personal injury caused by negligence, for fraud,
or for a consumer's non-excludable statutory rights.

## 11. Limitation of liability

To the fullest extent permitted by law, and except as stated in the paragraph
above:

- We are not liable for indirect, incidental, special, consequential, or punitive
  damages, nor for lost profits, lost revenue, lost data, or lost goodwill.
- We are not liable for charges billed to you by a model provider, however they
  arose, including charges caused by an agent loop, a misconfigured agent, or a
  compromised key.
- Our total aggregate liability arising out of or relating to the Service is
  limited to the greater of the amount you paid us in the twelve months before
  the event giving rise to the claim, or one hundred United States dollars.

## 12. Indemnity

You will indemnify and hold us harmless against claims, damages, and reasonable
legal costs arising from your use of the Service in breach of these Terms or the
Acceptable Use Policy, or from content you publish to the Marketplace.

## 13. Governing law and disputes

These Terms are governed by the laws of ${governingLaw}, without regard to its
conflict-of-laws rules. Disputes will be brought before ${jurisdiction}. If you
are a consumer, this does not deprive you of the protection of mandatory rules of
the country where you live.

## 14. Miscellaneous

If any provision of these Terms is held unenforceable, the rest remains in force.
Our failure to enforce a provision is not a waiver of it. You may not assign these
Terms without our consent; we may assign them to a successor in connection with a
merger, acquisition, or sale of assets.

These Terms, together with the [Privacy Policy](/privacy), the
[Cookie Policy](/cookies), and the [Acceptable Use Policy](/acceptable-use), are
the entire agreement between you and us regarding the Service.

## 15. Contact

Questions about these Terms: ${contactEmail}
`.trim();
