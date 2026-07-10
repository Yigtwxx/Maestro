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

// Tasks fetched per page of the history sidebar.
export const TASK_HISTORY_PAGE_SIZE = 20;

// Toast notifications: default lifetime before auto-dismiss, and the cap on how
// many can stack at once so a burst of errors cannot cover the screen.
export const TOAST_DURATION_MS = 5000;
export const TOAST_MAX = 4;

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

// First month at half price, once per account. Shown to anonymous visitors as
// a flat banner; the real, per-user figure comes from GET /billing/plans.
export const PUBLIC_DISCOUNT_PCT = 50;

// Days of Starter-quota trial a new account gets (mirrors TRIAL_DURATION_DAYS).
export const TRIAL_DURATION_DAYS = 14;

// Grace period between requesting deletion and the irreversible purge. Mirrors
// the backend ACCOUNT_DELETION_GRACE_DAYS; used to show the scheduled date.
export const ACCOUNT_DELETION_GRACE_DAYS = 30;

// Providers selectable when starting a task.
export const TASK_PROVIDERS: { value: LLMProvider; label: string; free: boolean }[] = [
  { value: 'gemini', label: 'Gemini Flash (Free — with your own key)', free: true },
  { value: 'ollama', label: 'Qwen3.5 (Free / Local — fallback)', free: true },
  { value: 'openai', label: 'OpenAI (BYOK)', free: false },
  { value: 'anthropic', label: 'Anthropic — Claude (BYOK)', free: false },
];

// AI (brain) providers selectable when adding a BYOK key.
export const BRAIN_KEY_PROVIDERS: { value: LLMProvider; label: string }[] = [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic (Claude)' },
];

// Non-LLM integrations selectable when connecting an external API key.
export const CONNECTED_KEY_PROVIDERS: { value: LLMProvider; label: string }[] = [
  { value: 'x', label: 'X (Twitter)' },
  { value: 'github', label: 'GitHub' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'google_maps', label: 'Google Maps' },
  { value: 'custom', label: 'Custom' },
];

// Providers that can drive task generation (mirrors backend LLM_CHAT_PROVIDERS).
export const BRAIN_CHAT_PROVIDERS: ReadonlySet<LLMProvider> = new Set([
  'ollama',
  'openai',
  'anthropic',
  'gemini',
]);

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
    features: ['Priority task queue', 'Advanced metrics', 'Marketplace publishing'],
  },
  {
    plan: 'scale',
    name: 'Scale',
    tagline: 'For heavy, sustained orchestration.',
    features: ['Highest token ceiling', 'Priority support', 'Early access features'],
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
export const TERMINAL_STATUSES: ReadonlySet<TaskStatus> = new Set([
  'completed',
  'failed',
  'cancelled',
  'timeout',
]);

// Events that mark the end of a task stream.
export const TERMINAL_EVENT_TYPES: ReadonlySet<string> = new Set([
  'task_completed',
  'task_failed',
]);

export const AGENT_ROLES = ['orchestrator', 'main', 'subagent', 'reviewer'] as const;

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
  'general',
] as const;
