// Single source of truth for BYOK providers on the frontend. Every provider
// list the UI needs is DERIVED from PROVIDERS below — the ids mirror the
// backend `LLMProvider` enum (backend/app/core/constants.py). Add a provider
// here (plus the backend enum/adapter and a ProviderIcon glyph) and it flows to
// the key screen, the brain selector and the task-start screen automatically.

import type { LLMProvider } from '@/types';

export type ProviderCategory = 'ai' | 'service';
export type ProviderKind = 'openai-compat' | 'anthropic' | 'ollama' | 'custom' | 'service';

export interface ProviderMeta {
  id: LLMProvider;
  label: string;
  category: ProviderCategory;
  kind: ProviderKind;
  /** Usable as a brain / can drive tasks (mirrors backend LLM_CHAT_PROVIDERS). */
  chat: boolean;
  /** Short hint shown on the brain selector cards. */
  hint?: string;
  /** Custom endpoints also need a base URL + model, not just a key. */
  needsEndpoint?: boolean;
  /** Example model id shown as the (optional) model-field placeholder. */
  modelPlaceholder?: string;
}

export const PROVIDERS: readonly ProviderMeta[] = [
  // --- AI brains -----------------------------------------------------------
  {
    id: 'ollama',
    label: 'Local LLM (Ollama)',
    category: 'ai',
    kind: 'ollama',
    chat: true,
    hint: 'No API key required',
  },
  {
    id: 'gemini',
    label: 'Google Gemini',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'With your own key',
    modelPlaceholder: 'gemini-2.5-pro',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK',
    modelPlaceholder: 'gpt-4o',
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    category: 'ai',
    kind: 'anthropic',
    chat: true,
    hint: 'BYOK',
    modelPlaceholder: 'claude-sonnet-5',
  },
  {
    id: 'groq',
    label: 'Groq',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK — fast inference',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK',
  },
  {
    id: 'mistral',
    label: 'Mistral AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK',
  },
  {
    id: 'xai',
    label: 'xAI (Grok)',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK — gateway to many models',
  },
  {
    id: 'together',
    label: 'Together AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK',
  },
  {
    id: 'perplexity',
    label: 'Perplexity',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    hint: 'BYOK — online Sonar models',
  },
  {
    id: 'custom',
    label: 'Custom (OpenAI-compatible)',
    category: 'ai',
    kind: 'custom',
    chat: true,
    hint: 'Your own endpoint + model',
    needsEndpoint: true,
  },
  // --- Service integrations (stored keys only; no backend consumer yet) -----
  { id: 'x', label: 'X (Twitter)', category: 'service', kind: 'service', chat: false },
  { id: 'github', label: 'GitHub', category: 'service', kind: 'service', chat: false },
  {
    id: 'instagram',
    label: 'Instagram',
    category: 'service',
    kind: 'service',
    chat: false,
  },
  {
    id: 'google_maps',
    label: 'Google Maps',
    category: 'service',
    kind: 'service',
    chat: false,
  },
  { id: 'slack', label: 'Slack', category: 'service', kind: 'service', chat: false },
  { id: 'notion', label: 'Notion', category: 'service', kind: 'service', chat: false },
  { id: 'discord', label: 'Discord', category: 'service', kind: 'service', chat: false },
  {
    id: 'telegram',
    label: 'Telegram',
    category: 'service',
    kind: 'service',
    chat: false,
  },
] as const;

export const PROVIDER_MAP: Record<LLMProvider, ProviderMeta> = Object.fromEntries(
  PROVIDERS.map((p) => [p.id, p]),
) as Record<LLMProvider, ProviderMeta>;

export const AI_PROVIDERS = PROVIDERS.filter((p) => p.category === 'ai');
export const SERVICE_PROVIDERS = PROVIDERS.filter((p) => p.category === 'service');

// Brains offered when adding a key: every AI provider that actually needs one
// (Ollama is local and keyless, so it is excluded here but kept as a default brain).
export const BRAIN_KEY_PROVIDERS = AI_PROVIDERS.filter((p) => p.id !== 'ollama');

// Non-LLM integrations offered under "Connected APIs".
export const CONNECTED_KEY_PROVIDERS = SERVICE_PROVIDERS;

// Providers selectable when starting a task (chat-capable AI providers).
export const TASK_PROVIDERS = AI_PROVIDERS.filter((p) => p.chat);

// Default-brain selector cards (same set as task providers).
export const BRAIN_OPTIONS = TASK_PROVIDERS;

// Classifies stored keys into Brain vs Connected (mirrors LLM_CHAT_PROVIDERS).
export const BRAIN_CHAT_PROVIDERS: ReadonlySet<LLMProvider> = new Set(
  PROVIDERS.filter((p) => p.chat).map((p) => p.id),
);
