import type { LLMProvider, SubscriptionPlan, TaskStatus } from '@/types';

// Empty means same-origin: in production a reverse proxy fronts both the app and
// the API on one domain, so the browser needs no absolute base and there is no
// CORS. Development sets these to absolute localhost URLs via .env.local.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

export const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL ?? '';

export const ACCESS_TOKEN_KEY = 'maestro.access_token';
export const REFRESH_TOKEN_KEY = 'maestro.refresh_token';
// Survives navigation and reloads so the architect page can restore the task
// the user was last watching. Events are refetched from the server, not stored.
export const ACTIVE_TASK_KEY = 'maestro.active_task';
// Records that the storage notice was dismissed, plus any future opt-ins.
export const CONSENT_KEY = 'maestro.consent';
// Tracks whether the first-run onboarding tour was completed or skipped, and how
// far the user got. Client-only; no backend flag mirrors it.
export const ONBOARDING_KEY = 'maestro.onboarding';

// Tasks fetched per page of the history sidebar.
export const TASK_HISTORY_PAGE_SIZE = 20;

// Reviews fetched per page of the marketplace reviews dialog.
export const REVIEWS_PAGE_SIZE = 20;

// Toast notifications: default lifetime before auto-dismiss, and the cap on how
// many can stack at once so a burst of errors cannot cover the screen.
export const TOAST_DURATION_MS = 5000;
export const TOAST_MAX = 4;

// Accent cyan as a space-separated RGB triplet, for effects that need a raw
// colour in a CSS custom property (see `DomainColor.rgb` in agent-colors.ts).
// Mirrors `theme.colors.accent.DEFAULT` (#22d3ee) in tailwind.config.ts.
export const ACCENT_RGB = '34 211 238';

// External links surfaced on the public landing page.
export const GITHUB_URL = 'https://github.com/Yigtwxx';
export const GITHUB_SPONSORS_URL = 'https://github.com/sponsors/Yigtwxx';

// Public marketing tabs, shared by the landing nav and the footer. `/agents`
// and `/marketplace` belong to the authenticated app, hence `/templates`.
export const MARKETING_NAV_LINKS = [
  { href: '/templates', label: 'Templates' },
  { href: '/use-cases', label: 'Use Cases' },
  { href: '/how-it-works', label: 'How It Works' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/docs', label: 'Docs' },
] as const;

// Grace period between requesting deletion and the irreversible purge. Mirrors
// the backend ACCOUNT_DELETION_GRACE_DAYS; used to show the scheduled date.
export const ACCOUNT_DELETION_GRACE_DAYS = 30;

// Max length of the profile bio (mirrors backend BIO_MAX_LEN).
export const BIO_MAX_LEN = 280;

// Max upload size for RAG documents (mirrors backend DOCUMENT_MAX_BYTES).
// Enforced client-side too so an oversize file is rejected before it is sent
// and never wastes an upload round-trip on a guaranteed 413.
export const DOCUMENT_MAX_BYTES = 5_000_000;

// Provider lists now live in a single typed registry (`lib/providers.ts`) so
// the key screen, brain selector and task-start screen never drift. Re-exported
// here for existing import paths.
export {
  TASK_PROVIDERS,
  BRAIN_KEY_PROVIDERS,
  CONNECTED_KEY_PROVIDERS,
  BRAIN_CHAT_PROVIDERS,
} from '@/lib/providers';

// Copy for the three paid plans. Prices and quotas come from the backend
// (GET /billing/plans) so they can never drift from what is actually charged.
export const SUBSCRIPTION_PLANS: {
  plan: SubscriptionPlan;
  name: string;
  tagline: string;
  features: string[];
}[] = [
  {
    plan: 'starter',
    name: 'Starter',
    tagline: 'For solo builders finding their footing.',
    features: ['BYOK API keys', 'Local LLM (Ollama)', 'Reviewer agent'],
  },
  {
    plan: 'pro',
    name: 'Pro',
    tagline: 'For teams shipping agents every day.',
    features: [
      'Priority task queue',
      'Advanced metrics',
      'Marketplace publishing',
    ],
  },
  {
    plan: 'scale',
    name: 'Scale',
    tagline: 'For heavy, sustained orchestration.',
    features: [
      'Highest token ceiling',
      'Priority support',
      'Early access features',
    ],
  },
];

// The plan card that gets the featured border. One per page.
export const RECOMMENDED_PLAN: SubscriptionPlan = 'pro';

// Cards the mock payment provider recognizes, surfaced as form hints.
export const TEST_CARDS = [
  { label: 'Visa', number: '4242 4242 4242 4242' },
  { label: 'Mastercard', number: '5555 5555 5555 4444' },
  { label: 'Declined', number: '4000 0000 0000 0002' },
] as const;

// Statuses after which a task emits no further events (mirrors backend _TERMINAL).
// `completed_with_warnings` is a genuine terminal state (partial subtask failure
// still produces an answer); omitting it left the task stuck "running" forever.
export const TERMINAL_STATUSES: ReadonlySet<TaskStatus> = new Set([
  'completed',
  'completed_with_warnings',
  'failed',
  'cancelled',
  'timeout',
]);

// Events that mark the end of a task stream. The backend emits distinct terminal
// events for the warnings and user-cancel paths; both must stop the stream and
// refresh history, or the socket reconnects indefinitely (see lib/ws.ts).
export const TERMINAL_EVENT_TYPES: ReadonlySet<string> = new Set([
  'task_completed',
  'task_completed_with_warnings',
  'task_failed',
  'task_cancelled',
]);

// WebSocket → HTTP polling fallback: after this many consecutive connection
// attempts that die before delivering a single message, stop retrying the
// socket and poll GET /tasks/{id} until the task is terminal.
export const WS_FALLBACK_AFTER_FAILURES = 3;
// Poll cadence: 4s = 15 req/min, well inside the shared read tier (60/min).
export const TASK_POLL_INTERVAL_MS = 4000;

export const AGENT_ROLES = [
  'orchestrator',
  'main',
  'subagent',
  'reviewer',
] as const;

// Roles a user can pin a model for, with the tier each defaults to.
// Mirrors backend MODEL_TIER_DEFAULTS (backend/app/core/constants.py).
export const MODEL_PREF_ROLES = [
  { role: 'orchestrator', label: 'Orchestrator', tier: 'strong' },
  { role: 'main', label: 'Main agent', tier: 'strong' },
  { role: 'subagent', label: 'Subagents', tier: 'cheap' },
  { role: 'reviewer', label: 'Reviewer', tier: 'cheap' },
  { role: 'synthesis', label: 'Synthesis', tier: 'strong' },
] as const;

// Local (Ollama) model tags served via FREE_MODEL_ENDPOINT. Unlike the cloud
// suggestions below, these only take effect under the Local LLM (Ollama) brain:
// model_preferences is provider-agnostic, so pinning one while a cloud brain is
// active would send an unknown model id to that provider. The picker suffixes
// them so this scope is visible to the user.
export const LOCAL_MODEL_SUGGESTIONS = [
  'nemotron-3-nano:30b-a3b-q4_K_M',
  'qwen3.5:9b',
] as const;

// Suggested model ids for the per-role picker. Cloud ids mirror backend
// PROVIDER_TIER_MODELS / MODEL_PRICING (backend/app/core/constants.py) — keep in
// sync when the backend lineup is refreshed. Local ids come first so the local
// tier is easy to compare head-to-head.
export const MODEL_SUGGESTIONS = [
  ...LOCAL_MODEL_SUGGESTIONS,
  'claude-sonnet-5',
  'claude-haiku-4-5',
  'gpt-4o',
  'gpt-4o-mini',
  'gemini-2.5-pro',
  'gemini-2.5-flash',
] as const;

// Domains the orchestrator can route to (mirrors backend registry.DOMAINS).
export const AGENT_DOMAINS = [
  'software',
  'finance',
  'marketing',
  'seo',
  'searching',
  'research',
  'data',
  'content',
  'legal',
  'education',
  // Connected-API squads — powered by a BYOK service key, degrading to web
  // search without one. Order must match backend DOMAIN_CATALOG exactly
  // (backend/tests/test_domain_frontend_parity.py compares the lists).
  'social',
  'community',
  'opensource',
  'local',
  'general',
] as const;

// Field limits for a custom agent, mirroring backend schemas/agent.py
// AgentConfigCreate. Kept here so the wizard can validate a step before the
// round-trip instead of surfacing a 422 four steps later;
// backend/tests/test_domain_frontend_parity.py compares these to the Pydantic
// max_length values, so a drift fails CI rather than the user's save.
export const AGENT_LIMITS = {
  name: 80,
  domain: 40,
  systemPrompt: 8000,
  systemPromptMin: 1,
  description: 280,
  routingHint: 280,
  outputFormat: 2000,
  // Mirrors backend CUSTOM_API_TOOLS_PER_AGENT_MAX. Each attached endpoint adds
  // a schema and a usage rule to the subagent's system prompt, which is what the
  // cap is protecting.
  customApiToolsPerAgent: 5,
} as const;

// Agent tools backed by a BYOK service key, and which providers each can use.
// Mirrors backend CONNECTED_TOOL_PROVIDERS plus community_read's per-platform
// dispatch. Drives the Architect connected rail: a squad declaring one of these
// tools gets a lane per provider, lit when it is called and dimmed with a
// connect link when the key is missing.
export const CONNECTED_TOOL_PROVIDERS: Record<string, readonly LLMProvider[]> =
  {
    repo_intel: ['github'],
    social_search: ['x'],
    places_intel: ['google_maps'],
    community_read: ['discord', 'slack', 'telegram'],
  };

// The one connected tool that still works with no key at all: GitHub serves
// anonymous reads (60/hour), so its lane is never a dead "connect me" row.
export const KEYLESS_CONNECTED_TOOLS: readonly string[] = ['repo_intel'];

// Connected tools a squad is built *around* — the tool its backend domain
// declares first. Without that key the squad still runs, but on `web_search`
// alone (backend `tools.py:resolve_enabled_tools` withholds the tool rather
// than failing the task). Every other connected tool a squad declares is an
// accelerator, not its reason to exist. Kept explicit rather than inferred
// from `tools[0]` so the meaning cannot silently flip when a backend tools
// tuple is reordered; `test_domain_frontend_parity.py` compares this map to
// DOMAIN_CATALOG. `opensource` is listed but never reads as required, because
// `repo_intel` is keyless.
export const SQUAD_CORE_CONNECTED_TOOL: Record<string, string> = {
  social: 'social_search',
  community: 'community_read',
  opensource: 'repo_intel',
  local: 'places_intel',
};
