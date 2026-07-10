'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

/**
 * Error boundary for the marketing, auth, and root segments. It renders inside
 * the root layout, so fonts and the cookie notice survive. Uncaught render
 * errors reach here instead of blanking the page; `reset()` re-renders the
 * failed segment. (Root-layout failures are caught by global-error.tsx.)
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <div className="w-full max-w-md rounded-lg border border-danger/40 bg-surface/95 p-8 shadow-lg backdrop-blur">
        <AlertTriangle className="mx-auto mb-4 h-8 w-8 text-danger" aria-hidden />
        <p className="font-mono text-sm text-danger">&gt; RUNTIME FAULT</p>
        <h1 className="mt-2 text-lg font-bold text-white">Something went wrong.</h1>
        <p className="mt-2 break-words font-mono text-xs leading-relaxed text-muted">
          {error.message || 'An unexpected error interrupted this page.'}
        </p>
        {error.digest !== undefined && (
          <p className="mt-2 font-mono text-[10px] text-muted/60">ref: {error.digest}</p>
        )}
        <div className="mt-6 flex items-center justify-center gap-3">
          <Button variant="lime" onClick={reset}>
            Try again
          </Button>
          <Link href="/">
            <Button variant="ghost">Go home</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
