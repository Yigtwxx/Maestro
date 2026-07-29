'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { api, ApiError } from '@/lib/api';

interface ChangeEmailDialogProps {
  open: boolean;
  onClose: () => void;
  /** Shown so the user can see what they are moving away from. */
  currentEmail: string;
}

/**
 * Requests a move to a new address.
 *
 * Deliberately does not change anything on its own: the account keeps its
 * current address until the new inbox proves it is reachable. The current
 * password is required because an attacker holding a stolen session must not
 * be able to silently redirect account recovery.
 */
export function ChangeEmailDialog({
  open,
  onClose,
  currentEmail,
}: ChangeEmailDialogProps) {
  const [newEmail, setNewEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const close = () => {
    setNewEmail('');
    setPassword('');
    setError(undefined);
    setSent(false);
    onClose();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api.requestEmailChange(newEmail, password);
      // The response is identical whether or not the target is already
      // registered, so there is nothing here to branch on.
      setSent(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not start the change.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={close} label="Change email address">
      <h3 className="font-sans text-lg font-bold text-white">
        <span className="text-primary">&gt;</span> Change email
      </h3>

      {sent ? (
        <>
          <p className="mt-4 text-sm text-muted">
            Check <span className="font-mono text-white">{newEmail}</span> for a
            confirmation link and code. Your account stays on{' '}
            <span className="font-mono text-white">{currentEmail}</span> until
            you use one of them.
          </p>
          <p className="mt-3 text-xs text-muted">
            We also let the current address know, in case this wasn&apos;t you.
          </p>
          <div className="mt-6 flex justify-end">
            <Button variant="lime" onClick={close}>
              Done
            </Button>
          </div>
        </>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4">
          <p className="text-sm text-muted">
            You&apos;re currently signed in as{' '}
            <span className="font-mono text-white">{currentEmail}</span>.
          </p>
          <Input
            label="New email"
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
            autoComplete="email"
            module="profile"
          />
          <Input
            label="Current password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            module="profile"
          />
          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" variant="lime" loading={busy} disabled={busy}>
              Send confirmation
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
