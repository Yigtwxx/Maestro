'use client';

import { useState } from 'react';
import { BadgeCheck, Copy, Check } from 'lucide-react';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { formatDate, useTimeZone } from '@/lib/date';
import { useAuthStore } from '@/stores/auth';

/** Read-only account metadata: when the account was created and its id. */
export function AccountCard() {
  const user = useAuthStore((s) => s.user);
  const tz = useTimeZone();
  const [copied, setCopied] = useState(false);

  if (!user) return null;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(user.id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (insecure context); silently ignore.
    }
  };

  return (
    <Card module="profile">
      <CardHeader icon={<BadgeCheck className="h-5 w-5" />} module="profile">
        <CardTitle>Account</CardTitle>
      </CardHeader>
      <dl className="grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-micro text-muted">Member since</dt>
          <dd className="mt-1 font-mono text-sm text-white">
            {user.created_at ? formatDate(user.created_at, tz) : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-micro text-muted">Account ID</dt>
          <dd className="mt-1 flex items-center gap-2">
            <code className="truncate font-mono text-sm text-white">{user.id}</code>
            <button
              type="button"
              onClick={onCopy}
              aria-label="Copy account ID"
              className="shrink-0 text-muted transition-colors hover:text-white"
            >
              {copied ? (
                <Check className="h-4 w-4 text-module-profile" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
          </dd>
        </div>
      </dl>
    </Card>
  );
}
