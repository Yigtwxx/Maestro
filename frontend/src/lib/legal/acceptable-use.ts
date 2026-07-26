import { LEGAL_ENTITY } from './config';

const { brand, contactEmail } = LEGAL_ENTITY;

export const ACCEPTABLE_USE = `
## Why this is its own policy

${brand} does not just answer questions. Agents search the web, fetch URLs,
execute code, and call APIs with your credentials. A platform that acts has a
larger blast radius than one that only speaks, so what you may point it at needs
saying plainly.

This policy is part of the [Terms of Service](/terms). Breaking it is breaking
them.

## Do not use ${brand} to break the law

That includes, without limitation, using agents to plan, carry out, or conceal:

- fraud, phishing, or any form of deception for financial gain;
- the sale or distribution of controlled substances, weapons, or stolen goods;
- money laundering or sanctions evasion;
- the production or distribution of child sexual abuse material, which we report
  to the competent authorities without notice to you;
- infringement of copyright, trademark, trade secrets, or other intellectual
  property rights.

## Do not use ${brand} to harm people

Do not build agents that:

- harass, bully, threaten, defame, or incite violence against anyone;
- generate sexual content involving minors, or non-consensual intimate imagery of
  real people;
- impersonate a real person or organisation in a way designed to deceive;
- generate political disinformation, or content designed to interfere with an
  election or a census;
- produce targeted manipulation of a vulnerable person or group;
- give medical, legal, or financial advice presented as coming from a licensed
  professional.

## Do not use ${brand} to attack systems

Agents that can run code and make HTTP requests must not be used for:

- scanning, probing, or testing the security of a system you do not own and are
  not authorised in writing to test;
- exploiting a vulnerability, gaining unauthorised access, or escalating
  privileges anywhere;
- denial-of-service traffic, credential stuffing, or password cracking;
- developing or distributing malware, ransomware, or spyware;
- evading rate limits, CAPTCHAs, paywalls, or access controls on any service;
- scraping a site in violation of its terms, its robots directives, or applicable
  law, or scraping personal data at scale.

Authorised security research on systems you own, or on systems whose owner has
given you written permission, is allowed. The burden of proving authorisation is
yours.

## Do not abuse the platform

- Do not attempt to break out of the code-execution sandbox, reach the host, or
  access another tenant's data.
- Do not deliberately construct agent loops or forks to consume compute you have
  not paid for.
- Do not create multiple accounts to evade quota or a suspension.
- Do not resell access to ${brand} without a written agreement with us.
- Do not use the Service to build a directly competing service by extracting its
  behaviour at scale.

## Marketplace content

Agent teams you publish are used by other people. Do not publish:

- system prompts containing prompt-injection payloads, jailbreaks, or instructions
  designed to make an installing user's agents behave against their interest;
- anything designed to exfiltrate an installing user's data, credentials, or
  outputs;
- credentials, API keys, personal data, or anyone's confidential information;
- content that violates any other part of this policy.

Every publish is scanned for injection patterns and rejected if it fails. Passing
the scan is not permission — the rest of this policy still applies.

## Bring your own key, bring your own responsibility

When an agent calls a model provider with your key, that provider's acceptable
use policy applies to that call as well as ours. A prompt that is allowed here and
forbidden by OpenAI, Anthropic, or Google is still forbidden. Their enforcement is
theirs; ours is ours; you are subject to both.

## Human oversight

Agent output can be confidently wrong. Do not deploy agent output into decisions
with legal, financial, medical, or safety consequences without a human reviewing
it. The Reviewer agent is a quality tool, not a substitute for you.

## What happens if you break this policy

We may remove content, suspend a task, restrict a feature, suspend your account,
or terminate it. Where the violation is minor and unintentional we will normally
warn you first. Where it is severe, ongoing, illegal, or endangers other users, we
will act immediately and without notice.

We may preserve and disclose information where we believe in good faith that it is
necessary to comply with the law, to enforce this policy, or to prevent imminent
harm.

## Reporting a violation

If you find a published agent team or a use of ${brand} that breaks this policy,
tell us at ${contactEmail}. Include enough detail for us to find it.
`.trim();
