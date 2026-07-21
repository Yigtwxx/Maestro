'use client';

import { useState } from 'react';
import { Markdown } from '@/components/ui/Markdown';
import { cn } from '@/lib/cn';
import { LOCALE_LABELS, type LegalLocale } from '@/lib/legal';

interface LegalBodyProps {
  /** Canonical, governing content and its locale. */
  content: string;
  locale: LegalLocale;
  /** Optional additional-language versions keyed by locale. */
  translations?: Partial<Record<LegalLocale, string>>;
}

/**
 * Renders a legal document's prose, with a language switcher when translated
 * versions exist. The canonical locale is shown first and remains the governing
 * text; other locales are convenience translations the reader can toggle to.
 */
export function LegalBody({ content, locale, translations }: LegalBodyProps) {
  const versions: Partial<Record<LegalLocale, string>> = { [locale]: content, ...translations };
  const available = Object.keys(versions) as LegalLocale[];
  const [active, setActive] = useState<LegalLocale>(locale);

  return (
    <div>
      {available.length > 1 && (
        <div
          role="group"
          aria-label="Language"
          className="mb-6 inline-flex rounded-lg border border-border bg-surface-2 p-0.5 font-mono text-xs"
        >
          {available.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setActive(code)}
              aria-pressed={active === code}
              className={cn(
                'rounded-md px-3 py-1.5 transition-colors',
                active === code
                  ? 'bg-primary/15 text-primary'
                  : 'text-muted hover:text-slate-200',
              )}
            >
              {LOCALE_LABELS[code]}
            </button>
          ))}
        </div>
      )}
      <Markdown content={versions[active] ?? content} />
    </div>
  );
}
