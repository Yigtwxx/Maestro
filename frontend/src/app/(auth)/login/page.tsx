'use client';

import { useState } from 'react';
import type { CSSProperties } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { cn } from '@/lib/cn';
import { MODULE_COLOR } from '@/lib/module-colors';

// Delay before redirecting on success so the "access granted" sweep reads.
const GRANTED_SWEEP_MS = 200;

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const completeMfa = useAuthStore((s) => s.completeMfa);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  // Remounts the card per failure so the shake replays on repeated errors.
  const [shakeNonce, setShakeNonce] = useState(0);
  const [granted, setGranted] = useState(false);
  // Second login step: set once the account requires a TOTP/recovery code.
  const [mfaToken, setMfaToken] = useState<string | undefined>();
  const [code, setCode] = useState('');

  const succeed = () => {
    setGranted(true);
    window.setTimeout(() => router.replace('/architect'), GRANTED_SWEEP_MS);
  };

  const fail = (err: unknown, fallback: string) => {
    setError(err instanceof ApiError ? err.message : fallback);
    setShakeNonce((n) => n + 1);
    setLoading(false);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setLoading(true);
    try {
      const challenge = await login(email, password);
      if (challenge) {
        // 2FA is on: reveal the code step instead of completing the login.
        setMfaToken(challenge.mfa_token);
        setLoading(false);
        return;
      }
      succeed();
    } catch (err) {
      fail(err, 'Login failed.');
    }
  };

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mfaToken) return;
    setError(undefined);
    setLoading(true);
    try {
      await completeMfa(mfaToken, code.trim(), email);
      succeed();
    } catch (err) {
      fail(err, 'Verification failed.');
    }
  };

  return (
    <div
      key={shakeNonce}
      className={cn(shakeNonce > 0 && !granted && 'animate-shake motion-reduce:animate-none')}
    >
      {granted && (
        <span
          aria-hidden
          className="page-scanline"
          style={{ ['--pt-rgb' as string]: MODULE_COLOR.brand.rgb } as CSSProperties}
        />
      )}
      <Card featured glow className={cn('stagger-children', error && 'shadow-glow-danger')}>
        {mfaToken ? (
          <>
            <h2 className="font-sans text-xl font-bold text-white">
              <span className="text-primary">&gt;</span> Two-Factor
            </h2>
            <p className="text-micro mt-2 text-muted">[ ENTER YOUR CODE ]</p>
            <form onSubmit={onVerify} className="mt-6 flex flex-col gap-4">
              <Input
                label="Authentication or recovery code"
                inputMode="text"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
              />
              {error && <p className="text-sm text-danger">{error}</p>}
              <Button type="submit" loading={loading || granted} className="mt-2 w-full">
                Verify
              </Button>
            </form>
            <p className="mt-6 text-center text-sm text-muted">
              Enter the 6-digit code from your authenticator app, or one of your
              recovery codes.
            </p>
          </>
        ) : (
          <>
            <h2 className="font-sans text-xl font-bold text-white">
              <span className="text-primary">&gt;</span> Sign In
            </h2>
            <p className="text-micro mt-2 text-muted">[ AUTHENTICATION REQUIRED ]</p>
            <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
              <Input
                label="Email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Input
                label="Password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <div className="-mt-2 text-right">
                <Link
                  href="/forgot-password"
                  className="text-xs text-muted hover:text-primary"
                >
                  Forgot password?
                </Link>
              </div>
              {error && <p className="text-sm text-danger">{error}</p>}
              <Button type="submit" loading={loading || granted} className="mt-2 w-full">
                Sign in
              </Button>
            </form>
            <p className="mt-6 text-center text-sm text-muted">
              Don&apos;t have an account?{' '}
              <Link href="/register" className="text-primary hover:underline">
                Sign up
              </Link>
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
