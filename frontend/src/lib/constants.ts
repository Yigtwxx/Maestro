import type { LLMProvider, SubscriptionPlan, TaskStatus } from '@/types';

// Empty means same-origin: in production a reverse proxy fronts both the app and
// the API on one domain, so the browser needs no absolute base and there is no
// CORS. Development sets these to absolute localhost URLs via .env.local.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

export const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL ?? '';

// Names the Web Lock that serializes refresh-token rotation across this
// origin's documents. Not a storage key — nothing is persisted; the access
// token lives in memory and the refresh token in an httpOnly cookie.
export const REFRESH_LOCK_NAME = 'maestro.refresh';
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

// Digits in an emailed verification code (mirrors backend EMAIL_CODE_DIGITS).
// Drives the number of OTP boxes; the backend rejects any other length.
export const EMAIL_CODE_DIGITS = 6;

// How long that code stays valid (mirrors backend EMAIL_CODE_TTL_MINUTES).
// Only used to seed the countdown before the server tells us the real expiry.
export const EMAIL_CODE_TTL_MINUTES = 15;

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

// Copy for the free plan plus the three paid ones. Prices and quotas come from
// the backend (GET /billing/plans) so they can never drift from what is charged;
// a plan the backend does not price is skipped by both grids.
export const SUBSCRIPTION_PLANS: {
  plan: SubscriptionPlan;
  name: string;
  tagline: string;
  features: string[];
}[] = [
  {
    plan: 'free',
    name: 'Free',
    tagline: 'Everything, unmetered, while the paid plans are in the works.',
    features: ['Unlimited tokens', 'BYOK API keys', 'Local LLM (Ollama)'],
  },
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
    features: ['Priority task queue', 'Advanced metrics', 'Priority support'],
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

// The plan card that gets the featured border. One per page. Points at the
// plan a visitor can actually take today; revisit when paid plans open.
export const RECOMMENDED_PLAN: SubscriptionPlan = 'free';

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

// Families of related domains (mirrors backend DOMAIN_GROUP_CATALOG). Order
// must match the backend exactly. Groups drive three things: the two-stage
// orchestrator routing, the Architect catalog's tabs, and the hue every domain
// in the family renders in (see lib/agent-colors.ts).
export const DOMAIN_GROUPS = [
  'build',
  'market',
  'money',
  'operate',
  'life',
  'knowledge',
] as const;

// Domains the orchestrator can route to (mirrors backend registry.DOMAINS).
// Order must match backend DOMAIN_CATALOG exactly, group block by group block
// (backend/tests/test_domain_frontend_parity.py compares the lists). Connected-
// API squads are scattered through the groups rather than gathered at the end:
// each is a member of its family first and a BYOK squad second, and every one
// of them degrades to web search without its key. `general` stays last — it is
// the routing fallback.
export const AGENT_DOMAINS = [
  // build
  'software',
  'devops',
  'security',
  'qa',
  'cloud',
  'apidesign',
  'mobile',
  'gamedev',
  'data',
  'opensource',
  // market
  'marketing',
  'seo',
  'content',
  'product',
  'sales',
  'ads',
  'brand',
  'ecommerce',
  'social',
  // money
  'finance',
  'crypto',
  'econ',
  'personalfinance',
  'tax',
  // operate
  'legal',
  'hr',
  'project',
  'procurement',
  'support',
  'community',
  // life
  'local',
  'travel',
  'career',
  'health',
  'food',
  // knowledge
  'searching',
  'research',
  'scholar',
  'education',
  'journalism',
  'translation',
  'climate',
  'general',
] as const;

// Which group each domain belongs to (mirrors backend DomainInfo.group). The
// backend serves the same mapping on `GET /agents`, but colour resolution runs
// before that response lands and Tailwind class names have to be static
// literals, so the mapping is duplicated here and parity-tested.
export const DOMAIN_GROUP_OF: Record<string, string> = {
  software: 'build',
  devops: 'build',
  security: 'build',
  qa: 'build',
  cloud: 'build',
  apidesign: 'build',
  mobile: 'build',
  gamedev: 'build',
  data: 'build',
  opensource: 'build',
  marketing: 'market',
  seo: 'market',
  content: 'market',
  product: 'market',
  sales: 'market',
  ads: 'market',
  brand: 'market',
  ecommerce: 'market',
  social: 'market',
  finance: 'money',
  crypto: 'money',
  econ: 'money',
  personalfinance: 'money',
  tax: 'money',
  legal: 'operate',
  hr: 'operate',
  project: 'operate',
  procurement: 'operate',
  support: 'operate',
  community: 'operate',
  local: 'life',
  travel: 'life',
  career: 'life',
  health: 'life',
  food: 'life',
  searching: 'knowledge',
  research: 'knowledge',
  scholar: 'knowledge',
  education: 'knowledge',
  journalism: 'knowledge',
  translation: 'knowledge',
  climate: 'knowledge',
  general: 'knowledge',
};

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
  // Mirrors backend SKILLS_PER_AGENT_MAX. Each attached bundle adds its whole
  // instruction text to the subagent's system prompt, which is what the cap is
  // protecting.
  skillsPerAgent: 5,
  // Mirrors backend MCP_SERVERS_PER_AGENT_MAX. The backend additionally refuses
  // an attachment whose servers offer more than MCP_TOOLS_PER_AGENT_MAX tools
  // between them — the server count alone does not bound the prompt cost.
  mcpServersPerAgent: 3,
} as const;

// Field limits for a skill, mirroring backend schemas/skill.py SkillCreate.
// Same contract as AGENT_LIMITS above: the wizard validates before the
// round-trip, and test_domain_frontend_parity.py fails on a drift.
export const SKILL_LIMITS = {
  name: 80,
  description: 280,
  instructions: 6000,
  outputFormat: 2000,
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
  security: 'repo_intel',
  opensource: 'repo_intel',
  social: 'social_search',
  journalism: 'social_search',
  support: 'community_read',
  community: 'community_read',
  local: 'places_intel',
  travel: 'places_intel',
};
