import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/** Standard content container for (app) panel pages. */
export function PageShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mx-auto w-full max-w-7xl px-6 pt-5 pb-8', className)}>{children}</div>
  );
}
