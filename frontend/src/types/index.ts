// Shared API types — mirror the backend Pydantic schemas.

export type LLMProvider =
  | 'ollama'
  | 'openai'
  | 'anthropic'
  | 'gemini'
  | 'x'
  | 'github'
  | 'instagram'
  | 'google_maps'
  | 'custom';

// There is no free plan; new accounts start on a trial.
export type SubscriptionPlan = 'starter' | 'pro' | 'scale';

export type SubscriptionStatus =
  | 'trialing'
  | 'active'
  | 'past_due'
  | 'canceled'
  | 'inactive';

export type CardBrand = 'visa' | 'mastercard';

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'needs_review'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timeout';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserPublic {
  id: string;
  email: string;
  display_name: string | undefined;
  subscription_tier: SubscriptionPlan;
  // Default LLM "brain" for tasks; undefined/null means the free local tier.
  default_provider: LLMProvider | null | undefined;
  // ISO timestamp. Set means the account is locked and scheduled for purge.
  deletion_requested_at?: string | null;
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
  discounted_price_cents: number;
  discount_eligible: boolean;
  quota_tokens: number;
  currency: string;
}

/**
 * A plan on the anonymous pricing page. Carries the list price only: first-month
 * discount eligibility is per-user and has no meaning before sign-up.
 */
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
  trial_end: string | undefined;
  cancel_at_period_end: boolean;
  used_tokens: number;
  quota_tokens: number;
  first_discount_available: boolean;
  payment_method: PaymentMethodPublic | undefined;
}

export interface ApiKeyPublic {
  id: string;
  provider: LLMProvider;
  label: string;
  key_hint: string;
  is_active: boolean;
  created_at: string;
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
  // Fixed-team member running this subtask (Turkish display name + id).
  member?: string;
  member_id?: string;
  // Main Agent's per-member briefs for the fixed team.
  assignments?: AssignmentBrief[];
  answer?: string;
  question?: string;
  error?: string;
  approved?: boolean;
  issues?: string[];
  retry_hints?: string[];
  // Subagent tool activity (agent_message with role 'subagent').
  action?: string;
  content?: string;
  query?: string;
  url?: string;
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

export interface DashboardMetrics {
  total_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  success_rate: number;
  total_tokens: number;
  avg_tokens_per_task: number;
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

// --- Agents (custom configurations) ---

export interface ToolCatalogItem {
  id: string;
  label: string;
}

export interface AgentConfig {
  id: string;
  name: string;
  domain: string;
  system_prompt: string;
  tools: string[];
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
