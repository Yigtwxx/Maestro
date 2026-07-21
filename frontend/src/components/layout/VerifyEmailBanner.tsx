'use client';

import { useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { toast } from '@/stores/toast';

/**
 * Slim reminder shown while the account's email is unverified. Keys purely
 * off the `email_verified` flag, so it renders (harmlessly) even when the
 * backend gate is disabled.
 */
export function VerifyEmailBanner() {
  const emailVerified = useAuthStore((s) => s.user?.email_verified);
  const [sending, setSending] = useState(false);

  // Hide when verified or while the profile has not loaded yet (undefined).
  if (emailVerified !== false) return null;

  const resend = async () => {
    setSending(true);
    try {
      await api.resendVerification();
      toast.success('Verification email sent. Check your inbox.');
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : 'Could not send the email.',
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex items-center justify-center gap-3 border-b border-primary/30 bg-primary/10 px-4 py-1.5 text-xs text-primary">
      <span>Verify your email address to unlock task runs and API keys.</span>
      <button
        type="button"
        onClick={resend}
        disabled={sending}
        className="font-semibold underline underline-offset-2 hover:text-white disabled:opacity-50"
      >
        {sending ? 'Sending…' : 'Resend email'}
      </button>
    </div>
  );
}
