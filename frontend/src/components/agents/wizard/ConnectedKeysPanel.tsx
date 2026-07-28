'use client';

import Link from 'next/link';
import { KeyRound } from 'lucide-react';
import { cn } from '@/lib/cn';
import { PROVIDER_MAP } from '@/lib/providers';
import type { LLMProvider, ToolCatalogItem } from '@/types';

interface ConnectedKeysPanelProps {
  /** The tools the user has actually selected. */
  selected: ToolCatalogItem[];
}

interface ProviderRow {
  id: LLMProvider;
  label: string;
  connected: boolean;
  /** True when every tool asking for this provider works without it anyway. */
  optional: boolean;
}

/**
 * Which BYOK service keys the selected tools want, and whether the user holds
 * them. Read-only by design: adding a key is a separate, security-sensitive
 * flow, so this links to it rather than embedding a key field mid-wizard.
 *
 * A missing key is deliberately not an error — `resolve_enabled_tools`
 * withholds that one tool and the squad falls back to web search, reporting the
 * gap in its answer (CLAUDE.md §8). Blocking here would make the wizard stricter
 * than the runtime.
 */
export function ConnectedKeysPanel({ selected }: ConnectedKeysPanelProps) {
  const rows = new Map<LLMProvider, ProviderRow>();
  for (const tool of selected) {
    for (const provider of tool.providers) {
      const existing = rows.get(provider);
      rows.set(provider, {
        id: provider,
        label: PROVIDER_MAP[provider]?.label ?? provider,
        connected: tool.connected || (existing?.connected ?? false),
        // Only optional if *every* tool wanting it is keyless.
        optional: (existing?.optional ?? true) && tool.keyless,
      });
    }
  }

  if (rows.size === 0) return null;
  const list = [...rows.values()].sort((a, b) => a.label.localeCompare(b.label));
  const missing = list.filter((row) => !row.connected && !row.optional);

  return (
    <section className="rounded-lg border border-border bg-surface-2/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <KeyRound className="h-3.5 w-3.5 text-muted" aria-hidden />
        <p className="text-micro text-muted">[ SERVICE KEYS THESE TOOLS USE ]</p>
      </div>

      <ul className="grid gap-2">
        {list.map((row) => (
          <li key={row.id} className="flex items-center justify-between gap-3">
            <span className="text-sm text-white">{row.label}</span>
            <span
              className={cn(
                'rounded px-2 py-0.5 text-xs font-medium',
                row.connected
                  ? 'bg-success/10 text-success'
                  : row.optional
                    ? 'bg-surface text-muted'
                    : 'bg-warning/10 text-warning',
              )}
            >
              {row.connected
                ? 'Connected'
                : row.optional
                  ? 'Optional'
                  : 'Not connected'}
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-3 text-xs leading-relaxed text-muted/80">
        {missing.length > 0
          ? 'The agent still runs without these — it withholds the tool, falls back to web search, and says so in its answer.'
          : 'Every tool you picked has the credential it needs.'}{' '}
        <Link
          href="/settings/api-keys"
          className="text-module-agents underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-module-agents"
        >
          Manage API keys
        </Link>
      </p>
    </section>
  );
}
