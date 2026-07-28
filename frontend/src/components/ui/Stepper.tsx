'use client';

import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

export interface StepperStep {
  id: string;
  label: string;
}

interface StepperProps {
  steps: StepperStep[];
  /** Index of the step being shown. */
  current: number;
  /**
   * Highest index the user has legitimately reached. Steps beyond it are
   * unreachable: the gate belongs here rather than in each caller, so a
   * half-filled draft cannot be skipped past by clicking the last chip.
   */
  furthest: number;
  onStep: (index: number) => void;
  /** Accent in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
}

/**
 * Horizontal progress header for a multi-step form. An ordered list of
 * buttons, so the sequence is conveyed to a screen reader by the markup and
 * the current step by `aria-current`, not by color alone.
 */
export function Stepper({
  steps,
  current,
  furthest,
  onStep,
  module,
}: StepperProps) {
  const accent = moduleColor(module);
  return (
    <nav aria-label="Agent setup progress">
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
        {steps.map((step, index) => {
          const isCurrent = index === current;
          const isDone = index < furthest;
          const reachable = index <= furthest;
          return (
            <li key={step.id} className="flex items-center gap-1">
              {index > 0 && (
                <span
                  aria-hidden
                  className={cn(
                    'h-px w-4 sm:w-6',
                    isDone || isCurrent ? accent.bgSolid : 'bg-border',
                  )}
                />
              )}
              <button
                type="button"
                onClick={() => reachable && onStep(index)}
                disabled={!reachable}
                aria-current={isCurrent ? 'step' : undefined}
                className={cn(
                  'flex items-center gap-2 rounded-md border px-2.5 py-1.5',
                  'text-xs font-medium transition-colors duration-200',
                  'focus-visible:outline-none focus-visible:ring-1',
                  accent.ring,
                  isCurrent && cn(accent.border, accent.bg, accent.text),
                  !isCurrent &&
                    reachable &&
                    'border-border text-muted hover:border-border-bright hover:text-white',
                  !reachable && 'cursor-not-allowed border-border/50 text-muted/40',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px]',
                    isCurrent || isDone
                      ? cn(accent.bgSolid, 'text-black')
                      : 'bg-surface-2 text-muted',
                  )}
                >
                  {isDone ? '✓' : index + 1}
                </span>
                <span className="hidden sm:inline">{step.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
