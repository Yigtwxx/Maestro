// Shared API types — mirror the backend Pydantic schemas.

// Mirrors the backend `LLMProvider` enum member-for-member, in the same order.
// `backend/tests/test_provider_frontend_parity.py` fails CI on any drift, here
// or in the PROVIDERS registry in `lib/providers.ts`.
export type LLMProvider =
  // --- AI brains ---
  | 'ollama'
  | 'openai'
  | 'anthropic'
  | 'gemini'
  | 'groq'
  | 'deepseek'
  | 'mistral'
  | 'xai'
  | 'openrouter'
  | 'together'
  | 'perplexity'
  | 'cerebras'
  | 'fireworks'
  | 'deepinfra'
  | 'sambanova'
  | 'nebius'
  | 'hyperbolic'
  | 'novita'
  | 'huggingface'
  | 'cohere'
  | 'moonshot'
  | 'zai'
  | 'qwen'
  | 'ai21'
  | 'custom'
  // --- Service integrations ---
  | 'x'
  | 'instagram'
  | 'reddit'
  | 'linkedin'
  | 'youtube'
  | 'tiktok'
  | 'bluesky'
  | 'pinterest'
  | 'discord'
  | 'slack'
  | 'telegram'
  | 'github'
  | 'gitlab'
  | 'vercel'
  | 'cloudflare'
  | 'sentry'
  | 'notion'
  | 'jira'
  | 'linear'
  | 'trello'
  | 'asana'
  | 'clickup'
  | 'airtable'
  | 'figma'
  | 'google_drive'
  | 'gmail'
  | 'resend'
  | 'sendgrid'
  | 'mailchimp'
  | 'twilio'
  | 'stripe'
  | 'shopify'
  | 'hubspot'
  | 'zendesk'
  | 'google_maps'
  | 'tavily'
  | 'exa'
  | 'serper'
  | 'firecrawl'
  | 'alpha_vantage'
  | 'coingecko'
  | 'openweather';

// Every account is provisioned with an active 'free' plan (unlimited tokens)
// at registration. The paid plans exist but are parked until a real payment
// processor is integrated.
export type SubscriptionPlan = 'free' | 'starter' | 'pro' | 'scale';

export type SubscriptionStatus =
  'active' | 'past_due' | 'canceled' | 'inactive';

export type CardBrand = 'visa' | 'mastercard';

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'needs_review'
  | 'awaiting_answer'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled'
  | 'timeout';

// The refresh half of the pair is never in a body — it arrives as an httpOnly
// cookie the browser stores on its own (CLAUDE.md §9 rule 14).
export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserPublic {
  id: string;
  email: string;
  display_name: string | undefined;
  // null = no active subscription (fresh account or never subscribed).
  subscription_tier: SubscriptionPlan | null;
  // Default LLM "brain" for tasks; undefined/null means the local model (ollama).
  default_provider: LLMProvider | null | undefined;
  // Per-role model pins ({main: 'claude-opus-4-8', ...}); null/undefined = tier defaults.
  model_preferences?: Record<string, string> | null;
  // Profile personalization (client-rendered monogram avatar + short bio).
  bio?: string | null;
  avatar_color?: string | null;
  avatar_emoji?: string | null;
  // Account preferences.
  timezone?: string | null;
  default_reviewer_enabled?: boolean;
  default_tracing_enabled?: boolean;
  // Whether TOTP two-factor auth is active (never exposes the secret).
  two_factor_enabled?: boolean;
  // Whether the account's email address has been verified. While false, task
  // start and API-key creation are soft-gated server-side.
  email_verified?: boolean;
  // ISO timestamp the account was created ("member since").
  created_at?: string | null;
  // ISO timestamp. Set means the account is locked and scheduled for purge.
  deletion_requested_at?: string | null;
  // Authorization role. The admin moderation surface is revealed only for 'admin'.
  role?: UserRole;
  // ISO timestamp. Set means a moderator suspended the account.
  suspended_at?: string | null;
}

export type UserRole = 'user' | 'admin';

/** One active login session (a refresh-token family). */
export interface SessionInfo {
  id: string;
  /** Human-readable device/browser summary parsed from the User-Agent. */
  device: string;
  ip: string | null;
  created_at: string;
  last_used_at: string | null;
  /** True for the session making this request. */
  current: boolean;
}

/** Response to a 2FA setup call: the secret to enroll + a ready-to-scan QR. */
export interface TwoFactorSetup {
  secret: string;
  otpauth_uri: string;
  /** Inline SVG markup for the QR code (no external image). */
  qr_svg: string;
}

/** One-time recovery codes shown right after enabling 2FA. */
export interface RecoveryCodes {
  recovery_codes: string[];
}

/**
 * A login response. Either a full token pair, or an MFA challenge that must be
 * completed via the TOTP verify endpoint before tokens are issued.
 */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
}

/** When deletion was requested, and when it becomes irreversible. */
export interface AccountDeletionStatus {
  deletion_requested_at: string;
  purge_after: string;
}

// --- Billing ---

/** A card as typed by the user. Sent once, never stored client-side. */
export interface CardInput {
  number: string;
  exp_month: number;
  exp_year: number;
  cvc: string;
  holder: string;
}

/** The safe-to-display remnants of a card. */
export interface PaymentMethodPublic {
  brand: CardBrand;
  last4: string;
  exp_month: number;
  exp_year: number;
}

export interface PlanPublic {
  plan: SubscriptionPlan;
  price_cents: number;
  quota_tokens: number;
  currency: string;
}

/** A paid plan on the anonymous pricing page, at list price. */
export interface PlanPublicListing {
  plan: SubscriptionPlan;
  price_cents: number;
  quota_tokens: number;
  currency: string;
}

export interface SubscriptionPublic {
  plan: SubscriptionPlan;
  status: SubscriptionStatus;
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
  used_tokens: number;
  quota_tokens: number;
  payment_method: PaymentMethodPublic | undefined;
}

export interface ApiKeyPublic {
  id: string;
  provider: LLMProvider;
  label: string;
  key_hint: string;
  is_active: boolean;
  created_at: string;
  // Only set for the custom OpenAI-compatible provider.
  base_url?: string;
  model?: string;
}

export interface TaskCreated {
  task_id: string;
  status: TaskStatus;
}

export interface AgentEvent {
  type: string;
  ts: string;
  role?: string;
  state?: string;
  index?: number;
  subtask?: string;
  domain?: string;
  reason?: string;
  // Routing decision origin: 'user' (manual selection) | 'orchestrator'.
  source?: string;
  subtasks?: string[];
  // Fixed-team member running this subtask (display name + id).
  member?: string;
  member_id?: string;
  // Main Agent's per-member briefs for the fixed team.
  assignments?: AssignmentBrief[];
  answer?: string;
  // Streamed synthesis chunk (agent_delta events carry ~80 chars each in `text`).
  text?: string;
  question?: string;
  error?: string;
  // agent_warning: 'degraded' (a fallback ran) | 'retry' (provider link is
  // failing). Non-fatal — the task keeps going, but the result is affected.
  kind?: string;
  message?: string;
  // The true terminal status carried on a task_failed event (cancelled |
  // timeout | failed), so the live view freezes with the correct look
  // regardless of which client cancelled and on snapshot replay.
  status?: TaskStatus;
  approved?: boolean;
  issues?: string[];
  retry_hints?: string[];
  // Subagent tool activity (agent_message with role 'subagent'). Each tool
  // call emits twice — `done: false` on start, `done: true` on completion — so
  // the canvas can show a call as in-flight rather than only after the fact.
  action?: string;
  done?: boolean;
  content?: string;
  query?: string;
  url?: string;
  // Connected-API tools only: the BYOK service the call authenticated against
  // ('x', 'github', 'google_maps', 'discord', 'slack', 'telegram'). Absent for
  // the keyless tools, which get no lane on the connected rail.
  provider?: string;
  repo?: string;
  channel?: string;
  [key: string]: unknown;
}

export interface TaskState {
  task_id: string;
  status: TaskStatus;
  prompt: string;
  domain: string | undefined;
  reviewer_enabled: boolean;
  result: TaskResult | undefined;
  error: string | undefined;
  events: AgentEvent[];
  metadata: Record<string, unknown>;
}

/** One row of the task history sidebar. Carries no events. */
export interface TaskSummary {
  task_id: string;
  status: TaskStatus;
  /** Truncated server-side. */
  prompt: string;
  domain: string | undefined;
  error: string | undefined;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  items: TaskSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskResult {
  domain: string;
  answer: string;
  subtasks: unknown[];
  metadata: Record<string, unknown>;
}

export interface ApiError {
  detail: string;
}

// --- Dashboard ---

/** Daily series over the trend window, oldest first (one entry per day). */
export interface DashboardTrends {
  window_days: number;
  /** ISO YYYY-MM-DD labels, oldest first. */
  days: string[];
  tasks: number[];
  completed: number[];
  failed: number[];
  tokens: number[];
  /** 0..1 per day; null on days with no terminal tasks. */
  success_rate: (number | null)[];
  /** null on days with no tasks. */
  avg_tokens_per_task: (number | null)[];
}

export interface DashboardMetrics {
  total_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  success_rate: number;
  total_tokens: number;
  avg_tokens_per_task: number;
  trends: DashboardTrends;
}

export interface ProviderUsage {
  tasks: number;
  tokens: number;
}

export interface TokenUsage {
  user_id: string;
  total_tokens: number;
  total_tasks: number;
  success_rate: number;
  by_provider: Record<string, ProviderUsage>;
}

export interface CostSummary {
  currency: string;
  total_cost: number;
  by_provider: Record<string, number>;
}

// --- Traces (execution spans) & cost breakdown ---

export type SpanKind = 'task' | 'step' | 'agent' | 'llm' | 'tool';
export type SpanStatus = 'ok' | 'error';
export type CostGroupBy = 'day' | 'model' | 'domain';

/**
 * A span's OTel-style attribute bag. Keys are dotted (`gen_ai.*`, `maestro.*`),
 * so the typed hints are optional and an index signature keeps the shape open.
 */
export interface SpanAttributes {
  'gen_ai.request.model'?: string;
  'gen_ai.response.model'?: string;
  'gen_ai.usage.input_tokens'?: number;
  'gen_ai.usage.output_tokens'?: number;
  'gen_ai.system'?: string;
  'gen_ai.response.finish_reason'?: string;
  'maestro.request.preview'?: string;
  'maestro.tokens.estimated'?: boolean;
  'maestro.role'?: string;
  'maestro.member_id'?: string;
  'maestro.domain'?: string;
  'maestro.index'?: number;
  'maestro.provider'?: string;
  'maestro.resumed'?: boolean;
  'maestro.tool.action'?: string;
  [key: string]: unknown;
}

/** One execution span. Tree is encoded via `parent_span_id` -> `span_id`. */
export interface TraceSpan {
  trace_id: string;
  span_id: string;
  // null on the root "task" span; may reference an id absent under the 1000 cap.
  parent_span_id: string | null;
  name: string;
  kind: SpanKind;
  user_id: string;
  start_time: string; // ISO
  end_time: string; // ISO
  duration_ms: number;
  status: SpanStatus;
  error_message: string | null;
  attributes: SpanAttributes;
  // Nonzero only on llm.chat spans; all parents carry 0.
  cost_usd: number;
  created_at: string;
}

export interface TaskTrace {
  task_id: string;
  // Sorted by start_time ASC, capped at 1000 server-side. Empty when tracing off.
  spans: TraceSpan[];
}

/** One rollup row per distinct span name. */
export interface TraceSummaryNode {
  name: string;
  kind: SpanKind;
  count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
}

export interface TraceSummary {
  task_id: string;
  span_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  nodes: TraceSummaryNode[];
}

export interface CostBucket {
  // day -> "YYYY-MM-DD"; model -> model name; domain -> domain string ("unknown").
  key: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface CostBreakdown {
  days: number;
  group_by: CostGroupBy;
  total_cost_usd: number;
  buckets: CostBucket[];
}

// --- Agents (custom configurations) ---

// 'executable' tools have a real runtime behind the subagent directive loop;
// 'declarative' ones the model performs natively in its reasoning. Mirrors
// backend schemas/agent.py ToolCatalogEntry.
export type ToolKind = 'executable' | 'declarative' | 'custom_api';

export interface ToolCatalogItem {
  id: string;
  label: string;
  description: string;
  kind: ToolKind;
  // Which BYOK services this tool can authenticate against. Plural because
  // community_read picks one per call. Empty means nothing to connect.
  providers: LLMProvider[];
  // Still useful with no key at all (repo_intel: GitHub serves anonymous reads).
  keyless: boolean;
  // Whether *this* user holds an active key. Always true when providers is empty.
  connected: boolean;
  // The operator switch. Distinct from `connected`: the remedies differ.
  available: boolean;
}

export interface AgentConfig {
  id: string;
  name: string;
  domain: string;
  system_prompt: string;
  tools: string[];
  description: string;
  routing_hint: string;
  output_format: string;
  routable: boolean;
  custom_api_tool_ids: string[];
  type: string;
  created_at: string;
  updated_at: string;
}

// A fixed team member of a built-in domain agent.
export interface TeamMember {
  id: string;
  name: string;
  description: string;
}

// One brief the Main Agent assigned to a fixed-team member.
export interface AssignmentBrief {
  member_id: string;
  member_name: string;
  brief: string;
  // Ids of earlier members whose output this member builds on.
  depends_on?: string[];
}

export interface BuiltinAgent {
  id: string;
  name: string;
  domain: string;
  type: string;
  description: string;
  capabilities: string[];
  tools: string[];
  team: TeamMember[];
}

export interface AgentList {
  builtin: BuiltinAgent[];
  custom: AgentConfig[];
}

export interface AgentConfigInput {
  name: string;
  domain: string;
  system_prompt: string;
  tools: string[];
  description: string;
  routing_hint: string;
  output_format: string;
  // Lets the orchestrator auto-route matching prompts to this agent, using
  // routing_hint as the description it classifies against.
  routable: boolean;
  // Ids of the user's own registered endpoints. Deliberately separate from
  // `tools`: those are catalog ids shared by everyone, these are per-user
  // records, and the backend rejects one appearing in the other's list.
  custom_api_tool_ids: string[];
}

// --- Custom API tools (user-registered HTTP endpoints) ---

export type CustomApiAuthMode = 'none' | 'bearer' | 'header' | 'query';
export type CustomApiMethod = 'GET' | 'POST';
export type CustomApiParameterType = 'string' | 'integer' | 'number' | 'boolean';

export interface CustomApiParameter {
  name: string;
  type: CustomApiParameterType;
  description: string;
  required: boolean;
  enum?: string[];
}

export interface CustomApiTool {
  id: string;
  slug: string;
  name: string;
  description: string;
  method: CustomApiMethod;
  base_url: string;
  path_template: string;
  query_template: Record<string, string>;
  headers: Record<string, string>;
  auth_mode: CustomApiAuthMode;
  auth_name: string;
  // Masked tail only — the stored credential is never returned.
  secret_hint?: string;
  parameters: CustomApiParameter[];
  response_json_path: string;
  response_max_chars: number;
  timeout_seconds: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomApiToolInput {
  slug: string;
  name: string;
  description: string;
  method: CustomApiMethod;
  base_url: string;
  path_template: string;
  auth_mode: CustomApiAuthMode;
  auth_name: string;
  // Write-only. Omit on update to leave the stored credential untouched.
  secret?: string;
  parameters: CustomApiParameter[];
  enabled: boolean;
}

export interface CustomApiToolTestResult {
  ok: boolean;
  status: number;
  duration_ms: number;
  preview: string;
  error?: string;
}

// --- Marketplace ---

export interface MarketplaceItem {
  id: string;
  name: string;
  description: string;
  domain: string;
  system_prompt: string;
  tools: string[];
  installs: number;
  security_scan: Record<string, unknown>;
  created_at: string;
  /** Daily install counts over the trend window (oldest first); null until events exist. */
  install_history: number[] | null;
  /** Denormalized review aggregates; null/0 until the first review lands. */
  rating_avg: number | null;
  rating_count: number;
}

/**
 * A published item as served to anonymous visitors. Deliberately narrower than
 * `MarketplaceItem`: the author's system prompt and the raw security-scan
 * findings never leave the authenticated surface.
 */
export interface MarketplaceItemPreview {
  id: string;
  name: string;
  description: string;
  domain: string;
  tools: string[];
  installs: number;
  /** True only for the first-party teams Maestro publishes. */
  featured: boolean;
  author_label: string;
  security_scan_status: string;
  created_at: string;
  rating_avg: number | null;
  rating_count: number;
}

/**
 * A review as served to clients. Carries no author identity (reviewer display
 * names are never public); `is_own` marks the caller's review server-side.
 */
export interface MarketplaceReview {
  /** The review's own id (a random uuid, not identity) — used to report it. */
  id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string;
  is_own: boolean;
}

export interface MarketplaceReviewList {
  items: MarketplaceReview[];
  total: number;
  /** The caller's review regardless of pagination, for prefilling the form. */
  my_review: MarketplaceReview | null;
}

export interface MarketplaceReviewInput {
  rating: number;
  comment?: string;
}

export interface MarketplacePublishInput {
  name: string;
  description: string;
  domain: string;
  system_prompt: string;
  tools: string[];
}

// --- Documents (RAG knowledge base) ---

export interface DocumentMeta {
  id: string;
  filename: string;
  chunk_count: number;
  created_at: string;
}

// --- Moderation / content reports ---

export type ReportReason = 'spam' | 'abuse' | 'malicious' | 'other';
export type ReportStatus = 'open' | 'resolved' | 'dismissed';
export type MarketplaceStatus = 'published' | 'hidden' | 'removed';

export interface ReportInput {
  reason: ReportReason;
  note?: string;
}

// --- Admin / moderation surface ---

export interface AdminRecentItem {
  id: string;
  name: string;
  domain: string;
  author_id: string | null;
  status: string;
  created_at: string | null;
}

export interface AdminOverview {
  users_total: number;
  admins_total: number;
  suspended_total: number;
  items_total: number;
  items_hidden: number;
  items_removed: number;
  reviews_total: number;
  open_reports: number;
  recent_items: AdminRecentItem[];
}

export interface AdminUserRow {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  subscription_tier: SubscriptionPlan | null;
  email_verified: boolean;
  suspended_at: string | null;
  deletion_requested_at: string | null;
  created_at: string | null;
}

export interface AdminUserDetail {
  user: AdminUserRow;
  counts: { items: number; agents: number; reviews: number };
}

export interface AdminMarketplaceItem {
  id: string;
  name: string;
  description: string;
  domain: string;
  author_id: string | null;
  installs: number;
  status: MarketplaceStatus;
  rating_avg: number | null;
  rating_count: number;
  security_scan: Record<string, unknown> | null;
  moderation: Record<string, unknown> | null;
  created_at: string | null;
}

export interface AdminReview {
  id: string;
  item_id: string;
  user_id: string;
  rating: number;
  comment: string | null;
  hidden: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminReport {
  id: string;
  target_type: 'item' | 'review';
  target_id: string;
  reporter_id: string;
  reason: ReportReason;
  note: string | null;
  status: ReportStatus;
  created_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
}

export interface AdminAuditEntry {
  id: string;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}
