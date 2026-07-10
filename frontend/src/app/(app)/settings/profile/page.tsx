'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { CreditCard, Download, ShieldCheck, Trash2, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import { ACCOUNT_DELETION_GRACE_DAYS } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  // Profile info form
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [profileError, setProfileError] = useState<string | undefined>();
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSavedNonce, setProfileSavedNonce] = useState(0);

  // Password form
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordRepeat, setNewPasswordRepeat] = useState('');
  const [passwordError, setPasswordError] = useState<string | undefined>();
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordSavedNonce, setPasswordSavedNonce] = useState(0);

  // Danger zone
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteError, setDeleteError] = useState<string | undefined>();
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  // Seed the form from the loaded profile.
  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name ?? '');
      setEmail(user.email);
    }
  }, [user]);

  const onSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError(undefined);
    setProfileSaving(true);
    try {
      const updated = await api.updateProfile({
        display_name: displayName,
        email,
      });
      setUser(updated);
      setProfileSavedNonce((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setProfileError('This email is already in use.');
      } else {
        setProfileError(err instanceof ApiError ? err.message : 'Profile could not be updated.');
      }
    } finally {
      setProfileSaving(false);
    }
  };

  const onChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(undefined);
    if (newPassword !== newPasswordRepeat) {
      setPasswordError('New passwords do not match.');
      return;
    }
    setPasswordSaving(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setNewPasswordRepeat('');
      setPasswordSavedNonce((n) => n + 1);
    } catch (err) {
      setPasswordError(
        err instanceof ApiError && err.status === 400
          ? 'Current password is incorrect.'
          : err instanceof ApiError
            ? err.message
            : 'Password could not be changed.',
      );
    } finally {
      setPasswordSaving(false);
    }
  };

  const onRequestDeletion = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeleteError(undefined);
    setDeleting(true);
    try {
      await api.requestAccountDeletion(deletePassword);
      // The account is now locked. Refreshing the profile makes the app layout
      // swap itself for the locked screen, where the user can still restore.
      await refreshUser();
    } catch (err) {
      setDeleteError(
        err instanceof ApiError && err.status === 400
          ? 'Incorrect password.'
          : err instanceof ApiError
            ? err.message
            : 'Deletion could not be requested.',
      );
      setDeleting(false);
    }
  };

  const onExportData = async () => {
    setDeleteError(undefined);
    setExporting(true);
    try {
      await api.exportAccountData();
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : 'Your data could not be exported.',
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-6 pt-5 pb-8">
      <div className="space-y-6">
        {/* Profile info */}
        <Card module="settings">
          <CardHeader icon={<UserRound className="h-5 w-5" />} module="settings">
            <CardTitle>Profile Details</CardTitle>
          </CardHeader>
          <form onSubmit={onSaveProfile} className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Display Name"
              placeholder="Your name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              module="settings"
            />
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              module="settings"
            />
            {profileError && (
              <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {profileError}</p>
            )}
            <div className="sm:col-span-2">
              <Button
                key={profileSavedNonce}
                type="submit"
                variant="solid"
                module="settings"
                loading={profileSaving}
                className={cn(
                  profileSavedNonce > 0 &&
                    'animate-pop-flash shadow-glow-mod-settings motion-reduce:animate-none',
                )}
              >
                Save
              </Button>
            </div>
          </form>
        </Card>

        {/* Security */}
        <Card module="settings">
          <CardHeader icon={<ShieldCheck className="h-5 w-5" />} module="settings">
            <CardTitle>Security</CardTitle>
          </CardHeader>
          <form onSubmit={onChangePassword} className="grid gap-4 sm:grid-cols-3">
            <Input
              label="Current Password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              module="settings"
            />
            <Input
              label="New Password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              module="settings"
            />
            <Input
              label="New Password (Repeat)"
              type="password"
              value={newPasswordRepeat}
              onChange={(e) => setNewPasswordRepeat(e.target.value)}
              required
              minLength={8}
              module="settings"
            />
            {passwordError && (
              <p className="text-sm text-danger sm:col-span-3">&gt; ERROR: {passwordError}</p>
            )}
            <div className="sm:col-span-3">
              <Button
                key={passwordSavedNonce}
                type="submit"
                variant="solid"
                module="settings"
                loading={passwordSaving}
                className={cn(
                  passwordSavedNonce > 0 &&
                    'animate-pop-flash shadow-glow-mod-settings motion-reduce:animate-none',
                )}
              >
                Change Password
              </Button>
            </div>
          </form>
        </Card>

        {/* Subscription */}
        <Card module="settings">
          <CardHeader icon={<CreditCard className="h-5 w-5" />} module="settings">
            <CardTitle>Subscription</CardTitle>
          </CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <p className="text-sm text-muted">Current plan</p>
              {user && <Badge module="settings">{user.subscription_tier}</Badge>}
            </div>
            <Link href="/settings/billing">
              <Button variant="outline" module="settings">
                Manage billing
              </Button>
            </Link>
          </div>
        </Card>

        {/* Danger zone */}
        <Card className="border-danger/40">
          <CardHeader icon={<Trash2 className="h-5 w-5 text-danger" />}>
            <CardTitle className="text-danger">Danger Zone</CardTitle>
          </CardHeader>
          <p className="mb-2 text-sm text-muted">
            Requesting deletion locks your account immediately. After{' '}
            {ACCOUNT_DELETION_GRACE_DAYS} days everything is erased permanently — your
            tasks, documents, agents, API keys and stored memories.
          </p>
          <p className="mb-4 text-sm text-muted">
            You can cancel any time within those {ACCOUNT_DELETION_GRACE_DAYS} days by
            signing in and choosing Restore. An active paid subscription is cancelled
            straight away and is not restored automatically.
          </p>

          <div className="mb-6">
            <Button
              variant="cyan-outline"
              className="gap-1.5"
              onClick={onExportData}
              loading={exporting}
            >
              <Download className="h-4 w-4" aria-hidden />
              Export my data
            </Button>
            <p className="mt-2 text-xs text-muted">
              Download everything we hold about you as JSON, before you go.
            </p>
          </div>

          {!confirmingDelete ? (
            <Button variant="danger-outline" onClick={() => setConfirmingDelete(true)}>
              Delete Account
            </Button>
          ) : (
            <form onSubmit={onRequestDeletion} className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Confirm by entering your password"
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                required
                className="sm:col-span-2"
              />
              {deleteError && (
                <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {deleteError}</p>
              )}
              <div className="flex gap-2 sm:col-span-2">
                <Button variant="danger-outline" type="submit" loading={deleting}>
                  Schedule deletion
                </Button>
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setConfirmingDelete(false);
                    setDeletePassword('');
                    setDeleteError(undefined);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
