'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/cn';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

interface CopyButtonProps {
  /** Written to the clipboard verbatim. */
  value: string;
  /** Accessible name and tooltip, e.g. "Copy result as Markdown". */
  label: string;
  /** Tints the confirmation tick in a module's hue. */
  module?: ModuleKey;
  className?: string;
}

/** How long the tick stays before reverting to the copy glyph. */
const CONFIRM_MS = 1500;

/**
 * Copy-to-clipboard control: the glyph turns into a tick for a moment, which is
 * the only feedback — a failed copy is silent, because the Clipboard API is
 * simply absent in insecure contexts and there is nothing the user can do.
 */
export function CopyButton({
  value,
  label,
  module,
  className,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const mc = moduleColor(module);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), CONFIRM_MS);
    } catch {
      // Clipboard may be unavailable (insecure context); silently ignore.
    }
  };

  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={label}
      title={label}
      className={cn(
        'shrink-0 rounded p-1 text-muted transition-colors hover:text-white',
        className,
      )}
    >
      {copied ? (
        <Check className={cn('h-4 w-4', mc.text)} />
      ) : (
        <Copy className="h-4 w-4" />
      )}
    </button>
  );
}
