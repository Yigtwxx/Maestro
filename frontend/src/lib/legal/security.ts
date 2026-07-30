import { LEGAL_ENTITY } from './config';

const { brand, contactEmail, securityEmail, sourceUrl } = LEGAL_ENTITY;

export const SECURITY = `
## Why this page exists

${brand} asks you to paste an API key — a bearer credential that can spend your
money — into a web form. That is a lot of trust. This page describes exactly what
happens to that key, and to everything else you give us, so you can decide whether
the trust is warranted rather than take our word for it.

Everything here is implemented in the source, which is public: ${sourceUrl}

## How your API keys are handled

### Encrypted before they touch a disk

A key you submit is encrypted with **AES-256-GCM** before it is written anywhere.
AES-GCM is authenticated encryption: a ciphertext that has been tampered with
fails to decrypt rather than decrypting to something wrong. Each key is encrypted
under a master key that lives in the server's environment, never in the codebase
and never in the database beside the data it protects.

### Never sent back to the browser

There is no endpoint that returns a decrypted key. The keys page shows you the
provider and the label you gave it, and nothing else. A key is decrypted only in
server memory, at the moment an agent needs to call that provider, and is
discarded afterwards.

If you lose a key, you cannot recover it from us. Rotate it with your provider and
paste the new one.

### Never written to a log

Keys are excluded from logging at every level, including debug. Exception handlers
return generic messages rather than raw provider responses, so a stack trace
cannot leak a credential into your logs or ours.

### Marketplace agents cannot read them

An agent team you install from the Marketplace is a system prompt and a list of
tools. It never receives your keys. Every provider call is brokered by our service
layer, which resolves the key server-side. A malicious published agent cannot
exfiltrate a credential it never sees.

## How your card is handled

Your full card number (PAN) is **never stored, never logged, and never returned in
an API response**. It exists in server memory for the duration of one call to the
payment processor. What persists is the card brand, its last four digits, and the
expiry — enough to show you which card is on file, and nothing more.

## How your data is isolated

Every account's data is scoped by user id at the query layer, in all three stores:

- **PostgreSQL** — account, subscription and usage rows are keyed to your user id
  and cascade-delete with it.
- **MongoDB** — task sessions, agent logs, documents and custom agents are filtered
  by user id on every read and write.
- **Qdrant (vector memory)** — every embedding carries your user id in its payload,
  and every retrieval applies a user filter. One account's memories cannot surface
  in another account's retrieval, by construction rather than by convention.

## How agents are contained

Autonomous agents are dangerous in three specific ways. Each has a hard limit.

### Runaway loops

Two agents that keep handing work back to each other would drain your provider
quota. Every subagent has a maximum iteration count; the Reviewer-to-Subagent
correction loop has its own, lower ceiling; and every task has a wall-clock
timeout. When a limit trips, the task is stopped, you are told, and the tokens
already spent are billed against your quota — because they were really spent.

### Prompt injection

Content an agent fetches from the web, or reads from a document, is untrusted. It
is wrapped in explicit delimiters and followed by an instruction telling the model
to treat the block as data and never to follow instructions inside it.

Agent teams published to the Marketplace are scanned for injection patterns before
they go live, and a publish that fails the scan is rejected. Treat this as a safety
net, not a guarantee: read a system prompt before you install it.

### Code execution

When an agent runs code, it runs inside an isolated Docker container, not on the
application host. Output is truncated before it re-enters the model's context.

## Authentication

Passwords are hashed with **Argon2**, the current password-hashing standard, and
are never stored or transmitted in a recoverable form. Sessions use short-lived
JWT access tokens with separate refresh tokens. The refresh token is held in an
\`HttpOnly\` cookie that page scripts cannot read, and the access token lives only
in the page's memory — neither is written to browser storage, so a scripting flaw
cannot be turned into a stolen session.

WebSocket connections — the live task and Architect streams — require the same
authentication as the HTTP API. There is no anonymous socket, and you can only
subscribe to a task you own.

Authentication endpoints are rate limited to slow credential stuffing, and every
endpoint validates its input against a strict schema before any handler sees it.

## Staying local

You do not have to give us any provider key at all. ${brand} ships with a local
model: an open-weights model served on the machine that runs the platform, with a
local embedding model for retrieval. With it, no prompt of yours ever leaves the
infrastructure you are running.

## What we do not claim

We would rather be believed than impressive, so:

- We hold **no** security certification — no SOC 2, no ISO 27001. We are not
  audited.
- We have not commissioned an external penetration test.
- We run no bug bounty programme.
- Billing currently runs through a mock provider. **Do not enter a real card
  number.** See the [Terms of Service](/terms).

No system is perfectly secure, and a small project is no exception.

## Reporting a vulnerability

If you find a security issue, email ${securityEmail} with enough detail to
reproduce it. Please give us a reasonable chance to fix it before disclosing it
publicly. We will not pursue legal action against anyone who researches in good
faith, stays within their own account, avoids degrading the service for others,
and does not access or destroy another user's data.

General questions: ${contactEmail}
`.trim();
