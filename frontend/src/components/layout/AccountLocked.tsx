'use client';

import { useState } from 'react';
import { Download, LogOut, RotateCcw, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { formatPurgeDate } from '@/lib/deletion';

interface AccountLockedProps {
  /** ISO timestamp of when deletion was requested. */
  requestedAt: string;
}

/**
 * Full-screen takeover for an account pending deletion.
 *
 * Every product endpoint 403s for a locked account, so rendering the normal app
 * would be a wall of errors. This gives the user the only three things they can
 * still do: come back, take their data, or leave.
 */
export function AccountLocked({ requestedAt }: AccountLockedProps) {
  const logout = useAuthStore((state) => state.logout);
  const setUser = useAuthStore((state) => state.setUser);
  const [busy, setBusy] = useState<'restore' | 'export' | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  const onRestore = async () => {
    setError(undefined);
    setBusy('restore');
    try {
      setUser(await api.cancelAccountDeletion());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Your account could not be restored.',
      );
      setBusy(undefined);
    }
  };

  const onExport = async () => {
    setError(undefined);
    setBusy('export');
    try {
      await api.exportAccountData();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Your data could not be exported.',
      );
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-5 py-16">
      <div className="w-full max-w-lg rounded-lg border border-danger/40 bg-surface p-8">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 shrink-0 text-danger" aria-hidden />
          <h1 className="font-sans text-lg font-bold text-danger">
            Account scheduled for deletion
          </h1>
        </div>

        <p className="mt-4 font-mono text-sm leading-relaxed text-slate-200">
          Everything in this account will be permanently erased on{' '}
          <strong className="text-white">{formatPurgeDate(requestedAt)}</strong>. Until
          then it is locked: you cannot run tasks or use any part of the product.
        </p>
        <p className="mt-3 font-mono text-xs leading-relaxed text-muted">
          Restoring brings the account straight back. It does not reinstate a
          subscription that was cancelled when you requested deletion.
        </p>

        {error && (
          <p className="mt-4 font-mono text-sm text-danger">&gt; ERROR: {error}</p>
        )}

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Button
            variant="lime"
            className="gap-1.5 whitespace-nowrap"
            onClick={onRestore}
            loading={busy === 'restore'}
            disabled={busy !== undefined}
          >
            <RotateCcw className="h-4 w-4 shrink-0" aria-hidden />
            Restore account
          </Button>
          <Button
            variant="cyan-outline"
            className="gap-1.5 whitespace-nowrap"
            onClick={onExport}
            loading={busy === 'export'}
            disabled={busy !== undefined}
          >
            <Download className="h-4 w-4 shrink-0" aria-hidden />
            Export my data
          </Button>
          <Button
            variant="ghost"
            className="gap-1.5 whitespace-nowrap sm:ml-auto"
            onClick={logout}
            disabled={busy !== undefined}
          >
            <LogOut className="h-4 w-4 shrink-0" aria-hidden />
            Sign out
          </Button>
        </div>
      </div>
    </main>
  );
}
