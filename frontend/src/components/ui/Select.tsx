import { forwardRef, useId } from 'react';
import type { SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
  /** Focus treatment in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, options, module, className, id, ...props },
  ref,
) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-micro text-muted">
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={selectId}
        className={cn(
          'rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-sm text-white',
          'focus:border-primary focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/60',
          'transition-[border-color,box-shadow] duration-200',
          module
            ? cn(moduleColor(module).focus, moduleColor(module).focusGlow)
            : 'focus:shadow-glow-primary',
          className,
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
});
