import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

export const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold',
    'uppercase tracking-wide transition-all focus:outline-none focus-visible:ring-2',
    'focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50',
    'motion-safe:active:scale-[0.98]',
  ],
  {
    variants: {
      variant: {
        lime: 'bg-primary text-black hover:bg-primary-hover hover:shadow-glow-primary',
        'lime-outline':
          'border border-primary/60 bg-primary-dim text-primary hover:border-primary hover:shadow-glow-primary',
        'cyan-outline':
          'border border-accent/60 bg-accent-dim text-accent hover:border-accent hover:shadow-glow-cyan',
        'danger-outline':
          'border border-danger/60 bg-danger-dim text-danger hover:border-danger hover:shadow-glow-danger',
        'sponsor-outline':
          'border border-sponsor/60 bg-sponsor-dim text-sponsor hover:border-sponsor hover:shadow-glow-sponsor',
        ghost: 'bg-transparent normal-case tracking-normal text-muted hover:bg-surface-2 hover:text-white',
      },
    },
    defaultVariants: {
      variant: 'lime',
    },
  },
);

type CvaVariant = NonNullable<VariantProps<typeof buttonVariants>['variant']>;

/** Legacy names still used across pages, mapped onto the new cyber-terminal variants. */
type LegacyVariant = 'primary' | 'secondary' | 'danger';

/** Module-tinted treatments — hue comes from the `module` prop (brand lime fallback). */
type ModuleVariant = 'solid' | 'outline';

const legacyMap: Record<LegacyVariant, CvaVariant> = {
  primary: 'lime',
  secondary: 'cyan-outline',
  danger: 'danger-outline',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: CvaVariant | LegacyVariant | ModuleVariant;
  /** Tint the button in a module's neon hue (use with variant "solid"/"outline"). */
  module?: ModuleKey;
  loading?: boolean;
}

const spinnerColor: Record<CvaVariant, string> = {
  lime: 'border-black/30 border-t-black',
  'lime-outline': 'border-primary/30 border-t-primary',
  'cyan-outline': 'border-accent/30 border-t-accent',
  'danger-outline': 'border-danger/30 border-t-danger',
  'sponsor-outline': 'border-sponsor/30 border-t-sponsor',
  ghost: 'border-white/30 border-t-white',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'lime', module, loading, className, children, disabled, ...props },
  ref,
) {
  // Module path: structural base classes only (variant: null skips the lime
  // default and its hover:bg-primary-hover), hue classes come from the map.
  const modulePath = module !== undefined || variant === 'solid' || variant === 'outline';
  let classes: string;
  let spinner: string;
  if (modulePath) {
    const mc = moduleColor(module);
    const outline = variant === 'outline';
    classes = cn(
      buttonVariants({ variant: null }),
      outline ? mc.btnOutline : cn(mc.btnSolid, 'shimmer-hover'),
      className,
    );
    spinner = outline ? 'border-white/20 border-t-current' : 'border-black/30 border-t-black';
  } else {
    const resolved: CvaVariant =
      variant in legacyMap ? legacyMap[variant as LegacyVariant] : (variant as CvaVariant);
    classes = cn(buttonVariants({ variant: resolved }), className);
    spinner = spinnerColor[resolved];
  }
  return (
    <button ref={ref} disabled={disabled || loading} className={classes} {...props}>
      {loading && (
        <span className={cn('h-4 w-4 animate-spin rounded-full border-2', spinner)} aria-hidden />
      )}
      {children}
    </button>
  );
});
