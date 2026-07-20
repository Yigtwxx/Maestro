'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Card } from '@/components/ui/Card';
import { api, ApiError, tokenStore } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

type Status = 'verifying' | 'success' | 'error';

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const [status, setStatus] = useState<Status>('verifying');
  const [message, setMessage] = useState<string | undefined>();
  // The token is single-use: StrictMode's dev double-effect must not burn it.
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setStatus('error');
      setMessage('This verification link is missing its token.');
      return;
    }
    api
      .verifyEmail(token)
      .then(() => {
        setStatus('success');
        // Update the banner immediately when this browser is signed in.
        if (tokenStore.getAccess()) void refreshUser();
      })
      .catch((err: unknown) => {
        setStatus('error');
        setMessage(
          err instanceof ApiError ? err.message : 'Verification failed.',
        );
      });
  }, [token, refreshUser]);

  return (
    <Card featured glow className="stagger-children">
      <h2 className="font-sans text-xl font-bold text-white">
        <span className="text-primary">&gt;</span> Email Verification
      </h2>
      {status === 'verifying' && (
        <p className="mt-6 text-sm text-muted">Verifying your email…</p>
      )}
      {status === 'success' && (
        <>
          <p className="mt-6 text-sm text-muted">
            Your email address is verified. You&apos;re all set.
          </p>
          <p className="mt-6 text-center text-sm text-muted">
            <Link href="/architect" className="text-primary hover:underline">
              Continue to Maestro
            </Link>
          </p>
        </>
      )}
      {status === 'error' && (
        <>
          <p className="mt-6 text-sm text-danger">{message}</p>
          <p className="mt-4 text-sm text-muted">
            Sign in and use the &quot;Resend email&quot; button in the banner to
            get a fresh link.
          </p>
          <p className="mt-6 text-center text-sm text-muted">
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </>
      )}
    </Card>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
