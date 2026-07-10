// Central API client. All backend calls go through here (project rule 5.2).

import {
  ACCESS_TOKEN_KEY,
  API_BASE_URL,
  REFRESH_TOKEN_KEY,
  TASK_HISTORY_PAGE_SIZE,
} from '@/lib/constants';
import type {
  AccountDeletionStatus,
  AgentConfig,
  AgentConfigInput,
  AgentList,
  ApiKeyPublic,
  CardInput,
  CostSummary,
  DashboardMetrics,
  DocumentMeta,
  LLMProvider,
  MarketplaceItem,
  MarketplaceItemPreview,
  MarketplacePublishInput,
  PaymentMethodPublic,
  PlanPublic,
  PlanPublicListing,
  SubscriptionPlan,
  SubscriptionPublic,
  TaskCreated,
  TaskListResponse,
  TaskState,
  TokenPair,
  TokenUsage,
  ToolCatalogItem,
  UserPublic,
} from '@/types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// --- Token storage (client-side only) ---

export const tokenStore = {
  getAccess(): string | undefined {
    if (typeof window === 'undefined') return undefined;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? undefined;
  },
  getRefresh(): string | undefined {
    if (typeof window === 'undefined') return undefined;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY) ?? undefined;
  },
  set(tokens: TokenPair): void {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  },
  clear(): void {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

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
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true, retryOn401 = true } = options;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  if (auth) {
    const token = tokenStore.getAccess();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${apiBase()}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
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
    const detail =
      typeof data?.detail === 'string' ? data.detail : 'An error occurred.';
    throw new ApiError(response.status, detail);
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
 * is missing, expired or about to expire. Returns undefined only when no
 * valid session remains (refresh failed or no refresh token).
 */
export async function ensureFreshAccessToken(): Promise<string | undefined> {
  const token = tokenStore.getAccess();
  if (token) {
    const exp = jwtExpiryMs(token);
    if (exp === undefined || exp - Date.now() > TOKEN_EXPIRY_MARGIN_MS) {
      return token;
    }
  }
  return (await tryRefresh()) ? tokenStore.getAccess() : undefined;
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = tokenStore.getRefresh();
  if (!refresh_token) return false;
  try {
    const tokens = await request<TokenPair>('/api/v1/auth/refresh', {
      method: 'POST',
      body: { refresh_token },
      auth: false,
    });
    tokenStore.set(tokens);
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

// Multipart upload (bypasses the JSON request helper; sets no Content-Type so
// the browser adds the multipart boundary).
async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  const headers: Record<string, string> = {};
  const token = tokenStore.getAccess();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers,
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof data?.detail === 'string' ? data.detail : 'Upload failed.';
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

// --- Endpoints ---

export const api = {
  register(email: string, password: string, display_name?: string) {
    return request<UserPublic>('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password, display_name },
      auth: false,
    });
  },

  async login(email: string, password: string): Promise<TokenPair> {
    const tokens = await request<TokenPair>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      auth: false,
    });
    tokenStore.set(tokens);
    return tokens;
  },

  // --- Users (current profile) ---

  getCurrentUser() {
    return request<UserPublic>('/api/v1/users/me');
  },

  updateProfile(input: {
    display_name?: string;
    email?: string;
    // null resets the default brain back to the free local tier.
    default_provider?: LLMProvider | null;
  }) {
    return request<UserPublic>('/api/v1/users/me', {
      method: 'PATCH',
      body: input,
    });
  },

  changePassword(current_password: string, new_password: string) {
    return request<void>('/api/v1/users/me/password', {
      method: 'POST',
      body: { current_password, new_password },
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
   * List prices for the public pricing page — no per-user discount. Anonymous,
   * so it never touches `tokenStore` and is safe to await in a server component.
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

  createApiKey(provider: LLMProvider, label: string, key: string) {
    return request<ApiKeyPublic>('/api/v1/api-keys', {
      method: 'POST',
      body: { provider, label, key },
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

  // --- Marketplace ---

  listMarketplace() {
    return request<MarketplaceItem[]>('/api/v1/marketplace');
  },

  /**
   * Published teams for the public landing page, featured first. Anonymous, so
   * it never touches `tokenStore` and is safe to await in a server component.
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
};
