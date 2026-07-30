'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { OtpInput } from '@/components/ui/OtpInput';
import { api, ApiError, ensureFreshAccessToken } from '@/lib/api';
import { EMAIL_CODE_DIGITS, EMAIL_CODE_TTL_MINUTES } from '@/lib/constants';
import { formatCountdown, maskEmail } from '@/lib/mask';
import { useAuthStore } from '@/stores/auth';

/** Seconds before a fresh code can be requested again. */
const RESEND_COOLDOWN_S = 60;

type LinkStatus = 'verifying' | 'success' | 'error';

/** The `?token=` path: nothing to type, just redeem and report. */
function VerifyByLink({ token }: { token: string }) {
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const [status, setStatus] = useState<LinkStatus>('verifying');
  const [message, setMessage] = useState<string | undefined>();
  // The token is single-use: StrictMode's dev double-effect must not burn it.
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    api
      .verifyEmail(token)
      .then(() => {
        setStatus('success');
        // Update the banner immediately when this browser is signed in. The
        // access token is held in memory and this page is usually opened from
        // an email link in a fresh tab, so "am I signed in?" has to go through
        // the refresh cookie rather than read a variable that is always empty
        // here. The auth store is no help either: nothing hydrates it on the
        // (auth) routes.
        void ensureFreshAccessToken().then((token) => {
          if (token) void refreshUser();
        });
      })
      .catch((err: unknown) => {
        setStatus('error');
        setMessage(err instanceof ApiError ? err.message : 'Verification failed.');
      });
  }, [token, refreshUser]);

  if (status === 'verifying') {
    return <p className="mt-6 text-sm text-muted">Verifying your email…</p>;
  }
  if (status === 'success') return <Verified />;
  return (
    <>
      <p className="mt-6 text-sm text-danger">{message}</p>
      <p className="mt-4 text-sm text-muted">
        Sign in to request a fresh link, or enter the code from the email
        instead.
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
function Verified() {
  return (
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
  );
}

/** The no-token path: type the six digits from the email. */
function VerifyByCode() {
  const user = useAuthStore((s) => s.user);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [code, setCode] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  // Only known once we have minted a code in this session; a page reload
  // loses it, and guessing an expiry would be worse than omitting one.
  const [expiresIn, setExpiresIn] = useState<number | undefined>();

  useEffect(() => {
    if (cooldown <= 0 && expiresIn === undefined) return;
    const id = window.setInterval(() => {
      setCooldown((s) => Math.max(0, s - 1));
      setExpiresIn((s) => (s === undefined ? s : Math.max(0, s - 1)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [cooldown, expiresIn]);

  const submit = useCallback(
    async (value: string) => {
      setBusy(true);
      setError(undefined);
      try {
        await api.verifyEmailCode(value);
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

  const resend = useCallback(async () => {
    setBusy(true);
    setError(undefined);
    try {
      await api.resendVerification();
      setCode('');
      setCooldown(RESEND_COOLDOWN_S);
      setExpiresIn(EMAIL_CODE_TTL_MINUTES * 60);
    } catch (err: unknown) {
      setError(
        err instanceof ApiError ? err.message : 'Could not send a new code.',
      );
    } finally {
      setBusy(false);
    }
  }, []);

  if (done) return <Verified />;

  if (!user) {
    return (
      <>
        <p className="mt-6 text-sm text-muted">
          Sign in to enter the code from your verification email, or just click
          the link in that email — it works signed out.
        </p>
        <p className="mt-6 text-center text-sm text-muted">
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </>
    );
  }

  if (user.email_verified) return <Verified />;

  return (
    <>
      <p className="mt-6 text-sm text-muted">
        Enter the {EMAIL_CODE_DIGITS}-digit code we sent to{' '}
        <span className="font-mono text-white">{maskEmail(user.email)}</span>.
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
        />
      </div>

      <p className="mt-4 min-h-5 text-center text-sm" aria-live="polite">
        {error ? (
          <span className="text-danger">{error}</span>
        ) : expiresIn !== undefined ? (
          <span className="text-muted">
            {expiresIn > 0
              ? `Code expires in ${formatCountdown(expiresIn)}`
              : 'That code has expired — send yourself a new one.'}
          </span>
        ) : (
          <span className="text-muted">
            The code expires {EMAIL_CODE_TTL_MINUTES} minutes after it was sent.
          </span>
        )}
      </p>

      <div className="mt-6 flex flex-col items-center gap-3">
        <Button
          variant="lime"
          disabled={busy || code.length < EMAIL_CODE_DIGITS}
          onClick={() => void submit(code)}
        >
          Verify
        </Button>
        <button
          type="button"
          onClick={() => void resend()}
          disabled={busy || cooldown > 0}
          className="text-sm text-muted transition-colors hover:text-primary disabled:cursor-not-allowed disabled:hover:text-muted"
        >
          {cooldown > 0
            ? `Resend code in ${formatCountdown(cooldown)}`
            : 'Resend code'}
        </button>
      </div>
    </>
  );
}

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';

  return (
    <Card featured glow className="stagger-children">
      <h2 className="font-sans text-xl font-bold text-white">
        <span className="text-primary">&gt;</span> Email Verification
      </h2>
      {token ? <VerifyByLink token={token} /> : <VerifyByCode />}
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
