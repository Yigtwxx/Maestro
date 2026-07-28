import { forwardRef, useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
  /** Secondary line under the label — what the option actually does. */
  hint?: ReactNode;
  error?: string;
  /** Accent in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

/**
 * A labelled checkbox built on the native input, so keyboard, form
 * participation and screen-reader semantics come for free. `accent-color`
 * carries the module hue rather than a hand-drawn box: it is one property,
 * respects forced-colors mode, and cannot drift out of sync with :checked.
 */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    { label, hint, error, module, className, id, disabled, ...props },
    ref,
  ) {
    const autoId = useId();
    const inputId = id ?? autoId;
    const hintId = hint ? `${inputId}-hint` : undefined;
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-2.5">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            disabled={disabled}
            aria-describedby={hintId}
            aria-invalid={Boolean(error)}
            className={cn(
              'mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded-sm border border-border',
              'bg-surface-2 focus-visible:outline-none focus-visible:ring-1',
              'transition-[box-shadow,border-color] duration-200',
              module ? moduleColor(module).focus : 'focus:border-primary',
              'disabled:cursor-not-allowed disabled:opacity-40',
              error && 'border-danger',
              className,
            )}
            style={{ accentColor: moduleColor(module).hex }}
            {...props}
          />
          <div className="flex min-w-0 flex-col gap-0.5">
            <label
              htmlFor={inputId}
              className={cn(
                'cursor-pointer text-sm leading-snug text-white',
                disabled && 'cursor-not-allowed text-muted',
              )}
            >
              {label}
            </label>
            {hint && (
              <p id={hintId} className="text-xs leading-snug text-muted/80">
                {hint}
              </p>
            )}
          </div>
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
    );
  },
);
