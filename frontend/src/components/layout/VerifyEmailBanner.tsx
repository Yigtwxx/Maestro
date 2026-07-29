'use client';

import { useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { EMAIL_VERIFICATION_LIVE } from '@/lib/legal';
import { useAuthStore } from '@/stores/auth';
import { toast } from '@/stores/toast';

/**
 * Slim reminder shown while the account's email is unverified.
 *
 * Silent whenever the gate is not enforced: with `EMAIL_VERIFICATION_LIVE`
 * false nothing is actually locked, and the default `console` sender delivers
 * no mail, so the banner would be pressing users toward something that is
 * neither required nor achievable. `/verify-email` stays reachable for anyone
 * who wants it.
 */
export function VerifyEmailBanner() {
  const emailVerified = useAuthStore((s) => s.user?.email_verified);
  const [sending, setSending] = useState(false);

  // Hooks above this line: the early returns below must not gate any of them.
  if (!EMAIL_VERIFICATION_LIVE) return null;
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
