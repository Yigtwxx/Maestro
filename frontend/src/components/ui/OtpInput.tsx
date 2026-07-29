'use client';

import { OTPInput, type SlotProps } from 'input-otp';
import { motion } from 'motion/react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';
import { EMAIL_CODE_DIGITS } from '@/lib/constants';

/**
 * Segmented entry for the numeric codes emailed by the verification flows.
 *
 * Built on `input-otp` rather than hand-rolled inputs: paste distribution,
 * `autocomplete="one-time-code"` autofill, IME and screen-reader announcement
 * are where hand-written OTP fields break, and the library renders a single
 * real input behind the boxes so all of it comes for free.
 */

interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  /** Fires once the last digit lands, so no separate submit press is needed. */
  onComplete?: (value: string) => void;
  /** Paints the boxes red and shakes them once. */
  error?: boolean;
  /** Paints the boxes in the success hue. */
  success?: boolean;
  disabled?: boolean;
  /** Focus treatment in a module's neon hue (defaults to the lime brand). */
  module?: ModuleKey;
  /** Labels the group for assistive tech. */
  label?: string;
}

function Slot({
  char,
  isActive,
  error,
  success,
  module,
}: Pick<SlotProps, 'char' | 'isActive'> & {
  error?: boolean;
  success?: boolean;
  module?: ModuleKey;
}) {
  const hue = moduleColor(module);
  return (
    <div
      className={cn(
        'relative flex h-14 w-11 items-center justify-center rounded-md border',
        'bg-surface-2 font-mono text-xl font-bold text-white',
        'transition-[border-color,box-shadow,color] duration-200',
        'border-border',
        isActive && !error && !success && cn(hue.focus, hue.focusGlow),
        error && 'border-danger text-danger',
        success && 'border-success text-success',
      )}
    >
      {char ?? (isActive ? <Caret hex={hue.hex} /> : null)}
    </div>
  );
}

/** Blinking caret for the active empty slot — the real input is invisible. */
function Caret({ hex }: { hex: string }) {
  return (
    <span
      aria-hidden
      className="h-6 w-px motion-safe:animate-pulse"
      style={{ backgroundColor: hex }}
    />
  );
}

export function OtpInput({
  value,
  onChange,
  onComplete,
  error = false,
  success = false,
  disabled = false,
  module,
  label = 'Verification code',
}: OtpInputProps) {
  return (
    <motion.div
      // A wrong code is worth a physical beat, not just a colour change.
      animate={error ? { x: [0, -8, 8, -5, 5, 0] } : { x: 0 }}
      transition={{ duration: 0.4 }}
      className="flex justify-center"
    >
      <OTPInput
        value={value}
        onChange={onChange}
        onComplete={onComplete}
        maxLength={EMAIL_CODE_DIGITS}
        disabled={disabled}
        aria-label={label}
        // Numeric keypad on mobile, and the OS offers the code from the
        // notification when the mail arrives.
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]*"
        containerClassName={cn(
          'flex items-center gap-2',
          disabled && 'opacity-50',
        )}
        render={({ slots }) => (
          <>
            <div className="flex gap-2">
              {slots.slice(0, 3).map((slot, i) => (
                <Slot
                  key={i}
                  {...slot}
                  error={error}
                  success={success}
                  module={module}
                />
              ))}
            </div>
            <span aria-hidden className="mx-1 h-px w-3 bg-border" />
            <div className="flex gap-2">
              {slots.slice(3).map((slot, i) => (
                <Slot
                  key={i}
                  {...slot}
                  error={error}
                  success={success}
                  module={module}
                />
              ))}
            </div>
          </>
        )}
      />
    </motion.div>
  );
}
