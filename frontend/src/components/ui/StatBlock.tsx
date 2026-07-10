import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface StatBlockProps extends HTMLAttributes<HTMLDivElement> {
  label: string;
  value: ReactNode;
  /** Small suffix or delta rendered next to the value (e.g. "+12.4%", "/ run"). */
  detail?: ReactNode;
  size?: 'sm' | 'lg';
  tone?: 'default' | 'lime' | 'cyan' | 'danger';
  /** Value tinted in a module's neon hue; wins over `tone` when set. */
  module?: ModuleKey;
}

const valueTone: Record<NonNullable<StatBlockProps['tone']>, string> = {
  default: 'text-white',
  lime: 'text-primary',
  cyan: 'text-accent',
  danger: 'text-danger',
};

export function StatBlock({
  label,
  value,
  detail,
  size = 'lg',
  tone = 'default',
  module,
  className,
  ...props
}: StatBlockProps) {
  return (
    <div className={cn('flex flex-col gap-1', className)} {...props}>
      <span className="text-micro text-muted">{label}</span>
      <span
        className={cn(
          'font-mono font-bold leading-none',
          size === 'lg' ? 'text-2xl' : 'text-sm',
          module ? moduleColor(module).text : valueTone[tone],
        )}
      >
        {value}
        {detail && <span className="ml-1.5 text-xs font-medium text-muted">{detail}</span>}
      </span>
    </div>
  );
}
