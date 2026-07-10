import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';
import { BorderGlow } from '@/components/effects/BorderGlow';

type CardAccent = 'lime' | 'cyan' | 'danger' | 'none';

const accentHover: Record<CardAccent, string> = {
  lime: 'transition-all hover:border-primary/50 hover:shadow-glow-primary',
  cyan: 'transition-all hover:border-accent/50 hover:shadow-glow-cyan',
  danger: 'transition-all hover:border-danger/50 hover:shadow-glow-danger',
  none: '',
};

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  accent?: CardAccent;
  /** Per-domain hover tint (border + glow); overrides `accent`/`module` when set. */
  domain?: string;
  /** Per-module hover tint (border + glow); overrides `accent` when set. */
  module?: ModuleKey;
  /** Animated neon gradient border + hover shimmer (one per page max). */
  featured?: boolean;
  /** Cursor-proximity border glow (module/domain tinted). */
  glow?: boolean;
}

export function Card({
  accent = 'none',
  domain,
  module,
  featured,
  glow,
  className,
  style,
  children,
  ...props
}: CardProps) {
  const dc = domain ? domainColor(domain) : undefined;
  const mc = module ? moduleColor(module) : undefined;
  const hover = dc
    ? cn('transition-all', dc.borderHover, dc.glowHover)
    : mc
      ? cn('transition-all', mc.borderHover, mc.glowHover)
      : accentHover[accent];
  // `.gradient-border` supplies its own border + background; skip the static ones.
  const base = featured
    ? 'rounded-lg p-6 gradient-border shimmer-hover'
    : 'rounded-lg border border-border bg-surface p-6';
  const featuredStyle: CSSProperties | undefined = featured
    ? { ['--gb-rgb' as string]: (mc ?? moduleColor(undefined)).rgb, ...style }
    : style;
  const glowRgb = dc?.rgb ?? (mc ?? moduleColor(undefined)).rgb;
  return (
    <div
      className={cn(base, hover, glow && 'relative', className)}
      style={featuredStyle}
      {...props}
    >
      {glow && <BorderGlow rgb={glowRgb} />}
      {children}
    </div>
  );
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  icon?: ReactNode;
  /** Tint the icon in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

export function CardHeader({ icon, module, className, children, ...props }: CardHeaderProps) {
  return (
    <div className={cn('mb-3 flex items-center gap-2.5', className)} {...props}>
      {icon && (
        <span className={module ? moduleColor(module).text : 'text-primary'} aria-hidden>
          {icon}
        </span>
      )}
      {children}
    </div>
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn('text-lg font-bold text-white', className)} {...props} />
  );
}

export function CardDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('mt-1 text-sm text-muted', className)} {...props} />;
}
