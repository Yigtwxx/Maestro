'use client';

import { useEffect, useState } from 'react';
import { Cpu } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import { MODEL_PREF_ROLES, MODEL_SUGGESTIONS } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';

// Sentinel for "no pin" (the role falls back to its tier default).
const DEFAULT_VALUE = '';
// Sentinel for the free-text option (never a real model id).
const CUSTOM_VALUE = '__custom__';

const isSuggestion = (value: string): boolean =>
  (MODEL_SUGGESTIONS as readonly string[]).includes(value);

/** Per-role model pins; unset roles use the brain's tier default. */
export function ModelPreferencesCard() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const [prefs, setPrefs] = useState<Record<string, string>>({});
  const [customRoles, setCustomRoles] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [savedNonce, setSavedNonce] = useState(0);

  useEffect(() => {
    if (user) {
      const saved = user.model_preferences ?? {};
      setPrefs(saved);
      // A saved model outside the suggestion list must round-trip into the
      // Custom input — falling back to Default would clear it on the next save.
      setCustomRoles(
        Object.fromEntries(
          Object.entries(saved)
            .filter(([, model]) => !isSuggestion(model))
            .map(([role]) => [role, true]),
        ),
      );
    }
  }, [user]);

  const selectValue = (role: string): string => {
    if (customRoles[role]) return CUSTOM_VALUE;
    const model = prefs[role];
    if (model === undefined) return DEFAULT_VALUE;
    return isSuggestion(model) ? model : CUSTOM_VALUE;
  };

  const onSelect = (role: string, value: string) => {
    if (value === CUSTOM_VALUE) {
      setCustomRoles((c) => ({ ...c, [role]: true }));
      return;
    }
    setCustomRoles((c) => ({ ...c, [role]: false }));
    setPrefs((p) => {
      const next = { ...p };
      if (value === DEFAULT_VALUE) delete next[role];
      else next[role] = value;
      return next;
    });
  };

  const onCustomInput = (role: string, value: string) => {
    setPrefs((p) => ({ ...p, [role]: value }));
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      const map = Object.fromEntries(
        Object.entries(prefs)
          .map(([role, model]) => [role, model.trim()])
          .filter(([, model]) => model !== ''),
      );
      const updated = await api.updateProfile({
        model_preferences: Object.keys(map).length ? map : null,
      });
      setUser(updated);
      setSavedNonce((n) => n + 1);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Model preferences could not be saved.',
      );
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <Card module="api-keys">
      <CardHeader icon={<Cpu className="h-5 w-5" />} module="api-keys">
        <CardTitle>Model Preferences</CardTitle>
      </CardHeader>
      <p className="mb-5 text-sm text-muted">
        Pin a specific model per agent role. Unset roles use your brain&apos;s tier
        default.
      </p>
      <form onSubmit={onSave} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          {MODEL_PREF_ROLES.map(({ role, label, tier }) => (
            <div key={role} className="space-y-2">
              <Select
                label={label}
                module="api-keys"
                value={selectValue(role)}
                onChange={(e) => onSelect(role, e.target.value)}
                options={[
                  { value: DEFAULT_VALUE, label: `Default (${tier})` },
                  ...MODEL_SUGGESTIONS.map((m) => ({ value: m, label: m })),
                  { value: CUSTOM_VALUE, label: 'Custom…' },
                ]}
              />
              {selectValue(role) === CUSTOM_VALUE && (
                <Input
                  aria-label={`${label} custom model`}
                  module="api-keys"
                  value={prefs[role] ?? ''}
                  onChange={(e) => onCustomInput(role, e.target.value)}
                  placeholder="claude-opus-4-8"
                />
              )}
            </div>
          ))}
        </div>

        {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
        <Button
          key={savedNonce}
          type="submit"
          variant="solid"
          module="api-keys"
          loading={saving}
          className={cn(
            savedNonce > 0 &&
              'animate-pop-flash shadow-glow-mod-api-keys motion-reduce:animate-none',
          )}
        >
          Save
        </Button>
      </form>
    </Card>
  );
}
