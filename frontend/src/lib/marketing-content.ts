// Copy for the public marketing tabs. Kept out of the page components so the
// pages stay layout-only and the strings live in one reviewable place.

import { Boxes, Brain, KeyRound, Network } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { AgentDomain } from '@/lib/agent-colors';
import { GITHUB_URL } from '@/lib/constants';

// --- How it works ---------------------------------------------------------

export interface Feature {
  icon: LucideIcon;
  title: string;
  description: string;
}

export const FEATURES: readonly Feature[] = [
  {
    icon: KeyRound,
    title: 'BYOK Security',
    description:
      'Connect your own API keys. They are encrypted with AES-256-GCM, never stored in plain text, and never returned to the browser.',
  },
  {
    icon: Network,
    title: 'Multi-Layer Orchestration',
    description:
      'The orchestrator routes the task, a domain expert splits it into subtasks, specialist subagents execute, and the reviewer audits the result.',
  },
  {
    icon: Brain,
    title: 'RAG Memory',
    description:
      'Past conversations and uploaded documents are remembered. Relevant context is retrieved and injected into every task, scoped to you alone.',
  },
  {
    icon: Boxes,
    title: 'Marketplace',
    description:
      'Install community agent teams in one click, or publish your own. Every publication passes a mandatory prompt security scan.',
  },
] as const;

export interface PipelineStage {
  label: string;
  description: string;
  optional?: boolean;
}

/** The one-way task flow, mirroring the backend `AgentRole` hierarchy. */
export const PIPELINE: readonly PipelineStage[] = [
  {
    label: 'ORCHESTRATOR',
    description:
      'Reads your prompt and decides which domain owns it. It routes; it never does the work itself.',
  },
  {
    label: 'MAIN AGENT',
    description:
      'The domain expert. Breaks the task into subtasks and briefs its fixed team of specialists.',
  },
  {
    label: 'SUBAGENT',
    description:
      'A specialist executing one atomic subtask — a web search, a data fetch, a sandboxed script run.',
  },
  {
    label: 'REVIEWER',
    description:
      'Audits each deliverable and sends it back with concrete fixes when it falls short.',
    optional: true,
  },
] as const;

// --- Use cases ------------------------------------------------------------

export interface UseCase {
  domain: AgentDomain;
  title: string;
  description: string;
  /** Concrete prompts a visitor could paste in verbatim. */
  examples: readonly string[];
}

export const USE_CASES: readonly UseCase[] = [
  {
    domain: 'software',
    title: 'Ship a feature end to end',
    description:
      'Architecture, implementation and review as separate steps, each auditable on its own.',
    examples: [
      'Add rate limiting to our public API and write the tests.',
      'Find the root cause of this stack trace and propose a verified fix.',
    ],
  },
  {
    domain: 'finance',
    title: 'Brief yourself before the market opens',
    description:
      'Filings, news and sentiment gathered in parallel, then reconciled into one position-neutral read.',
    examples: [
      'Summarize the bull and bear case for this quarter’s earnings.',
      'What macro risks would move this sector in the next month?',
    ],
  },
  {
    domain: 'marketing',
    title: 'Position a launch, then write it',
    description:
      'Audience research and competitor framing feed the message hierarchy the copy is built from.',
    examples: [
      'Build a launch campaign for a developer tool aimed at platform teams.',
      'Rewrite this landing page around the strongest differentiated claim.',
    ],
  },
  {
    domain: 'seo',
    title: 'Audit a site by traffic impact',
    description:
      'Crawl structure, metadata and Core Web Vitals, ranked by what actually costs you visits.',
    examples: [
      'Audit our docs site and rank the fixes by expected traffic gain.',
      'Which pages are being indexed but never ranked, and why?',
    ],
  },
  {
    domain: 'searching',
    title: 'Find and verify a specific fact',
    description:
      'Several search framings run in parallel, then a verifier cross-checks before anything is reported.',
    examples: [
      'Find the primary source for this statistic and check it holds up.',
      'What changed in this library between v3 and v4?',
    ],
  },
  {
    domain: 'research',
    title: 'Answer an open question with citations',
    description:
      'Claims traced to primary sources; conflicts surfaced rather than quietly resolved.',
    examples: [
      'Survey the current evidence on retrieval-augmented generation quality.',
      'Where does the literature disagree about this method, and how strongly?',
    ],
  },
  {
    domain: 'data',
    title: 'Turn a dataset into a decision',
    description:
      'Collection, cleaning, statistics and visualization, ending in business language.',
    examples: [
      'Clean this export and tell me which cohort is churning fastest.',
      'Which of these metrics actually moved, and which is noise?',
    ],
  },
  {
    domain: 'content',
    title: 'Draft, critique, then publish',
    description:
      'An outline and a voice guide come first; a critic reads the draft before the editor finalizes it.',
    examples: [
      'Write a technical blog post about our migration, then tear it apart.',
      'Produce five headline variants and explain which hook is strongest.',
    ],
  },
  {
    domain: 'legal',
    title: 'Read a contract clause by clause',
    description:
      'Obligations, asymmetries and negotiable terms, ranked by exposure. Analysis, never advice.',
    examples: [
      'Map the obligations each party carries in this agreement.',
      'Check this data flow against GDPR requirements and flag the gaps.',
    ],
  },
  {
    domain: 'education',
    title: 'Design a course, not just a lesson',
    description:
      'Measurable objectives drive the modules, the lessons and the assessments that check them.',
    examples: [
      'Build a four-week curriculum introducing vector databases.',
      'Explain this concept three ways, for three different levels.',
    ],
  },
] as const;

// --- Docs -----------------------------------------------------------------

/** Rendered with the shared `<Markdown>` component. */
export const DOCS_QUICKSTART = `## Run Maestro locally

Everything runs on your machine. The free tier uses a local model through
Ollama, so a full task costs nothing.

### 1. Start the infrastructure

\`\`\`bash
docker compose up -d
\`\`\`

This brings up PostgreSQL, MongoDB and Qdrant.

### 2. Start the app

\`\`\`bash
# Windows
./scripts/dev.ps1

# macOS / Linux
./scripts/dev.sh
\`\`\`

The script creates the backend virtualenv, applies migrations, seeds the
featured agent teams, then launches the API on port 8000 and the frontend on
port 3000.

### 3. Connect a model

Maestro is bring-your-own-key. Add an OpenAI, Anthropic or Gemini key under
**Settings → API Keys**, or skip it entirely and run against local Qwen3 via
Ollama. Keys are encrypted with AES-256-GCM before they touch the database and
are never sent back to the browser.
`;

export const DOCS_ARCHITECTURE = `## How a task flows

A single prompt travels one way through four layers. The **orchestrator** reads
it and picks the owning domain. The **main agent** for that domain splits the
work and briefs its fixed team. Each **subagent** executes one atomic subtask,
calling tools — web search, HTTP fetch, a sandboxed code run — as needed. If you
enable the **reviewer**, it audits every deliverable and sends failures back with
concrete fixes, up to \`max_review_iterations\` times.

Every layer is bounded: \`max_iterations\` per subagent, \`max_review_iterations\`
on the review loop, and \`task_timeout_seconds\` on the task as a whole. A task
that hits a limit stops, reports why, and still bills the tokens it spent.

## Where your data lives

Relational records — accounts, subscriptions, the token ledger — sit in
PostgreSQL. Agent logs, task sessions and marketplace items live in MongoDB.
Conversation memory and document chunks are embedded into Qdrant and retrieved
per task. Memory is scoped per user; nothing crosses that boundary.
`;

export const DOCS_COMMUNITY = `## Community

Maestro is open source. Read the code, file an issue, or open a pull request.

- **Source and issues:** [${GITHUB_URL}](${GITHUB_URL})
- **Marketplace:** publish an agent team and it appears in the community band of
  the Templates tab once it passes the security scan.

Adding a new LLM provider means writing one adapter class — no existing code
changes. The same is true of payment processors.
`;
