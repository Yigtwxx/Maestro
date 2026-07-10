import { cn } from '@/lib/cn';
import type { CardBrand } from '@/types';

interface BrandMarkProps {
  className?: string;
}

/** Visa: the wordmark, reduced to a monochrome glyph that inherits currentColor. */
export function VisaMark({ className }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 48 16"
      role="img"
      aria-label="Visa"
      className={cn('h-4 w-auto', className)}
      fill="currentColor"
    >
      <text
        x="0"
        y="13"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fontSize="15"
        fontWeight="700"
        fontStyle="italic"
        letterSpacing="0.5"
      >
        VISA
      </text>
    </svg>
  );
}

/** Mastercard: the interlocking circles. */
export function MastercardMark({ className }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 36 22"
      role="img"
      aria-label="Mastercard"
      className={cn('h-4 w-auto', className)}
    >
      <circle cx="13" cy="11" r="10" fill="currentColor" opacity="0.85" />
      <circle cx="23" cy="11" r="10" fill="currentColor" opacity="0.45" />
    </svg>
  );
}

interface CardBrandLogoProps {
  brand: CardBrand | undefined;
  className?: string;
}

/** The detected brand, or both marks dimmed while the number is still ambiguous. */
export function CardBrandLogo({ brand, className }: CardBrandLogoProps) {
  if (brand === 'visa') return <VisaMark className={className} />;
  if (brand === 'mastercard') return <MastercardMark className={className} />;
  return (
    <span className="flex items-center gap-2 text-muted/40" aria-hidden>
      <VisaMark />
      <MastercardMark />
    </span>
  );
}
