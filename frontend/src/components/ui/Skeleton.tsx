import type { CSSProperties, HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  /** Sheen tint in a module's neon hue (defaults to neutral slate). */
  module?: ModuleKey;
}

/** Shimmering loading placeholder block — size it via className. */
export function Skeleton({ module, className, style, ...props }: SkeletonProps) {
  const tinted: CSSProperties | undefined = module
    ? { ['--sk-rgb' as string]: moduleColor(module).rgb, ...style }
    : style;
  return <div className={cn('skeleton', className)} style={tinted} aria-hidden {...props} />;
}

/** Stat-tile shaped placeholder (dashboard metric grid). */
export function SkeletonStatTile({ module }: { module?: ModuleKey }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <Skeleton module={module} className="h-3 w-24" />
      <Skeleton module={module} className="mt-3 h-8 w-16" />
      <Skeleton module={module} className="mt-3 h-8 w-full" />
    </div>
  );
}

/** Card-shaped placeholder with heading + body lines. */
export function SkeletonCard({ module, lines = 4 }: { module?: ModuleKey; lines?: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <Skeleton module={module} className="h-4 w-40" />
      <div className="mt-4 flex flex-col gap-3">
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} module={module} className="h-3" style={{ width: `${90 - i * 12}%` }} />
        ))}
      </div>
    </div>
  );
}

/** Row-list placeholder (tables, key lists, document lists). */
export function SkeletonList({ module, rows = 3 }: { module?: ModuleKey; rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-md border border-border bg-surface p-4">
          <Skeleton module={module} className="h-8 w-8 shrink-0" />
          <div className="flex-1">
            <Skeleton module={module} className="h-3 w-1/3" />
            <Skeleton module={module} className="mt-2 h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}
