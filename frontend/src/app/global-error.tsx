'use client';

import { useEffect } from 'react';
import './globals.css';

/**
 * Last-resort boundary: an error thrown while rendering the root layout itself
 * escapes app/error.tsx, so this file replaces the whole document, `<html>` and
 * `<body>` included. It is deliberately self-contained -- the font CSS vars come
 * from the root layout that just failed, so it leans on globals.css defaults and
 * a raw button instead of shared components.
 */
export default function GlobalError({
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
    <html lang="en">
      <body className="bg-background text-slate-200">
        <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center font-mono">
          <div className="w-full max-w-md rounded-lg border border-danger/40 bg-surface p-8 shadow-lg">
            <p className="text-sm text-danger">&gt; SYSTEM FAULT</p>
            <h1 className="mt-2 text-lg font-bold text-white">The application crashed.</h1>
            <p className="mt-2 break-words text-xs leading-relaxed text-muted">
              A fatal error stopped the app from rendering. Reloading may recover it.
            </p>
            {error.digest !== undefined && (
              <p className="mt-2 text-[10px] text-muted/60">ref: {error.digest}</p>
            )}
            <button
              type="button"
              onClick={reset}
              className="mt-6 inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-semibold uppercase tracking-wide text-black transition-colors hover:bg-primary-hover"
            >
              Reload
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
