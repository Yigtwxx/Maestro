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
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  // Remounts the card per failure so the shake replays on repeated errors.
  const [shakeNonce, setShakeNonce] = useState(0);
  const [granted, setGranted] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setLoading(true);
    try {
      await login(email, password);
      setGranted(true);
      window.setTimeout(() => router.replace('/architect'), GRANTED_SWEEP_MS);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed.');
      setShakeNonce((n) => n + 1);
      setLoading(false);
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
      <Card featured className={cn('stagger-children', error && 'shadow-glow-danger')}>
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
      </Card>
    </div>
  );
}
