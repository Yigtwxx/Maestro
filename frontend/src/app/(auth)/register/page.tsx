'use client';

import { useState } from 'react';
import type { CSSProperties } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { cn } from '@/lib/cn';
import { MODULE_COLOR } from '@/lib/module-colors';

// Delay before redirecting on success so the "access granted" sweep reads.
const GRANTED_SWEEP_MS = 200;

export default function RegisterPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  // Remounts the card per failure so the shake replays on repeated errors.
  const [shakeNonce, setShakeNonce] = useState(0);
  const [granted, setGranted] = useState(false);

  const fail = (message: string) => {
    setError(message);
    setShakeNonce((n) => n + 1);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (password.length < 8) {
      fail('Password must be at least 8 characters.');
      return;
    }
    setLoading(true);
    try {
      await api.register(email, password, displayName || undefined);
      await login(email, password);
      setGranted(true);
      window.setTimeout(() => router.replace('/architect'), GRANTED_SWEEP_MS);
    } catch (err) {
      fail(err instanceof ApiError ? err.message : 'Registration failed.');
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
          <span className="text-primary">&gt;</span> Create Account
        </h2>
        <p className="text-micro mt-2 text-muted">[ START FOR FREE — QWEN3 LOCAL ]</p>
        <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
          <Input
            label="Display name (optional)"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
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
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button type="submit" loading={loading || granted} className="mt-2 w-full">
            Sign up
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          Already have an account?{' '}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </Card>
    </div>
  );
}
