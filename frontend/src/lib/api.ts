// Central API client. All backend calls go through here (project rule 5.2).

import {
  API_BASE_URL,
  REVIEWS_PAGE_SIZE,
  TASK_HISTORY_PAGE_SIZE,
} from '@/lib/constants';
import { withRefreshLock } from '@/lib/refresh-lock';
import type {
  AccessTokenResponse,
  AccountDeletionStatus,
  AdminAuditEntry,
  AdminMarketplaceItem,
  AdminOverview,
  AdminReport,
  AdminReview,
  AdminUserDetail,
  AdminUserRow,
  AgentConfig,
  AgentConfigInput,
  CustomApiTool,
  CustomApiToolInput,
  CustomApiToolTestResult,
  AgentList,
  ApiKeyPublic,
  CaptchaChallenge,
  CardInput,
  CostBreakdown,
  CostGroupBy,
  CostSummary,
  DashboardMetrics,
  HumanCheckFields,
  DocumentMeta,
  LLMProvider,
  MarketplaceItem,
  MarketplaceItemPreview,
  MarketplacePublishInput,
  MarketplaceReview,
  MarketplaceReviewInput,
  MarketplaceReviewList,
  MarketplaceStatus,
  MfaChallenge,
  PaymentMethodPublic,
  PlanPublic,
  PlanPublicListing,
  RecoveryCodes,
  ReportInput,
  ReportStatus,
  SessionInfo,
  SubscriptionPlan,
  SubscriptionPublic,
  TaskCreated,
  TaskListResponse,
  TaskState,
  TaskTrace,
  TokenUsage,
  TraceSummary,
  ToolCatalogItem,
  TwoFactorSetup,
  UserPublic,
  UserRole,
} from '@/types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Turn a FastAPI error body into a human-readable message. FastAPI returns a
 * string `detail` for raised HTTPExceptions (400/401/403/...) but an array of
 * `{loc, msg}` objects for 422 request-validation errors. Surface the first
 * validation message instead of a generic fallback so users learn what to fix.
 */
function extractDetail(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null | undefined)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === 'string') return first.msg;
  }
  return fallback;
}

// --- Token storage ---

/**
 * The access token, held in this module for the lifetime of the document and
 * persisted nowhere.
 *
 * Its other half, the refresh token, rides in an httpOnly cookie this code
 * cannot read (backend `core/cookies.py`). Neither is in `localStorage`, so an
 * XSS foothold can spend the current 30-minute access token and nothing more —
 * it cannot walk off with a 7-day session (CLAUDE.md §8, "Token storage").
 *
 * The consequence to keep in mind everywhere else: a page load starts with no
 * access token and has to ask `/auth/refresh` for one.
 */
let accessToken: string | undefined;

export const accessTokenStore = {
  get(): string | undefined {
    return accessToken;
  },
  set(token: string): void {
    accessToken = token;
  },
  clear(): void {
    accessToken = undefined;
  },
};

/**
 * Drop the tokens that sessions predating the cookie change left behind.
 *
 * Nothing reads them any more, so leaving them would mean a live refresh token
 * sitting in a store any script on the origin can read — exactly what this
 * change exists to end. The keys are inlined rather than re-exported as
 * constants, which would keep the names alive as an API.
 *
 * Remove after the release following v0.3 (added 2026-07).
 */
function purgeLegacyTokenStorage(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem('maestro.access_token');
    window.localStorage.removeItem('maestro.refresh_token');
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). Nothing
    // depends on the purge succeeding.
  }
}

purgeLegacyTokenStorage();

/**
 * Resolve the base every request is prefixed with.
 *
 * In the browser an empty base means same-origin, which is what the production
 * reverse proxy serves. On the server there is no origin to be relative to —
 * `/pricing` and `/templates` are force-dynamic server components that fetch
 * from inside the container, and Node's fetch rejects a relative URL — so the
 * server needs an absolute one. `INTERNAL_API_ORIGIN` names the backend on the
 * private network; development falls back to the absolute localhost base.
 */
function apiBase(): string {
  if (typeof window !== 'undefined') return API_BASE_URL;
  if (process.env.INTERNAL_API_ORIGIN) return process.env.INTERNAL_API_ORIGIN;
  return API_BASE_URL.startsWith('http') ? API_BASE_URL : 'http://backend:8000';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT' | 'PATCH';
  body?: unknown;
  auth?: boolean;
  retryOn401?: boolean;
  /** Let the request outlive the page that started it (sign-out revocation). */
  keepalive?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    auth = true,
    retryOn401 = true,
    keepalive,
  } = options;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  if (auth) {
    const token = accessTokenStore.get();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${apiBase()}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    // Required, not cosmetic: the refresh cookie is what keeps a session alive
    // across reloads, and development runs the app on :3000 against the API on
    // :8000 — same site, but cross-origin, where the default `same-origin`
    // credentials mode would silently drop it.
    credentials: 'include',
    keepalive,
  });

  // Transparent one-shot refresh on expired access token.
  if (response.status === 401 && auth && retryOn401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, { ...options, retryOn401: false });
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(data, 'An error occurred.'));
  }
  return data as T;
}

// Decode the `exp` claim (ms epoch) of a JWT without verifying it — enough to
// know client-side whether the backend will still accept the token.
function jwtExpiryMs(token: string): number | undefined {
  try {
    const part = token.split('.')[1] ?? '';
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(window.atob(base64)) as { exp?: number };
    return typeof payload.exp === 'number' ? payload.exp * 1000 : undefined;
  } catch {
    return undefined;
  }
}

// Refresh this early so a token handed to a WebSocket handshake cannot expire
// mid-flight.
const TOKEN_EXPIRY_MARGIN_MS = 60_000;

/**
 * Return an access token the backend will accept, refreshing it first when it
 * is missing, expired or about to expire. Returns undefined only when no valid
 * session remains (the refresh cookie is gone, expired or revoked).
 *
 * "Missing" is the normal case on a fresh page load, not an edge case: the
 * access token is held in memory, so a reload always starts without one.
 */
export async function ensureFreshAccessToken(): Promise<string | undefined> {
  const token = accessTokenStore.get();
  if (token) {
    const exp = jwtExpiryMs(token);
    if (exp === undefined || exp - Date.now() > TOKEN_EXPIRY_MARGIN_MS) {
      return token;
    }
  }
  return (await tryRefresh()) ? accessTokenStore.get() : undefined;
}

// Coalesce concurrent refreshes *within this document* into one in-flight
// rotation — the dashboard's parallel metric calls, React StrictMode's
// double-invoked effect. Without it each would replay the same refresh cookie,
// and the backend's reuse-detection reads a replay as token theft and revokes
// the whole session family.
//
// This does not replace `withRefreshLock`, which handles the same hazard
// *across* documents. Both are needed: neither one sees the other's tabs.
let refreshInflight: Promise<boolean> | undefined;

async function tryRefresh(): Promise<boolean> {
  if (refreshInflight) return refreshInflight;
  refreshInflight = withRefreshLock(async () => {
    try {
      // No body: the refresh token travels only as an httpOnly cookie, which
      // `credentials: 'include'` attaches. `retryOn401` off because a 401 here
      // *is* the failure — retrying would recurse.
      const tokens = await request<AccessTokenResponse>('/api/v1/auth/refresh', {
        method: 'POST',
        auth: false,
        retryOn401: false,
      });
      accessTokenStore.set(tokens.access_token);
      return true;
    } catch {
      accessTokenStore.clear();
      return false;
    }
  });
  try {
    return await refreshInflight;
  } finally {
    refreshInflight = undefined;
  }
}

// Multipart upload (bypasses the JSON request helper; sets no Content-Type so
// the browser adds the multipart boundary).
async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  const headers: Record<string, string> = {};
  const token = accessTokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers,
    body: form,
    credentials: 'include',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(data, 'Upload failed.'));
  }
  return data as T;
}

// --- Endpoints ---

export const api = {
  /**
   * Create an account.
   *
   * Resolves 202 with the same body whether the address was free or already
   * registered — the endpoint deliberately reveals nothing — so this response
   * must never be branched on to infer whether an account was created.
   */
  register(
    email: string,
    password: string,
    display_name?: string,
    guard?: HumanCheckFields,
  ) {
    return request<{ detail: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password, display_name, ...guard },
      auth: false,
    });
  },

  /**
   * Fetch the form challenge for a public form.
   *
   * Public, and on its own rate-limit tier: rendering the register page spends
   * one, so it must not share the bucket that guards credential stuffing.
   */
  challenge() {
    return request<CaptchaChallenge>('/api/v1/auth/challenge', {
      method: 'GET',
      auth: false,
    });
  },

  /**
   * Log in. Returns an access token on success, or an MFA challenge when the
   * account has 2FA enabled — in which case no tokens are issued and the caller
   * must complete `loginVerifyTotp`. The refresh half arrives as an httpOnly
   * cookie the browser stores on its own; this code never sees it.
   */
  async login(
    email: string,
    password: string,
  ): Promise<AccessTokenResponse | MfaChallenge> {
    const result = await request<AccessTokenResponse | MfaChallenge>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: { email, password },
        auth: false,
      },
    );
    if ('access_token' in result) {
      accessTokenStore.set(result.access_token);
    }
    return result;
  },

  /** Complete a 2FA login with a TOTP or recovery code; holds the access token. */
  async loginVerifyTotp(
    mfa_token: string,
    code: string,
  ): Promise<AccessTokenResponse> {
    const tokens = await request<AccessTokenResponse>('/api/v1/auth/login/totp', {
      method: 'POST',
      body: { mfa_token, code },
      auth: false,
    });
    accessTokenStore.set(tokens.access_token);
    return tokens;
  },

  /**
   * Revoke this session's family server-side and expire the refresh cookie.
   *
   * `auth: false` because the cookie is what authenticates it — sending the
   * access token would only arm the 401→refresh retry for no benefit.
   * `keepalive` so the revocation survives the navigation that follows a
   * sign-out click.
   */
  logout(): Promise<void> {
    return request<void>('/api/v1/auth/logout', {
      method: 'POST',
      auth: false,
      keepalive: true,
    });
  },

  // --- Email verification & password reset ---

  /** Redeem an emailed verification link. Public (works signed out). */
  verifyEmail(token: string) {
    return request<{ detail: string }>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: { token },
      auth: false,
    });
  },

  /**
   * Redeem the numeric code from a verification email.
   *
   * Requires a session, unlike `verifyEmail`: six digits are not unique, so
   * the backend can only look a code up within one account's rows.
   */
  verifyEmailCode(code: string) {
    return request<{ detail: string }>('/api/v1/auth/verify-email/code', {
      method: 'POST',
      body: { code },
    });
  },

  /**
   * Ask to move the account to a new address.
   *
   * Nothing changes until the new inbox confirms. Always resolves 202 with the
   * same body whether or not the target is already registered, so it must not
   * be branched on.
   */
  requestEmailChange(new_email: string, current_password: string) {
    return request<{ detail: string }>('/api/v1/users/me/email', {
      method: 'POST',
      body: { new_email, current_password },
    });
  },

  /** Redeem an email-change link. Public (works signed out). */
  confirmEmailChange(token: string) {
    return request<{ detail: string }>('/api/v1/auth/change-email', {
      method: 'POST',
      body: { token },
      auth: false,
    });
  },

  /** Redeem the code from an email-change confirmation. Needs a session. */
  confirmEmailChangeCode(code: string) {
    return request<{ detail: string }>('/api/v1/auth/change-email/code', {
      method: 'POST',
      body: { code },
    });
  },

  /** Rotate the verification token and re-send the email. */
  resendVerification() {
    return request<{ detail: string }>('/api/v1/auth/resend-verification', {
      method: 'POST',
    });
  },

  /** Always resolves 202 — the response never reveals account existence. */
  forgotPassword(email: string, guard?: HumanCheckFields) {
    return request<{ detail: string }>('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: { email, ...guard },
      auth: false,
    });
  },

  /** Redeem a reset link. The backend revokes every existing session. */
  resetPassword(token: string, new_password: string) {
    return request<{ detail: string }>('/api/v1/auth/reset-password', {
      method: 'POST',
      body: { token, new_password },
      auth: false,
    });
  },

  // --- Users (current profile) ---

  getCurrentUser() {
    return request<UserPublic>('/api/v1/users/me');
  },

  updateProfile(input: {
    display_name?: string;
    // null resets the default brain back to the local model.
    default_provider?: LLMProvider | null;
    // null clears the field. Avatar is a monogram (palette key + emoji), no blob.
    bio?: string | null;
    avatar_color?: string | null;
    avatar_emoji?: string | null;
    // Account preferences.
    timezone?: string | null;
    default_reviewer_enabled?: boolean;
    default_tracing_enabled?: boolean;
    // Per-role model pins. Whole-map replace; null (or {}) clears all pins.
    model_preferences?: Record<string, string> | null;
  }) {
    return request<UserPublic>('/api/v1/users/me', {
      method: 'PATCH',
      body: input,
    });
  },

  changePassword(
    current_password: string,
    new_password: string,
    revoke_other_sessions = true,
  ) {
    return request<void>('/api/v1/users/me/password', {
      method: 'POST',
      body: { current_password, new_password, revoke_other_sessions },
    });
  },

  // --- Active sessions ---

  listSessions() {
    return request<SessionInfo[]>('/api/v1/users/me/sessions');
  },

  revokeSession(id: string) {
    return request<void>(`/api/v1/users/me/sessions/${id}`, { method: 'DELETE' });
  },

  revokeOtherSessions() {
    return request<void>('/api/v1/users/me/sessions/revoke-others', {
      method: 'POST',
    });
  },

  // --- Two-factor auth (TOTP) ---

  setup2fa() {
    return request<TwoFactorSetup>('/api/v1/users/me/2fa/setup', {
      method: 'POST',
    });
  },

  /** Confirm the pending secret; returns the one-time recovery codes. */
  enable2fa(password: string, code: string) {
    return request<RecoveryCodes>('/api/v1/users/me/2fa/enable', {
      method: 'POST',
      body: { password, code },
    });
  },

  disable2fa(password: string, code?: string) {
    return request<UserPublic>('/api/v1/users/me/2fa/disable', {
      method: 'POST',
      body: { password, code },
    });
  },

  /** Locks the account and starts the grace period. Nothing is destroyed yet. */
  requestAccountDeletion(password: string) {
    return request<AccountDeletionStatus>('/api/v1/users/me', {
      method: 'DELETE',
      body: { password },
    });
  },

  /** Restores an account scheduled for deletion. */
  cancelAccountDeletion() {
    return request<UserPublic>('/api/v1/users/me/deletion/cancel', {
      method: 'POST',
    });
  },

  /**
   * Downloads everything the platform holds about the user (GDPR Art.20).
   * A plain link cannot carry the bearer token, so fetch it and hand the
   * browser a blob.
   */
  async exportAccountData(): Promise<void> {
    const token = await ensureFreshAccessToken();
    const response = await fetch(`${apiBase()}/api/v1/users/me/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      throw new ApiError(response.status, 'Your data could not be exported.');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement('a');
      link.href = url;
      link.download = `maestro-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  },

  // --- Billing ---

  getPlans() {
    return request<PlanPublic[]>('/api/v1/billing/plans');
  },

  /**
   * List prices for the public pricing page. Anonymous, so it never touches
   * `accessTokenStore` and is safe to await in a server component.
   */
  getPublicPlans() {
    return request<PlanPublicListing[]>('/api/v1/billing/plans/public', {
      auth: false,
    });
  },

  getSubscription() {
    return request<SubscriptionPublic>('/api/v1/billing/subscription');
  },

  getPaymentMethod() {
    return request<PaymentMethodPublic | undefined>('/api/v1/billing/payment-method');
  },

  /** The card number is sent once and never persisted client-side. */
  subscribe(plan: SubscriptionPlan, card: CardInput) {
    return request<SubscriptionPublic>('/api/v1/billing/subscribe', {
      method: 'POST',
      body: { plan, card },
    });
  },

  cancelSubscription() {
    return request<SubscriptionPublic>('/api/v1/billing/cancel', {
      method: 'POST',
    });
  },

  listApiKeys() {
    return request<ApiKeyPublic[]>('/api/v1/api-keys');
  },

  createApiKey(
    provider: LLMProvider,
    label: string,
    key: string,
    // Only for the custom OpenAI-compatible provider.
    baseUrl?: string,
    model?: string,
  ) {
    return request<ApiKeyPublic>('/api/v1/api-keys', {
      method: 'POST',
      body: {
        provider,
        label,
        key,
        base_url: baseUrl,
        model,
      },
    });
  },

  deleteApiKey(id: string) {
    return request<void>(`/api/v1/api-keys/${id}`, { method: 'DELETE' });
  },

  startTask(input: {
    prompt: string;
    provider: LLMProvider;
    reviewer_enabled: boolean;
    allow_questions?: boolean;
    // Record a span waterfall with per-call tokens and cost. Omit to inherit
    // the user's default, then the server-wide TRACING_ENABLED.
    tracing_enabled?: boolean;
    // User-selected domain agent; omit to let the orchestrator route.
    domain?: string;
  }) {
    return request<TaskCreated>('/api/v1/tasks', { method: 'POST', body: input });
  },

  getTask(taskId: string) {
    return request<TaskState>(`/api/v1/tasks/${taskId}`);
  },

  listTasks(limit = TASK_HISTORY_PAGE_SIZE, offset = 0) {
    return request<TaskListResponse>(
      `/api/v1/tasks?limit=${limit}&offset=${offset}`,
    );
  },

  cancelTask(taskId: string) {
    return request<{ cancelled: boolean }>(`/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
    });
  },

  deleteTask(taskId: string) {
    return request<void>(`/api/v1/tasks/${taskId}`, { method: 'DELETE' });
  },

  answerTask(taskId: string, answer: string) {
    return request<{ delivered: boolean }>(`/api/v1/tasks/${taskId}/answer`, {
      method: 'POST',
      body: { answer },
    });
  },

  // --- Dashboard ---

  dashboardMetrics() {
    return request<DashboardMetrics>('/api/v1/dashboard/metrics');
  },

  tokenUsage() {
    return request<TokenUsage>('/api/v1/dashboard/token-usage');
  },

  costSummary() {
    return request<CostSummary>('/api/v1/dashboard/cost-summary');
  },

  /**
   * Trace-derived cost buckets over the last `days`, grouped by day, model or
   * domain. Empty (total 0, no buckets) when server-side tracing is disabled.
   */
  costBreakdown(days = 30, groupBy: CostGroupBy = 'day') {
    return request<CostBreakdown>(
      `/api/v1/dashboard/costs?days=${days}&group_by=${groupBy}`,
    );
  },

  // --- Traces (execution spans) ---

  /** Ordered execution spans for a task. Empty `spans` when tracing is off. */
  getTaskTrace(taskId: string) {
    return request<TaskTrace>(`/api/v1/tasks/${taskId}/trace`);
  },

  /** Per-node token/cost rollup for a task's trace. Zeroed when tracing is off. */
  getTaskTraceSummary(taskId: string) {
    return request<TraceSummary>(`/api/v1/tasks/${taskId}/trace/summary`);
  },

  // --- Agents (custom configurations) ---

  listAgents() {
    return request<AgentList>('/api/v1/agents');
  },

  listTools() {
    return request<ToolCatalogItem[]>('/api/v1/agents/tools');
  },

  getAgent(id: string) {
    return request<AgentConfig>(`/api/v1/agents/${id}`);
  },

  createAgent(input: AgentConfigInput) {
    return request<AgentConfig>('/api/v1/agents', { method: 'POST', body: input });
  },

  updateAgent(id: string, input: AgentConfigInput) {
    return request<AgentConfig>(`/api/v1/agents/${id}`, {
      method: 'PUT',
      body: input,
    });
  },

  deleteAgent(id: string) {
    return request<void>(`/api/v1/agents/${id}`, { method: 'DELETE' });
  },

  // --- Custom API tools (user-registered HTTP endpoints) ---

  listCustomApiTools() {
    return request<CustomApiTool[]>('/api/v1/custom-api-tools');
  },

  createCustomApiTool(input: CustomApiToolInput) {
    return request<CustomApiTool>('/api/v1/custom-api-tools', {
      method: 'POST',
      body: input,
    });
  },

  // Partial by design: omitting `secret` leaves the stored credential in place,
  // so renaming a tool cannot silently break a working call.
  updateCustomApiTool(id: string, input: Partial<CustomApiToolInput>) {
    return request<CustomApiTool>(`/api/v1/custom-api-tools/${id}`, {
      method: 'PATCH',
      body: input,
    });
  },

  deleteCustomApiTool(id: string) {
    return request<void>(`/api/v1/custom-api-tools/${id}`, { method: 'DELETE' });
  },

  testCustomApiTool(id: string, args: Record<string, string>) {
    return request<CustomApiToolTestResult>(
      `/api/v1/custom-api-tools/${id}/test`,
      { method: 'POST', body: { args } },
    );
  },

  // --- Marketplace ---

  listMarketplace() {
    return request<MarketplaceItem[]>('/api/v1/marketplace');
  },

  /**
   * Published teams for the public landing page, featured first. Anonymous, so
   * it never touches `accessTokenStore` and is safe to await in a server component.
   */
  listShowcase() {
    return request<MarketplaceItemPreview[]>('/api/v1/marketplace/showcase', {
      auth: false,
    });
  },

  publishMarketplace(input: MarketplacePublishInput) {
    return request<MarketplaceItem>('/api/v1/marketplace', {
      method: 'POST',
      body: input,
    });
  },

  installMarketplace(id: string) {
    return request<AgentConfig>(`/api/v1/marketplace/${id}/install`, {
      method: 'POST',
    });
  },

  listReviews(id: string, limit = REVIEWS_PAGE_SIZE, offset = 0) {
    return request<MarketplaceReviewList>(
      `/api/v1/marketplace/${id}/reviews?limit=${limit}&offset=${offset}`,
    );
  },

  /** Create or replace the caller's review of an item (server-side upsert). */
  submitReview(id: string, input: MarketplaceReviewInput) {
    return request<MarketplaceReview>(`/api/v1/marketplace/${id}/reviews`, {
      method: 'POST',
      body: input,
    });
  },

  /** Flag a marketplace item for moderator review. */
  reportItem(id: string, input: ReportInput) {
    return request<{ detail: string }>(`/api/v1/marketplace/${id}/report`, {
      method: 'POST',
      body: input,
    });
  },

  /** Flag a specific review for moderator review. */
  reportReview(reviewId: string, input: ReportInput) {
    return request<{ detail: string }>(
      `/api/v1/marketplace/reviews/${reviewId}/report`,
      { method: 'POST', body: input },
    );
  },

  // --- Documents (RAG knowledge base) ---

  listDocuments() {
    return request<DocumentMeta[]>('/api/v1/documents');
  },

  uploadDocument(file: File) {
    return uploadFile<DocumentMeta>('/api/v1/documents', file);
  },

  deleteDocument(id: string) {
    return request<void>(`/api/v1/documents/${id}`, { method: 'DELETE' });
  },

  // --- Admin / moderation (gated server-side by the admin role) ---

  adminOverview() {
    return request<AdminOverview>('/api/v1/admin/overview');
  },

  adminListUsers(query?: string, limit = 50, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (query) params.set('q', query);
    return request<AdminUserRow[]>(`/api/v1/admin/users?${params.toString()}`);
  },

  adminGetUser(id: string) {
    return request<AdminUserDetail>(`/api/v1/admin/users/${id}`);
  },

  adminSuspendUser(id: string, reason?: string) {
    return request<AdminUserRow>(`/api/v1/admin/users/${id}/suspend`, {
      method: 'POST',
      body: { reason },
    });
  },

  adminUnsuspendUser(id: string) {
    return request<AdminUserRow>(`/api/v1/admin/users/${id}/unsuspend`, {
      method: 'POST',
    });
  },

  adminSetUserRole(id: string, role: UserRole) {
    return request<AdminUserRow>(`/api/v1/admin/users/${id}/role`, {
      method: 'POST',
      body: { role },
    });
  },

  adminListItems(status?: MarketplaceStatus, limit = 50, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    return request<AdminMarketplaceItem[]>(
      `/api/v1/admin/marketplace/items?${params.toString()}`,
    );
  },

  adminSetItemStatus(id: string, status: MarketplaceStatus, reason?: string) {
    return request<AdminMarketplaceItem>(
      `/api/v1/admin/marketplace/items/${id}/status`,
      { method: 'POST', body: { status, reason } },
    );
  },

  adminListItemReviews(id: string) {
    return request<AdminReview[]>(`/api/v1/admin/marketplace/items/${id}/reviews`);
  },

  adminHideReview(reviewId: string, hidden: boolean, reason?: string) {
    return request<AdminReview>(
      `/api/v1/admin/marketplace/reviews/${reviewId}/hide`,
      { method: 'POST', body: { hidden, reason } },
    );
  },

  adminDeleteAgent(agentId: string, reason?: string) {
    const params = reason ? `?reason=${encodeURIComponent(reason)}` : '';
    return request<{ detail: string }>(`/api/v1/admin/agents/${agentId}${params}`, {
      method: 'DELETE',
    });
  },

  adminListReports(status?: ReportStatus, limit = 50, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    return request<AdminReport[]>(`/api/v1/admin/reports?${params.toString()}`);
  },

  adminResolveReport(id: string, resolution: ReportStatus) {
    return request<AdminReport>(`/api/v1/admin/reports/${id}/resolve`, {
      method: 'POST',
      body: { resolution },
    });
  },

  adminListAudit(limit = 50, offset = 0) {
    return request<AdminAuditEntry[]>(
      `/api/v1/admin/audit?limit=${limit}&offset=${offset}`,
    );
  },
};
