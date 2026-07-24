'use client';

import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';

/** Password change. Requires the current password. */
export function SecurityCard() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordRepeat, setNewPasswordRepeat] = useState('');
  const [revokeOthers, setRevokeOthers] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [savedNonce, setSavedNonce] = useState(0);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (newPassword !== newPasswordRepeat) {
      setError('New passwords do not match.');
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(currentPassword, newPassword, revokeOthers);
      setCurrentPassword('');
      setNewPassword('');
      setNewPasswordRepeat('');
      setSavedNonce((n) => n + 1);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? 'Current password is incorrect.'
          : err instanceof ApiError
            ? err.message
            : 'Password could not be changed.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card module="profile">
      <CardHeader icon={<ShieldCheck className="h-5 w-5" />} module="profile">
        <CardTitle>Password</CardTitle>
      </CardHeader>
      <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-3">
        <Input
          label="Current Password"
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          module="profile"
        />
        <Input
          label="New Password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          minLength={8}
          module="profile"
        />
        <Input
          label="New Password (Repeat)"
          type="password"
          value={newPasswordRepeat}
          onChange={(e) => setNewPasswordRepeat(e.target.value)}
          required
          minLength={8}
          module="profile"
        />
        {error && <p className="text-sm text-danger sm:col-span-3">&gt; ERROR: {error}</p>}
        <label className="flex items-center gap-2 text-sm text-muted sm:col-span-3">
          <input
            type="checkbox"
            checked={revokeOthers}
            onChange={(e) => setRevokeOthers(e.target.checked)}
            className="h-4 w-4 accent-module-profile"
          />
          Sign out of all other devices
        </label>
        <div className="sm:col-span-3">
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
            Change Password
          </Button>
        </div>
      </form>
    </Card>
  );
}
