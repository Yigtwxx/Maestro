'use client';

import { useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { api, ApiError } from '@/lib/api';
import { ACCOUNT_DELETION_GRACE_DAYS } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';

/** Data export (GDPR Art.20) and the reversible account-deletion request. */
export function DangerZoneCard() {
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const onExport = async () => {
    setError(undefined);
    setExporting(true);
    try {
      await api.exportAccountData();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Your data could not be exported.');
    } finally {
      setExporting(false);
    }
  };

  const onRequestDeletion = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setDeleting(true);
    try {
      await api.requestAccountDeletion(deletePassword);
      // The account is now locked. Refreshing swaps the app for the locked screen.
      await refreshUser();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? 'Incorrect password.'
          : err instanceof ApiError
            ? err.message
            : 'Deletion could not be requested.',
      );
      setDeleting(false);
    }
  };

  return (
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
          onClick={onExport}
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
          {error && (
            <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {error}</p>
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
                setError(undefined);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
