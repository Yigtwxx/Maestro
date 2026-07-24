'use client';

import { useEffect, useMemo, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import { browserTimezone, listTimezones } from '@/lib/timezones';
import { useAuthStore } from '@/stores/auth';

// Sentinel for "no explicit timezone" (fall back to the browser's local zone).
const AUTO = '';

/** Real, wired preferences: display timezone and default reviewer behaviour. */
export function PreferencesCard() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const [timezone, setTimezone] = useState<string>(AUTO);
  const [reviewerDefault, setReviewerDefault] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [savedNonce, setSavedNonce] = useState(0);

  useEffect(() => {
    if (user) {
      setTimezone(user.timezone ?? AUTO);
      setReviewerDefault(user.default_reviewer_enabled ?? false);
    }
  }, [user]);

  const options = useMemo(() => {
    const zones = listTimezones().map((tz) => ({ value: tz, label: tz }));
    return [{ value: AUTO, label: `Browser default (${browserTimezone()})` }, ...zones];
  }, []);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      const updated = await api.updateProfile({
        timezone: timezone || null,
        default_reviewer_enabled: reviewerDefault,
      });
      setUser(updated);
      setSavedNonce((n) => n + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Preferences could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <Card module="profile">
      <CardHeader icon={<SlidersHorizontal className="h-5 w-5" />} module="profile">
        <CardTitle>Preferences</CardTitle>
      </CardHeader>
      <form onSubmit={onSave} className="space-y-5">
        <div className="max-w-sm">
          <Select
            label="Timezone"
            module="profile"
            options={options}
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          />
          <p className="mt-1.5 text-micro text-muted">
            Applied to dates shown in billing and the live task event log.
          </p>
        </div>

        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={reviewerDefault}
            onChange={(e) => setReviewerDefault(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-module-profile"
          />
          <span className="leading-tight">
            <span className="block text-sm text-white">
              Enable the Reviewer agent by default
            </span>
            <span className="block text-micro text-muted">
              New tasks start with quality review on unless you turn it off.
            </span>
          </span>
        </label>

        {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
        <Button
          key={savedNonce}
          type="submit"
          variant="solid"
          module="profile"
          loading={saving}
          className={cn(
            savedNonce > 0 &&
              'animate-pop-flash shadow-glow-mod-profile motion-reduce:animate-none',
          )}
        >
          Save
        </Button>
      </form>
    </Card>
  );
}
