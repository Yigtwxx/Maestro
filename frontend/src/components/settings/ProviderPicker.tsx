'use client';

import { useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { ProviderIcon } from '@/components/ProviderIcon';
import { cn } from '@/lib/cn';
import { groupProviders, type ProviderMeta } from '@/lib/providers';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { LLMProvider } from '@/types';

const mc = MODULE_COLOR['api-keys'];

/** Under this many options the list fits on screen and a filter box is noise. */
const FILTER_THRESHOLD = 8;

interface ProviderPickerProps {
  providers: readonly ProviderMeta[];
  value: LLMProvider;
  onChange: (id: LLMProvider) => void;
  /** Accessible name for the radiogroup, e.g. "AI provider". */
  label: string;
}

/**
 * Grouped, filterable provider radiogroup.
 *
 * The catalog is far too long for a flat grid, so options are bucketed by
 * `ProviderMeta.group` and a substring filter narrows them. Selection lives in
 * the parent, which is what lets filtering never disturb it.
 */
export function ProviderPicker({ providers, value, onChange, label }: ProviderPickerProps) {
  const [query, setQuery] = useState('');
  const radios = useRef(new Map<LLMProvider, HTMLButtonElement>());

  const buckets = useMemo(() => {
    const all = groupProviders(providers);
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all
      .map((bucket) => ({
        ...bucket,
        items: bucket.items.filter(
          (p) =>
            p.label.toLowerCase().includes(needle) ||
            // Ids are snake_case; normalizing lets "google drive" match.
            p.id.replace(/_/g, ' ').includes(needle) ||
            // Matching the heading is what makes "email" surface the whole
            // messaging bucket, which is most of this filter's value.
            bucket.label.toLowerCase().includes(needle),
        ),
      }))
      .filter((bucket) => bucket.items.length > 0);
  }, [providers, query]);

  const visibleIds = useMemo(
    () => buckets.flatMap((bucket) => bucket.items.map((p) => p.id)),
    [buckets],
  );

  const selectedMeta = providers.find((p) => p.id === value);
  const selectedVisible = visibleIds.includes(value);
  // A radiogroup should be a single tab stop. When the filter hides the
  // selection the stop moves to the first visible option so the group stays
  // reachable from the keyboard.
  const tabStop = selectedVisible ? value : visibleIds[0];

  const move = (to: number | 'first' | 'last') => {
    if (visibleIds.length === 0) return;
    const current = visibleIds.indexOf(value);
    let next: number;
    if (to === 'first') next = 0;
    else if (to === 'last') next = visibleIds.length - 1;
    else if (current === -1) next = 0;
    else next = (current + to + visibleIds.length) % visibleIds.length;

    const id = visibleIds[next];
    onChange(id);
    const el = radios.current.get(id);
    el?.focus();
    el?.scrollIntoView({ block: 'nearest' });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        move(1);
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        move(-1);
        break;
      case 'Home':
        event.preventDefault();
        move('first');
        break;
      case 'End':
        event.preventDefault();
        move('last');
        break;
      default:
        break;
    }
  };

  return (
    <div>
      <p className="mb-2 text-micro text-muted">Provider</p>

      {providers.length > FILTER_THRESHOLD && (
        <div className="relative mb-3">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            type="search"
            aria-label={`Filter ${label} list`}
            placeholder="Filter providers..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
            module="api-keys"
          />
        </div>
      )}

      {!selectedVisible && selectedMeta && (
        <p className="mb-2 text-xs text-muted">
          Selected: <span className={mc.text}>{selectedMeta.label}</span>
        </p>
      )}

      {buckets.length === 0 ? (
        <p className="text-sm text-muted">
          &gt; No provider matches &quot;{query.trim()}&quot;.
        </p>
      ) : (
        <div
          role="radiogroup"
          aria-label={label}
          onKeyDown={onKeyDown}
          className="max-h-[22rem] overflow-y-auto pr-1"
        >
          {buckets.map((bucket, index) => (
            <div key={bucket.group}>
              {/* Hidden from the a11y tree on purpose: a bare text node between
                  radios is noise, and each radio already names itself. */}
              <p
                className={cn('mb-1.5 text-micro text-muted', index > 0 && 'mt-3')}
                aria-hidden
              >
                {bucket.label}
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {bucket.items.map((p) => {
                  const active = p.id === value;
                  return (
                    <button
                      key={p.id}
                      ref={(el) => {
                        if (el) radios.current.set(p.id, el);
                        else radios.current.delete(p.id);
                      }}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      tabIndex={p.id === tabStop ? 0 : -1}
                      onClick={() => onChange(p.id)}
                      className={cn(
                        'flex items-center gap-2 rounded-lg border p-2.5 text-left text-sm transition-all',
                        active
                          ? 'border-module-api-keys bg-surface-2 text-white shadow-glow-mod-api-keys'
                          : 'border-border bg-surface text-muted hover:border-border-bright hover:bg-surface-2',
                      )}
                    >
                      <ProviderIcon
                        provider={p.id}
                        className={cn('h-6 w-6 shrink-0', active ? mc.text : 'text-muted')}
                      />
                      <span className="truncate">{p.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ProviderPicker;
