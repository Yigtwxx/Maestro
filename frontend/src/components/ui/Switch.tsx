'use client';

import { useId } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  /** Secondary line under the label — the consequence of turning it on. */
  hint?: ReactNode;
  disabled?: boolean;
  /** Accent in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

/**
 * An on/off toggle for a setting that applies immediately in the surrounding
 * form state. `role="switch"` + `aria-checked` is the correct semantic here
 * (as opposed to a checkbox): the control has two states and no third,
 * indeterminate one, and it is not submitted as form data.
 */
export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
  module,
}: SwitchProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const accent = moduleColor(module);
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-0.5">
        <label
          htmlFor={id}
          className={cn(
            'text-sm leading-snug text-white',
            disabled && 'text-muted',
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
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={hintId}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full',
          'border transition-colors duration-200 focus-visible:outline-none',
          'focus-visible:ring-1',
          accent.ring,
          checked ? 'border-transparent' : 'border-border bg-surface-2',
          disabled && 'cursor-not-allowed opacity-40',
        )}
        style={checked ? { backgroundColor: accent.hex } : undefined}
      >
        <span
          className={cn(
            'inline-block h-3.5 w-3.5 rounded-full transition-transform duration-200',
            checked ? 'translate-x-[18px] bg-black' : 'translate-x-[3px] bg-muted',
          )}
        />
      </button>
    </div>
  );
}
