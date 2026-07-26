// Single source of truth for BYOK providers on the frontend. Every provider
// list the UI needs is DERIVED from PROVIDERS below — the ids mirror the
// backend `LLMProvider` enum (backend/app/core/constants.py), in the same
// order. Add a provider here (plus the backend enum/adapter and, if it has a
// freely-licensed mark, a glyph in `components/provider-glyphs.ts`) and it
// flows to the key screen, the brain selector and the task-start screen
// automatically.
//
// `backend/tests/test_provider_frontend_parity.py` fails CI if this registry,
// the `LLMProvider` union in `types/index.ts`, or the chat/service flags below
// drift from the backend.
//
// Every `docsUrl` was requested live on 2026-07-26 and none returned 404.
// Console links that redirect to a sign-in page are intentional: the user logs
// in and lands on the key screen.

import type { LLMProvider } from '@/types';

export type ProviderCategory = 'ai' | 'service';
export type ProviderKind = 'openai-compat' | 'anthropic' | 'ollama' | 'custom' | 'service';

/** Sub-heading a provider is filed under in the picker. */
export type AiProviderGroup = 'local' | 'frontier' | 'inference' | 'gateway';
export type ServiceProviderGroup =
  | 'social'
  | 'dev'
  | 'productivity'
  | 'comms'
  | 'commerce'
  | 'data';
export type ProviderGroup = AiProviderGroup | ServiceProviderGroup;

export const PROVIDER_GROUP_LABELS: Record<ProviderGroup, string> = {
  local: 'Local',
  frontier: 'Model Labs',
  inference: 'Inference Clouds',
  gateway: 'Gateways & Custom',
  social: 'Social & Community',
  dev: 'Developer & Cloud',
  productivity: 'Productivity & Design',
  comms: 'Email & Messaging',
  commerce: 'Commerce & CRM',
  data: 'Search & Data',
};

export interface ProviderMeta {
  id: LLMProvider;
  label: string;
  category: ProviderCategory;
  kind: ProviderKind;
  /** Usable as a brain / can drive tasks (mirrors backend LLM_CHAT_PROVIDERS). */
  chat: boolean;
  /** Picker sub-heading this provider is filed under. */
  group: ProviderGroup;
  /** Short hint shown on the brain selector cards. */
  hint?: string;
  /** Custom endpoints also need a base URL + model, not just a key. */
  needsEndpoint?: boolean;
  /** Example model id shown as the (optional) model-field placeholder. */
  modelPlaceholder?: string;
  /** Where the user creates the key. Omitted when there is no stable page. */
  docsUrl?: string;
}

export const PROVIDERS: readonly ProviderMeta[] = [
  // --- AI brains -----------------------------------------------------------
  {
    id: 'ollama',
    label: 'Local LLM (Ollama)',
    category: 'ai',
    kind: 'ollama',
    chat: true,
    group: 'local',
    hint: 'No API key required',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK',
    modelPlaceholder: 'gpt-4o',
    docsUrl: 'https://platform.openai.com/api-keys',
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    category: 'ai',
    kind: 'anthropic',
    chat: true,
    group: 'frontier',
    hint: 'BYOK',
    modelPlaceholder: 'claude-sonnet-5',
    docsUrl: 'https://platform.claude.com/settings/keys',
  },
  {
    id: 'gemini',
    label: 'Google Gemini',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'With your own key',
    modelPlaceholder: 'gemini-2.5-pro',
    docsUrl: 'https://aistudio.google.com/apikey',
  },
  {
    id: 'groq',
    label: 'Groq',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK — fast inference',
    docsUrl: 'https://console.groq.com/keys',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK',
    docsUrl: 'https://platform.deepseek.com/api_keys',
  },
  {
    id: 'mistral',
    label: 'Mistral AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK',
    docsUrl: 'https://console.mistral.ai/api-keys',
  },
  {
    id: 'xai',
    label: 'xAI (Grok)',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK',
    docsUrl: 'https://console.x.ai/',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'gateway',
    hint: 'BYOK — gateway to many models',
    docsUrl: 'https://openrouter.ai/keys',
  },
  {
    id: 'together',
    label: 'Together AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    docsUrl: 'https://api.together.ai/settings/api-keys',
  },
  {
    id: 'perplexity',
    label: 'Perplexity',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK — online Sonar models',
    docsUrl: 'https://www.perplexity.ai/account/api/keys',
  },
  {
    id: 'cerebras',
    label: 'Cerebras',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK — wafer-scale inference',
    docsUrl: 'https://cloud.cerebras.ai/platform/',
  },
  {
    id: 'fireworks',
    label: 'Fireworks AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    // Fireworks rejects a bare model name; the account path prefix is required.
    modelPlaceholder: 'accounts/fireworks/models/gpt-oss-120b',
    docsUrl: 'https://app.fireworks.ai/settings/users/api-keys',
  },
  {
    id: 'deepinfra',
    label: 'DeepInfra',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    docsUrl: 'https://deepinfra.com/dash/api_keys',
  },
  {
    id: 'sambanova',
    label: 'SambaNova',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    docsUrl: 'https://cloud.sambanova.ai/apis',
  },
  {
    id: 'nebius',
    label: 'Nebius Token Factory',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK — formerly AI Studio',
    docsUrl: 'https://docs.tokenfactory.nebius.com/quickstart',
  },
  {
    id: 'hyperbolic',
    label: 'Hyperbolic',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    docsUrl: 'https://app.hyperbolic.ai/settings',
  },
  {
    id: 'novita',
    label: 'Novita AI',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK',
    docsUrl: 'https://novita.ai/settings/key-management',
  },
  {
    id: 'huggingface',
    label: 'Hugging Face',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'inference',
    hint: 'BYOK — Inference Providers router',
    docsUrl: 'https://huggingface.co/settings/tokens',
  },
  {
    id: 'cohere',
    label: 'Cohere',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    // Cohere retired its floating aliases; only dated snapshots resolve.
    hint: 'BYOK — Command models',
    modelPlaceholder: 'command-a-plus-05-2026',
    docsUrl: 'https://dashboard.cohere.com/api-keys',
  },
  {
    id: 'moonshot',
    label: 'Moonshot (Kimi)',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    // Keys are bound to the host they were issued on; a China-registered key
    // will not authenticate against the international endpoint.
    hint: 'BYOK — international endpoint',
    docsUrl: 'https://platform.kimi.ai/console/api-keys',
  },
  {
    id: 'zai',
    label: 'Z.ai (GLM)',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK — standard API keys',
    docsUrl: 'https://z.ai/manage-apikey/apikey-list',
  },
  {
    id: 'qwen',
    label: 'Alibaba Qwen',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK — DashScope international',
    docsUrl: 'https://www.alibabacloud.com/help/en/model-studio/get-api-key',
  },
  {
    id: 'ai21',
    label: 'AI21 Labs',
    category: 'ai',
    kind: 'openai-compat',
    chat: true,
    group: 'frontier',
    hint: 'BYOK — Jamba models',
    docsUrl: 'https://studio.ai21.com/v2/account/api-key',
  },
  {
    id: 'custom',
    label: 'Custom (OpenAI-compatible)',
    category: 'ai',
    kind: 'custom',
    chat: true,
    group: 'gateway',
    // Azure OpenAI, vLLM and LiteLLM all land here rather than getting their own
    // entry: each needs a per-key base URL, which is exactly what this provides.
    hint: 'Your own endpoint — Azure OpenAI, vLLM, LiteLLM',
    needsEndpoint: true,
    docsUrl: 'https://learn.microsoft.com/en-us/azure/ai-foundry/openai/',
  },

  // --- Service integrations ------------------------------------------------
  // Keys are stored encrypted for every provider here. Six are read by a tool
  // today (GitHub, X, Google Maps, Discord, Slack, Telegram); the rest are
  // staged for upcoming integrations, which the page states plainly.
  // Social & community
  {
    id: 'x',
    label: 'X (Twitter)',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://docs.x.com/x-api/getting-started/getting-access',
  },
  {
    id: 'instagram',
    label: 'Instagram',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl:
      'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/get-started',
  },
  {
    id: 'reddit',
    label: 'Reddit',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://www.reddit.com/prefs/apps',
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://www.linkedin.com/developers/apps/new',
  },
  {
    id: 'youtube',
    label: 'YouTube',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://developers.google.com/youtube/registering_an_application',
  },
  {
    id: 'tiktok',
    label: 'TikTok',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://developers.tiktok.com/doc/getting-started-create-an-app/',
  },
  {
    id: 'bluesky',
    label: 'Bluesky',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://bsky.app/settings/app-passwords',
  },
  {
    id: 'pinterest',
    label: 'Pinterest',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://developers.pinterest.com/apps/',
  },
  {
    id: 'discord',
    label: 'Discord',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://discord.com/developers/applications',
  },
  {
    id: 'slack',
    label: 'Slack',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    docsUrl: 'https://api.slack.com/apps',
  },
  {
    id: 'telegram',
    label: 'Telegram',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'social',
    // The docs anchor, not t.me/BotFather: that link is a dead end for anyone
    // without the desktop app installed.
    docsUrl: 'https://core.telegram.org/bots/features#botfather',
  },
  // Developer & cloud
  {
    id: 'github',
    label: 'GitHub',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'dev',
    docsUrl: 'https://github.com/settings/personal-access-tokens',
  },
  {
    id: 'gitlab',
    label: 'GitLab',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'dev',
    // Docs rather than the console, so the link also serves self-hosted users.
    docsUrl: 'https://docs.gitlab.com/user/profile/personal_access_tokens/',
  },
  {
    id: 'vercel',
    label: 'Vercel',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'dev',
    docsUrl: 'https://vercel.com/account/tokens',
  },
  {
    id: 'cloudflare',
    label: 'Cloudflare',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'dev',
    docsUrl:
      'https://developers.cloudflare.com/fundamentals/api/get-started/create-token/',
  },
  {
    id: 'sentry',
    label: 'Sentry',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'dev',
    docsUrl: 'https://sentry.io/settings/account/api/auth-tokens/',
  },
  // Productivity & design
  {
    id: 'notion',
    label: 'Notion',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://developers.notion.com/guides/get-started/authorization',
  },
  {
    id: 'jira',
    label: 'Jira',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://id.atlassian.com/manage-profile/security/api-tokens',
  },
  {
    id: 'linear',
    label: 'Linear',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://linear.app/settings/account/security',
  },
  {
    id: 'trello',
    label: 'Trello',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl:
      'https://support.atlassian.com/trello/docs/getting-started-with-trello-rest-api/',
  },
  {
    id: 'asana',
    label: 'Asana',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://app.asana.com/0/my-apps',
  },
  {
    id: 'clickup',
    label: 'ClickUp',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://developer.clickup.com/docs/authentication',
  },
  {
    id: 'airtable',
    label: 'Airtable',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://airtable.com/create/tokens',
  },
  {
    id: 'figma',
    label: 'Figma',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl:
      'https://help.figma.com/hc/en-us/articles/8085703771159-Manage-personal-access-tokens',
  },
  {
    id: 'google_drive',
    label: 'Google Drive',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'productivity',
    docsUrl: 'https://developers.google.com/workspace/drive/api/quickstart/python',
  },
  // Email & messaging
  {
    id: 'gmail',
    label: 'Gmail',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'comms',
    docsUrl: 'https://developers.google.com/workspace/gmail/api/quickstart/python',
  },
  {
    id: 'resend',
    label: 'Resend',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'comms',
    docsUrl: 'https://resend.com/api-keys',
  },
  {
    id: 'sendgrid',
    label: 'SendGrid',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'comms',
    docsUrl: 'https://www.twilio.com/docs/sendgrid/ui/account-and-settings/api-keys',
  },
  {
    id: 'mailchimp',
    label: 'Mailchimp',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'comms',
    docsUrl: 'https://mailchimp.com/help/about-api-keys/',
  },
  {
    id: 'twilio',
    label: 'Twilio',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'comms',
    docsUrl: 'https://www.twilio.com/docs/iam/api-keys/keys-in-console',
  },
  // Commerce & CRM
  {
    id: 'stripe',
    label: 'Stripe',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'commerce',
    docsUrl: 'https://dashboard.stripe.com/apikeys',
  },
  {
    id: 'shopify',
    label: 'Shopify',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'commerce',
    docsUrl:
      'https://shopify.dev/docs/apps/build/dev-dashboard/get-api-access-tokens',
  },
  {
    id: 'hubspot',
    label: 'HubSpot',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'commerce',
    docsUrl:
      'https://developers.hubspot.com/docs/apps/legacy-apps/private-apps/overview',
  },
  {
    id: 'zendesk',
    label: 'Zendesk',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'commerce',
    docsUrl:
      'https://support.zendesk.com/hc/en-us/articles/4408889192858-Managing-API-token-access-to-the-Zendesk-API',
  },
  // Search & data
  {
    id: 'google_maps',
    label: 'Google Maps',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://console.cloud.google.com/project/_/google/maps-apis/credentials',
  },
  {
    id: 'tavily',
    label: 'Tavily',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://app.tavily.com/home',
  },
  {
    id: 'exa',
    label: 'Exa',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://dashboard.exa.ai/api-keys',
  },
  {
    id: 'serper',
    label: 'Serper',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://serper.dev/dashboard',
  },
  {
    id: 'firecrawl',
    label: 'Firecrawl',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://www.firecrawl.dev/app/api-keys',
  },
  {
    id: 'alpha_vantage',
    label: 'Alpha Vantage',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://www.alphavantage.co/support/#api-key',
  },
  {
    id: 'coingecko',
    label: 'CoinGecko',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://docs.coingecko.com/docs/setting-up-your-api-key',
  },
  {
    id: 'openweather',
    label: 'OpenWeather',
    category: 'service',
    kind: 'service',
    chat: false,
    group: 'data',
    docsUrl: 'https://home.openweathermap.org/api_keys',
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

export interface ProviderGroupBucket {
  group: ProviderGroup;
  label: string;
  items: ProviderMeta[];
}

/**
 * Bucket providers by `group`, preserving catalog order.
 *
 * Ordering is derived rather than declared — group order is the order each
 * group first appears in PROVIDERS, and within a group items keep their catalog
 * position. That keeps PROVIDERS the only thing anyone has to reorder.
 */
export function groupProviders(list: readonly ProviderMeta[]): ProviderGroupBucket[] {
  const buckets = new Map<ProviderGroup, ProviderMeta[]>();
  for (const provider of list) {
    const existing = buckets.get(provider.group);
    if (existing) existing.push(provider);
    else buckets.set(provider.group, [provider]);
  }
  return Array.from(buckets, ([group, items]) => ({
    group,
    label: PROVIDER_GROUP_LABELS[group],
    items,
  }));
}
