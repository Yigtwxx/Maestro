'use client';

import { Star } from 'lucide-react';
import { cn } from '@/lib/cn';

const STAR_COUNT = 5;

interface RatingStarsProps {
  /** Average (possibly fractional) rating to display. */
  value: number;
  className?: string;
}

/** Read-only star row; fractional averages fill stars partially. */
export function RatingStars({ value, className }: RatingStarsProps) {
  return (
    <span
      className={cn('inline-flex items-center gap-0.5', className)}
      aria-label={`${value.toFixed(1)} out of ${STAR_COUNT} stars`}
    >
      {Array.from({ length: STAR_COUNT }, (_, i) => {
        const fill = Math.max(0, Math.min(1, value - i));
        return (
          <span key={i} className="relative inline-flex" aria-hidden>
            <Star className="h-3.5 w-3.5 text-muted/40" />
            <span
              className="absolute inset-0 overflow-hidden"
              style={{ width: `${fill * 100}%` }}
            >
              <Star className="h-3.5 w-3.5 fill-module-marketplace text-module-marketplace" />
            </span>
          </span>
        );
      })}
    </span>
  );
}

interface RatingPickerProps {
  /** Current selection; 0 means nothing picked yet. */
  value: number;
  onChange: (value: number) => void;
  className?: string;
}

/** Interactive 1–5 star picker (radio semantics, keyboard reachable). */
export function RatingPicker({ value, onChange, className }: RatingPickerProps) {
  return (
    <div
      className={cn('flex items-center gap-1', className)}
      role="radiogroup"
      aria-label="Rating"
    >
      {Array.from({ length: STAR_COUNT }, (_, i) => {
        const star = i + 1;
        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={value === star}
            aria-label={`${star} star${star > 1 ? 's' : ''}`}
            onClick={() => onChange(star)}
            className="rounded p-0.5 transition-transform hover:scale-110 focus-visible:outline focus-visible:outline-1 focus-visible:outline-module-marketplace"
          >
            <Star
              className={cn(
                'h-5 w-5',
                star <= value
                  ? 'fill-module-marketplace text-module-marketplace'
                  : 'text-muted/40',
              )}
            />
          </button>
        );
      })}
    </div>
  );
}
