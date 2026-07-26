import { BRAND, MONOGRAM } from '@/components/provider-glyphs';
import { PROVIDER_MAP } from '@/lib/providers';
import type { LLMProvider } from '@/types';

/**
 * Two-letter fallback for a provider with no brand glyph.
 *
 * Derived from the provider's catalog label rather than hardcoded, because the
 * catalog is far larger than the set of marks we can legally inline — most
 * providers reach this path. `MONOGRAM` overrides it only where the derivation
 * would be meaningless or would collide with another provider.
 */
function monogram(provider: LLMProvider): string {
  const explicit = MONOGRAM[provider];
  if (explicit) return explicit;

  // Parentheticals are disambiguators, not part of the name: "xAI (Grok)" must
  // read XA, not X(.
  const label = PROVIDER_MAP[provider]?.label.replace(/\(.*?\)/g, '').trim();
  if (!label) return '?';
  const words = label.split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  const initials =
    words.length >= 2 ? words[0][0] + words[1][0] : words[0].slice(0, 2);
  return initials.toUpperCase();
}

interface ProviderIconProps {
  provider: LLMProvider;
  className?: string;
}

/** Inline, brand-colored logo for a BYOK provider. Decorative. */
export function ProviderIcon({ provider, className }: ProviderIconProps) {
  const brand = BRAND[provider];

  if (brand) {
    const gradient = brand.gradient;
    // Duplicate ids across instances are fine: every definition is identical.
    const gradientId = `provider-gradient-${provider}`;
    return (
      <svg
        viewBox="0 0 24 24"
        className={className}
        role="img"
        aria-hidden
        fillRule={brand.evenOdd ? 'evenodd' : undefined}
      >
        {gradient && (
          <defs>
            <linearGradient id={gradientId} x1="0" y1="1" x2="1" y2="0">
              {gradient.map((color, i) => (
                <stop
                  key={color}
                  offset={`${(i / (gradient.length - 1)) * 100}%`}
                  stopColor={color}
                />
              ))}
            </linearGradient>
          </defs>
        )}
        <g
          transform={brand.transform}
          fill={gradient ? `url(#${gradientId})` : brand.fill}
        >
          {brand.d.map((d, i) => (
            <path key={i} d={d} />
          ))}
        </g>
      </svg>
    );
  }

  const mono = monogram(provider);
  return (
    <svg viewBox="0 0 24 24" className={className} role="img" aria-hidden fill="none">
      <rect
        x="1"
        y="1"
        width="22"
        height="22"
        rx="6"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.45"
      />
      <text
        x="12"
        y="12.5"
        textAnchor="middle"
        dominantBaseline="central"
        // Two monospace glyphs at 9 sit comfortably inside the 22-unit rect;
        // three would overrun it.
        fontSize={mono.length > 2 ? 7 : 9}
        fontWeight={700}
        fill="currentColor"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {mono}
      </text>
    </svg>
  );
}

export default ProviderIcon;
