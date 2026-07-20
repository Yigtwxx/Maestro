'use client';

import { useCallback, useEffect, useState } from 'react';
import { BrainCircuit, Cable } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import DecryptedText from '@/components/DecryptedText';
import { ProviderIcon } from '@/components/ProviderIcon';
import { ModelPreferencesCard } from '@/components/settings/ModelPreferencesCard';
import { PageShell } from '@/components/layout/PageShell';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import {
  BRAIN_CHAT_PROVIDERS,
  BRAIN_KEY_PROVIDERS,
  BRAIN_OPTIONS,
  CONNECTED_KEY_PROVIDERS,
  type ProviderMeta,
} from '@/lib/providers';
import { MODULE_COLOR } from '@/lib/module-colors';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import type { ApiKeyPublic, LLMProvider } from '@/types';

const mc = MODULE_COLOR['api-keys'];

/** Best-effort host of a stored custom endpoint, for the saved-key card. */
function endpointHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Add-key form + masked key cards, parameterized per section. */
function KeySection({
  heading,
  providers,
  keys,
  loading,
  onCreated,
  onDelete,
  anchor,
}: {
  heading: string;
  providers: ProviderMeta[];
  keys: ApiKeyPublic[];
  loading: boolean;
  onCreated: () => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  /** `data-onboarding` id for the submit button, when this section is a tour target. */
  anchor?: string;
}) {
  const [provider, setProvider] = useState<LLMProvider>(providers[0].id);
  const [label, setLabel] = useState('');
  const [secret, setSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  // Bumped per successful save — replays the confirmation flash on the button.
  const [savedNonce, setSavedNonce] = useState(0);

  const providerMeta = providers.find((p) => p.id === provider);
  const needsEndpoint = providerMeta?.needsEndpoint ?? false;
  // Chat providers accept an optional model override (required only for custom).
  const isChat = providerMeta?.chat ?? false;

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      await api.createApiKey(
        provider,
        label,
        secret,
        needsEndpoint ? baseUrl : undefined,
        isChat ? model || undefined : undefined,
      );
      setLabel('');
      setSecret('');
      setBaseUrl('');
      setModel('');
      setSavedNonce((n) => n + 1);
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Key could not be added.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <form
        onSubmit={onAdd}
        className="mb-6 grid gap-4 rounded-lg border border-border bg-surface p-5 sm:grid-cols-2"
      >
        <p className={`text-micro sm:col-span-2 ${mc.text}`}>[ {heading} ]</p>

        <div className="sm:col-span-2">
          <p className="mb-2 text-micro text-muted">Provider</p>
          <div
            role="radiogroup"
            aria-label="Provider"
            className="grid grid-cols-2 gap-2 sm:grid-cols-3"
          >
            {providers.map((p) => {
              const active = p.id === provider;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setProvider(p.id)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg border p-2.5 text-left text-sm transition-all',
                    active
                      ? 'border-module-api-keys bg-surface-2 text-white shadow-glow-mod-api-keys'
                      : 'border-border bg-surface text-muted hover:border-border-bright hover:bg-surface-2',
                  )}
                >
                  <ProviderIcon
                    provider={p.id}
                    className={cn('h-6 w-6 shrink-0', active ? mc.text : 'text-muted')}
                  />
                  <span className="truncate">{p.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <Input
          label="Label"
          placeholder="E.g. Personal OpenAI"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
          module="api-keys"
        />

        {needsEndpoint && (
          <Input
            label="Base URL"
            placeholder="https://your-endpoint/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            required
            module="api-keys"
          />
        )}

        {isChat && (
          <Input
            label={needsEndpoint ? 'Model' : 'Model (optional)'}
            placeholder={
              needsEndpoint
                ? 'E.g. llama-3.1-8b-instruct'
                : (providerMeta?.modelPlaceholder ?? 'Leave blank for provider default')
            }
            value={model}
            onChange={(e) => setModel(e.target.value)}
            required={needsEndpoint}
            className="sm:col-span-2"
            module="api-keys"
          />
        )}

        <Input
          label="API Key"
          type="password"
          placeholder="sk-..."
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          required
          className="sm:col-span-2"
          module="api-keys"
        />
        {error && <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {error}</p>}
        <div className="sm:col-span-2">
          <Button
            key={savedNonce}
            type="submit"
            variant="solid"
            module="api-keys"
            data-onboarding={anchor}
            loading={saving}
            className={cn(
              savedNonce > 0 &&
              'animate-pop-flash shadow-glow-mod-api-keys motion-reduce:animate-none',
            )}
          >
            Add Key
          </Button>
        </div>
      </form>

      {loading ? (
        <SkeletonList module="api-keys" rows={2} />
      ) : keys.length === 0 ? (
        <p className="text-sm text-muted">&gt; No saved keys.</p>
      ) : (
        <ul className="stagger-children grid gap-3 sm:grid-cols-2">
          {keys.map((key) => (
            <li
              key={key.id}
              className="rounded-lg border border-border border-l-2 border-l-module-api-keys bg-surface p-4 transition-all hover:shadow-glow-mod-api-keys"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <ProviderIcon
                    provider={key.provider}
                    className={`h-5 w-5 shrink-0 ${mc.text}`}
                  />
                  <p className="truncate text-sm font-bold text-white">{key.label}</p>
                </div>
                <Badge module="api-keys" className="uppercase">
                  {key.provider}
                </Badge>
              </div>
              {key.model && (
                <p className="mb-2 truncate font-mono text-xs text-muted">
                  &gt; {key.model}
                  {key.base_url && ` @ ${endpointHost(key.base_url)}`}
                </p>
              )}
              <p className="mb-3 font-mono text-xs text-muted">
                <DecryptedText
                  text={key.key_hint}
                  animateOn="view"
                  speed={30}
                  encryptedClassName="text-module-api-keys/50"
                />
              </p>
              <div className="flex items-center justify-between">
                <Badge tone="cyan" dot>
                  Active
                </Badge>
                <Button variant="danger-outline" onClick={() => void onDelete(key.id)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function ApiKeysPage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [keys, setKeys] = useState<ApiKeyPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [brainError, setBrainError] = useState<string | undefined>();
  const [brainSaving, setBrainSaving] = useState<LLMProvider | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setKeys(await api.listApiKeys());
    } catch {
      // Key list failure surfaces as empty sections; brain errors show inline.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    void refreshUser();
  }, [load, refreshUser]);

  const onDelete = async (id: string) => {
    try {
      await api.deleteApiKey(id);
      toast.success('Key deleted.');
      await load();
      // The deleted key may have backed the default brain; re-sync the profile.
      await refreshUser();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Key could not be deleted.');
    }
  };

  const brainKeys = keys.filter((k) => BRAIN_CHAT_PROVIDERS.has(k.provider));
  const connectedKeys = keys.filter((k) => !BRAIN_CHAT_PROVIDERS.has(k.provider));
  const activeBrain = user?.default_provider ?? 'ollama';

  const hasActiveKey = (provider: LLMProvider) =>
    keys.some((k) => k.provider === provider && k.is_active);

  // Only brains the user can actually run: Ollama (free, keyless), providers
  // with an active key, and the current default (so it never vanishes even if
  // its key was deleted).
  const visibleBrains = BRAIN_OPTIONS.filter(
    (option) =>
      option.id === 'ollama' || option.id === activeBrain || hasActiveKey(option.id),
  );

  const onSelectBrain = async (provider: LLMProvider) => {
    setBrainError(undefined);
    setBrainSaving(provider);
    try {
      setUser(await api.updateProfile({ default_provider: provider }));
    } catch (err) {
      setBrainError(err instanceof ApiError ? err.message : 'Brain could not be selected.');
    } finally {
      setBrainSaving(undefined);
    }
  };

  return (
    <PageShell>
      {/* --- Brain: default LLM + AI keys --- */}
      <div className="mb-4 flex items-center gap-2">
        <BrainCircuit className={`h-5 w-5 ${mc.text}`} aria-hidden />
        <h2 className="text-lg font-bold text-white">Brain</h2>
      </div>
      <p className="mb-4 text-sm text-muted">
        This brain is used when you start a task without picking a provider.
      </p>

      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        {visibleBrains.map((option) => {
          const selectable = option.id === 'ollama' || hasActiveKey(option.id);
          const active = activeBrain === option.id;
          return (
            <button
              key={option.id}
              type="button"
              disabled={!selectable || brainSaving !== undefined}
              onClick={() => void onSelectBrain(option.id)}
              aria-pressed={active}
              className={cn(
                'rounded-lg border p-4 text-left transition-all',
                active
                  ? 'border-module-api-keys bg-surface shadow-glow-mod-api-keys'
                  : 'border-border bg-surface',
                selectable && !active && 'hover:border-border-bright hover:bg-surface-2',
                !selectable && 'cursor-not-allowed opacity-50',
              )}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <ProviderIcon
                    provider={option.id}
                    className={`h-5 w-5 shrink-0 ${active ? mc.text : 'text-muted'}`}
                  />
                  <p className="truncate text-sm font-bold text-white">{option.label}</p>
                </div>
                {active && <Badge module="api-keys">Default Brain</Badge>}
                {brainSaving === option.id && (
                  <span
                    className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-current"
                    aria-hidden
                  />
                )}
              </div>
              <p className="font-mono text-xs text-muted">
                &gt; {selectable ? option.hint : 'Add a key'}
              </p>
            </button>
          );
        })}
      </div>
      {brainError && <p className="mb-4 text-sm text-danger">&gt; ERROR: {brainError}</p>}

      <div className="mb-6">
        <ModelPreferencesCard />
      </div>

      <KeySection
        heading="NEW AI KEY"
        providers={BRAIN_KEY_PROVIDERS}
        keys={brainKeys}
        loading={loading}
        onCreated={load}
        onDelete={onDelete}
        anchor="add-key"
      />

      {/* --- Connected APIs: non-LLM integrations --- */}
      <div className="mb-4 mt-10 flex items-center gap-2 border-t border-border pt-8">
        <Cable className={`h-5 w-5 ${mc.text}`} aria-hidden />
        <h2 className="text-lg font-bold text-white">Connected APIs</h2>
      </div>
      <p className="mb-4 text-sm text-muted">
        External service keys your agents can use — Slack, Notion, GitHub, and more.
      </p>

      <KeySection
        heading="NEW SERVICE KEY"
        providers={CONNECTED_KEY_PROVIDERS}
        keys={connectedKeys}
        loading={loading}
        onCreated={load}
        onDelete={onDelete}
      />
    </PageShell>
  );
}
