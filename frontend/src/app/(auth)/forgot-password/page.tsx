'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { api, ApiError } from '@/lib/api';
import type { CaptchaChallenge } from '@/types';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  // Same anti-automation pair as the register form: this endpoint mails an
  // address the caller chose, so it carries the identical abuse surface.
  const [challenge, setChallenge] = useState<CaptchaChallenge | undefined>();
  const [websiteUrl, setWebsiteUrl] = useState('');

  useEffect(() => {
    let active = true;
    api
      .challenge()
      .then((next) => {
        if (active) setChallenge(next);
      })
      .catch(() => {
        // A failed fetch must not brick the form; the submit is rejected
        // server-side and shows the same neutral confirmation either way.
      });
    return () => {
      active = false;
    };
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setLoading(true);
    try {
      await api.forgotPassword(email, {
        website_url: websiteUrl,
        challenge: challenge?.nonce,
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card featured glow className="stagger-children">
      <h2 className="font-sans text-xl font-bold text-white">
        <span className="text-primary">&gt;</span> Reset Password
      </h2>
      <p className="text-micro mt-2 text-muted">[ WE&apos;LL EMAIL YOU A LINK ]</p>
      {sent ? (
        <p className="mt-6 text-sm text-muted">
          If an account exists for that address, a reset link is on its way.
          Check your inbox.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
          {/* Honeypot -- see the register form for why it is named this way. */}
          <input
            type="text"
            name="website_url"
            value={websiteUrl}
            onChange={(e) => setWebsiteUrl(e.target.value)}
            autoComplete="off"
            tabIndex={-1}
            aria-hidden="true"
            className="hidden"
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button type="submit" loading={loading} className="mt-2 w-full">
            Send reset link
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-muted">
        Remembered it?{' '}
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
