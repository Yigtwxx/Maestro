import type { CSSProperties } from 'react';
import { cn } from '@/lib/cn';

const barColor = {
  lime: 'bg-primary',
  cyan: 'bg-accent',
  danger: 'bg-danger',
} as const;

interface ProgressBarProps {
  /** 0–100. Omit for indeterminate (animated) mode. */
  value?: number;
  color?: keyof typeof barColor;
  /** Raw hue override (e.g. a per-domain hex); wins over `color` when set. */
  hex?: string;
  className?: string;
}

export function ProgressBar({ value, color = 'lime', hex, className }: ProgressBarProps) {
  const indeterminate = value === undefined;
  const fillStyle: CSSProperties = {
    ...(hex ? { backgroundColor: hex } : {}),
    ...(indeterminate ? {} : { width: `${Math.min(Math.max(value, 0), 100)}%` }),
  };
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : value}
      className={cn('h-1 w-full overflow-hidden rounded-full bg-surface-2', className)}
    >
      <div
        className={cn(
          'h-full rounded-full transition-all duration-500',
          !hex && barColor[color],
          indeterminate && 'w-1/3 animate-indeterminate',
        )}
        style={fillStyle}
      />
    </div>
  );
}
