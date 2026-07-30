'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { OtpInput } from '@/components/ui/OtpInput';
import { api, ApiError, ensureFreshAccessToken } from '@/lib/api';
import { EMAIL_CODE_DIGITS, EMAIL_CODE_TTL_MINUTES } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';

type LinkStatus = 'confirming' | 'success' | 'error';

/** The `?token=` path: the link does the work, we just report the outcome. */
function ConfirmByLink({ token }: { token: string }) {
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const [status, setStatus] = useState<LinkStatus>('confirming');
  const [message, setMessage] = useState<string | undefined>();
  // The token is single-use: StrictMode's dev double-effect must not burn it.
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    api
      .confirmEmailChange(token)
      .then(() => {
        setStatus('success');
        // Reached from an email link in a fresh tab, where the in-memory access
        // token is empty; the refresh cookie is the only way to tell whether
        // this browser holds a session. See verify-email/page.tsx.
        void ensureFreshAccessToken().then((token) => {
          if (token) void refreshUser();
        });
      })
      .catch((err: unknown) => {
        setStatus('error');
        setMessage(
          err instanceof ApiError ? err.message : 'Confirmation failed.',
        );
      });
  }, [token, refreshUser]);

  if (status === 'confirming') {
    return <p className="mt-6 text-sm text-muted">Confirming your new address…</p>;
  }
  if (status === 'success') return <Confirmed />;
  return (
    <>
      <p className="mt-6 text-sm text-danger">{message}</p>
      <p className="mt-4 text-sm text-muted">
        Your account still uses its previous address. Start the change again
        from Settings to get a fresh link.
      </p>
      <p className="mt-6 text-center text-sm text-muted">
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}

/** Shared success panel, reached from either the link or the code. */
function Confirmed() {
  return (
    <>
      <p className="mt-6 text-sm text-muted">
        Your email address is updated. For safety, every other session was
        signed out — you may need to sign in again elsewhere.
      </p>
      <p className="mt-6 text-center text-sm text-muted">
        <Link href="/architect" className="text-primary hover:underline">
          Continue to Maestro
        </Link>
      </p>
    </>
  );
}

/** The no-token path: type the code from the confirmation email. */
function ConfirmByCode() {
  const user = useAuthStore((s) => s.user);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [code, setCode] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = useCallback(
    async (value: string) => {
      setBusy(true);
      setError(undefined);
      try {
        await api.confirmEmailChangeCode(value);
        setDone(true);
        void refreshUser();
      } catch (err: unknown) {
        setError(
          err instanceof ApiError ? err.message : 'That code could not be checked.',
        );
        setCode('');
      } finally {
        setBusy(false);
      }
    },
    [refreshUser],
  );

  if (done) return <Confirmed />;

  if (!user) {
    return (
      <>
        <p className="mt-6 text-sm text-muted">
          Sign in to enter the code from your confirmation email, or click the
          link in that email — it works signed out.
        </p>
        <p className="mt-6 text-center text-sm text-muted">
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </>
    );
  }

  return (
    <>
      <p className="mt-6 text-sm text-muted">
        Enter the {EMAIL_CODE_DIGITS}-digit code we sent to your new address.
        Until you do, your account stays on{' '}
        <span className="font-mono text-white">{user.email}</span>.
      </p>

      <div className="mt-8">
        <OtpInput
          value={code}
          onChange={(v) => {
            setCode(v);
            if (error) setError(undefined);
          }}
          onComplete={submit}
          error={Boolean(error)}
          disabled={busy}
          label="Email change confirmation code"
        />
      </div>

      <p className="mt-4 min-h-5 text-center text-sm" aria-live="polite">
        {error ? (
          <span className="text-danger">{error}</span>
        ) : (
          <span className="text-muted">
            The code expires {EMAIL_CODE_TTL_MINUTES} minutes after it was sent.
          </span>
        )}
      </p>

      <div className="mt-6 flex justify-center">
        <Button
          variant="lime"
          disabled={busy || code.length < EMAIL_CODE_DIGITS}
          onClick={() => void submit(code)}
        >
          Confirm
        </Button>
      </div>
    </>
  );
}

function ChangeEmailInner() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';

  return (
    <Card featured glow className="stagger-children">
      <h2 className="font-sans text-xl font-bold text-white">
        <span className="text-primary">&gt;</span> Confirm New Email
      </h2>
      {token ? <ConfirmByLink token={token} /> : <ConfirmByCode />}
    </Card>
  );
}

export default function ChangeEmailPage() {
  return (
    <Suspense fallback={null}>
      <ChangeEmailInner />
    </Suspense>
  );
}
