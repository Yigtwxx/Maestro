import { forwardRef, useId } from 'react';
import type { TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  /** Focus treatment in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, module, className, id, ...props },
  ref,
) {
  const autoId = useId();
  const textareaId = id ?? autoId;
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={textareaId} className="text-micro text-muted">
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        id={textareaId}
        aria-invalid={Boolean(error)}
        className={cn(
          'rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-sm text-white',
          'placeholder:text-muted/60 focus:border-primary focus:outline-none',
          'focus-visible:ring-1 focus-visible:ring-primary/60',
          'transition-[border-color,box-shadow] duration-200',
          module
            ? cn(moduleColor(module).focus, moduleColor(module).focusGlow)
            : 'focus:shadow-glow-primary',
          error && 'border-danger',
          className,
        )}
        style={{ caretColor: moduleColor(module).hex }}
        {...props}
      />
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
});
