'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { api, ApiError } from '@/lib/api';

function ResetPasswordInner() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Reset failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card featured glow className="stagger-children">
      <h2 className="font-sans text-xl font-bold text-white">
        <span className="text-primary">&gt;</span> Choose a New Password
      </h2>
      {done ? (
        <>
          <p className="mt-6 text-sm text-muted">
            Password updated. Every previous session has been signed out.
          </p>
          <p className="mt-6 text-center text-sm text-muted">
            <Link href="/login" className="text-primary hover:underline">
              Sign in with your new password
            </Link>
          </p>
        </>
      ) : (
        <>
          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
            <Input
              label="New password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Input
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <Button type="submit" loading={loading} className="mt-2 w-full">
              Set new password
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-muted">
            Link expired?{' '}
            <Link href="/forgot-password" className="text-primary hover:underline">
              Request a new one
            </Link>
          </p>
        </>
      )}
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordInner />
    </Suspense>
  );
}
