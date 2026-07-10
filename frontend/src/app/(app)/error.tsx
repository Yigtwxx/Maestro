'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

/**
 * Error boundary for the authenticated app segment. It renders inside
 * (app)/layout.tsx, so the sidebar, top bar, and status bar stay put and only
 * the crashed view is replaced. `reset()` re-renders that view.
 */
export default function AppError({
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
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="w-full max-w-md rounded-lg border border-danger/40 bg-surface/95 p-8 shadow-lg backdrop-blur">
        <AlertTriangle className="mx-auto mb-4 h-8 w-8 text-danger" aria-hidden />
        <p className="font-mono text-sm text-danger">&gt; MODULE FAULT</p>
        <h1 className="mt-2 text-lg font-bold text-white">This view crashed.</h1>
        <p className="mt-2 break-words font-mono text-xs leading-relaxed text-muted">
          {error.message || 'An unexpected error interrupted this module.'}
        </p>
        {error.digest !== undefined && (
          <p className="mt-2 font-mono text-[10px] text-muted/60">ref: {error.digest}</p>
        )}
        <div className="mt-6 flex items-center justify-center gap-3">
          <Button variant="lime" onClick={reset}>
            Try again
          </Button>
          <Link href="/dashboard">
            <Button variant="ghost">Dashboard</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
