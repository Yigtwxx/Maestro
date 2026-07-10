'use client';

import { useCallback, useEffect, useState } from 'react';
import { BrainCircuit, Cable } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import DecryptedText from '@/components/DecryptedText';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import {
  BRAIN_CHAT_PROVIDERS,
  BRAIN_KEY_PROVIDERS,
  CONNECTED_KEY_PROVIDERS,
} from '@/lib/constants';
import { MODULE_COLOR } from '@/lib/module-colors';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import type { ApiKeyPublic, LLMProvider } from '@/types';

const mc = MODULE_COLOR.settings;

// Brain options: the free local tier plus each BYOK chat provider.
const BRAIN_OPTIONS: { value: LLMProvider; name: string; hint: string }[] = [
  { value: 'ollama', name: 'Local LLM (Ollama)', hint: 'Free — works without a key' },
  { value: 'gemini', name: 'Google Gemini', hint: 'With your own key (free tier)' },
  { value: 'openai', name: 'OpenAI', hint: 'BYOK' },
  { value: 'anthropic', name: 'Anthropic (Claude)', hint: 'BYOK' },
];

/** Add-key form + masked key cards, parameterized per section. */
function KeySection({
  heading,
  providers,
  keys,
  loading,
  onCreated,
  onDelete,
}: {
  heading: string;
  providers: { value: LLMProvider; label: string }[];
  keys: ApiKeyPublic[];
  loading: boolean;
  onCreated: () => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [provider, setProvider] = useState<LLMProvider>(providers[0].value);
  const [label, setLabel] = useState('');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  // Bumped per successful save — replays the confirmation flash on the button.
  const [savedNonce, setSavedNonce] = useState(0);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      await api.createApiKey(provider, label, secret);
      setLabel('');
      setSecret('');
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
        <Select
          label="Provider"
          value={provider}
          onChange={(e) => setProvider(e.target.value as LLMProvider)}
          options={providers}
          module="settings"
        />
        <Input
          label="Label"
          placeholder="E.g. Personal OpenAI"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
          module="settings"
        />
        <Input
          label="API Key"
          type="password"
          placeholder="sk-..."
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          required
          className="sm:col-span-2"
          module="settings"
        />
        {error && <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {error}</p>}
        <div className="sm:col-span-2">
          <Button
            key={savedNonce}
            type="submit"
            variant="solid"
            module="settings"
            loading={saving}
            className={cn(
              savedNonce > 0 &&
                'animate-pop-flash shadow-glow-mod-settings motion-reduce:animate-none',
            )}
          >
            Add Key
          </Button>
        </div>
      </form>

      {loading ? (
        <SkeletonList module="settings" rows={2} />
      ) : keys.length === 0 ? (
        <p className="text-sm text-muted">&gt; No saved keys.</p>
      ) : (
        <ul className="stagger-children grid gap-3 sm:grid-cols-2">
          {keys.map((key) => (
            <li
              key={key.id}
              className="rounded-lg border border-border border-l-2 border-l-module-settings bg-surface p-4 transition-all hover:shadow-glow-mod-settings"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="truncate text-sm font-bold text-white">{key.label}</p>
                <Badge module="settings" className="uppercase">
                  {key.provider}
                </Badge>
              </div>
              <p className="mb-3 font-mono text-xs text-muted">
                <DecryptedText
                  text={`sk-████████████…${key.key_hint}`}
                  animateOn="view"
                  speed={30}
                  encryptedClassName="text-module-settings/50"
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
    <div className="mx-auto max-w-4xl px-6 pt-5 pb-8">
      {/* --- Brain: default LLM + AI keys --- */}
      <div className="mb-4 flex items-center gap-2">
        <BrainCircuit className={`h-5 w-5 ${mc.text}`} aria-hidden />
        <h2 className="text-lg font-bold text-white">Brain</h2>
      </div>
      <p className="mb-4 text-sm text-muted">
        This brain is used when you start a task without picking a provider.
      </p>

      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        {BRAIN_OPTIONS.map((option) => {
          const selectable = option.value === 'ollama' || hasActiveKey(option.value);
          const active = activeBrain === option.value;
          return (
            <button
              key={option.value}
              type="button"
              disabled={!selectable || brainSaving !== undefined}
              onClick={() => void onSelectBrain(option.value)}
              aria-pressed={active}
              className={cn(
                'rounded-lg border p-4 text-left transition-all',
                active
                  ? 'border-module-settings bg-surface shadow-glow-mod-settings'
                  : 'border-border bg-surface',
                selectable && !active && 'hover:border-border-bright hover:bg-surface-2',
                !selectable && 'cursor-not-allowed opacity-50',
              )}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="text-sm font-bold text-white">{option.name}</p>
                {active && <Badge module="settings">Default Brain</Badge>}
                {brainSaving === option.value && (
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

      <KeySection
        heading="NEW AI KEY"
        providers={BRAIN_KEY_PROVIDERS}
        keys={brainKeys}
        loading={loading}
        onCreated={load}
        onDelete={onDelete}
      />

      {/* --- Connected APIs: non-LLM integrations --- */}
      <div className="mb-4 mt-10 flex items-center gap-2 border-t border-border pt-8">
        <Cable className={`h-5 w-5 ${mc.text}`} aria-hidden />
        <h2 className="text-lg font-bold text-white">Connected APIs</h2>
      </div>
      <p className="mb-4 text-sm text-muted">
        External service keys your agents can use — X, Instagram, Google Maps,
        and more.
      </p>

      <KeySection
        heading="NEW SERVICE KEY"
        providers={CONNECTED_KEY_PROVIDERS}
        keys={connectedKeys}
        loading={loading}
        onCreated={load}
        onDelete={onDelete}
      />
    </div>
  );
}
