'use client';

import { cn } from '@/lib/cn';
import { domainColor, type DomainColor } from '@/lib/agent-colors';
import {
  ACCENT_RGB,
  CONNECTED_TOOL_PROVIDERS,
  KEYLESS_CONNECTED_TOOLS,
  SQUAD_CORE_CONNECTED_TOOL,
} from '@/lib/constants';
import { PROVIDER_MAP } from '@/lib/providers';
import { ProviderIcon } from '@/components/ProviderIcon';
import { BorderGlow } from '@/components/effects/BorderGlow';
import { CardMotif } from '@/components/architect/card-motifs/CardMotif';
import type { BuiltinAgent, LLMProvider } from '@/types';

interface AgentCatalogProps {
  agents: BuiltinAgent[];
  /** Selected domain id; null = automatic routing; undefined = no choice yet. */
  selected: string | null | undefined;
  onSelect: (domain: string | null) => void;
  /** BYOK service keys this account has stored — provider names only. */
  connectedProviders: ReadonlySet<string>;
  disabled?: boolean;
}

// Picking a squad is the whole job of this screen, so the cards carry a louder
// border glow than the library default: a thicker, wider arc with more bloom,
// and a low `sensitivity` so it is already lit while the cursor is mid-card
// rather than only within a hair of the edge.
const CARD_GLOW = { sensitivity: 0.05, intensity: 2 } as const;

// `relative` anchors the BorderGlow overlay, which positions itself `-inset-px`
// against the card and inherits its radius. `group` drives the per-domain
// CardMotif's hover animation; `isolate` gives the card its own stacking context
// so the motif's `-z-10` layer paints above the card fill but below the text,
// without escaping behind the card or clipping the BorderGlow bloom.
const cardBase =
  'group relative isolate flex h-full flex-col rounded-lg border bg-surface p-5 text-left ' +
  'transition-all disabled:cursor-not-allowed disabled:opacity-60';

/** One connected tool a squad declares, resolved against the stored keys. */
interface ApiRequirement {
  tool: string;
  providers: readonly LLMProvider[];
  /** The squad is built around this tool and no key can substitute for it. */
  required: boolean;
  /** Works with no key at all (GitHub serves anonymous reads). */
  keyless: boolean;
  /** Any single provider of the group satisfies it (community_read). */
  anyOf: boolean;
  /** At least one stored key actually covers this tool. */
  satisfiedByKey: boolean;
  /** Whether the tool can run at all — a stored key, or none needed. */
  satisfied: boolean;
}

/**
 * Connected-API requirements for a squad, in the order its backend domain
 * declares them. Built-in tools (web search, summarize, …) are deliberately
 * excluded: they need no key, so listing them would bury the signal.
 */
function apiRequirements(
  agent: BuiltinAgent,
  connected: ReadonlySet<string>,
): ApiRequirement[] {
  const coreTool = SQUAD_CORE_CONNECTED_TOOL[agent.domain];
  const out: ApiRequirement[] = [];
  for (const tool of agent.tools) {
    const providers = CONNECTED_TOOL_PROVIDERS[tool];
    if (!providers) continue;
    const keyless = KEYLESS_CONNECTED_TOOLS.includes(tool);
    const anyOf = providers.length > 1;
    const connectedCount = providers.filter((p) => connected.has(p)).length;
    // `community_read` needs any one of its three platforms; everything else
    // has a single provider, so "all" and "any" coincide there.
    const satisfiedByKey = anyOf
      ? connectedCount > 0
      : connectedCount === providers.length;
    out.push({
      tool,
      providers,
      keyless,
      anyOf,
      satisfiedByKey,
      required: tool === coreTool && !keyless,
      satisfied: keyless || satisfiedByKey,
    });
  }
  return out;
}

/**
 * One row per connected tool: a requirement badge, then a chip per provider it
 * can use. `community_read`'s three platforms stay separate chips under one
 * badge, with an "any one" hint — grouping them into a single chip would make a
 * narrow card wrap mid-name, and three badges would read as three obligations.
 */
function ApiRow({
  req,
  connected,
  dc,
}: {
  req: ApiRequirement;
  connected: ReadonlySet<string>;
  dc: DomainColor;
}) {
  const badge = req.required ? 'required' : 'optional';
  const title = req.keyless
    ? 'Used without a key; adding one only raises the rate limit'
    : req.required
      ? 'This squad is built on it — without the key it falls back to web search'
      : 'Optional accelerator for this squad';

  return (
    <span className="flex flex-wrap items-center gap-1.5" title={title}>
      <span
        className={cn(
          'text-micro rounded border px-1.5 py-1',
          req.required
            ? req.satisfied
              ? cn(dc.border, dc.bg, dc.text)
              : 'border-warning/60 bg-warning-dim text-warning'
            : 'border-border text-muted',
        )}
      >
        {badge}
      </span>
      {req.providers.map((provider) => {
        const isConnected = connected.has(provider);
        return (
          <span
            key={provider}
            className={cn(
              'inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px]',
              isConnected
                ? 'border-border bg-surface-2 text-slate-200'
                : 'border-dashed border-border/60 text-muted',
            )}
          >
            <ProviderIcon provider={provider} className="h-3.5 w-3.5" />
            {PROVIDER_MAP[provider]?.label ?? provider}
            {isConnected && (
              <span className="text-success" aria-label="connected">
                ✓
              </span>
            )}
          </span>
        );
      })}
      {req.keyless && !req.satisfiedByKey && (
        <span className="text-[11px] text-muted">no key needed</span>
      )}
      {req.anyOf && <span className="text-[11px] text-muted">any one</span>}
    </span>
  );
}

/** Domain agent picker: one card per expert plus automatic routing. */
export function AgentCatalog({
  agents,
  selected,
  onSelect,
  connectedProviders,
  disabled,
}: AgentCatalogProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <button
        type="button"
        aria-pressed={selected === null}
        disabled={disabled}
        onClick={() => onSelect(null)}
        className={cn(
          cardBase,
          selected === null
            ? 'border-accent shadow-glow-cyan'
            : 'border-border hover:border-border-bright',
        )}
      >
        {!disabled && <BorderGlow rgb={ACCENT_RGB} {...CARD_GLOW} />}
        <span className="text-base font-bold text-accent">
          Automatic (Orchestrator)
        </span>
        <span className="mt-1 text-[13px] leading-relaxed text-slate-400">
          If you are not sure which expert to pick, just write your prompt;
          the Orchestrator analyzes the task and routes it to the best expert.
        </span>
      </button>

      {agents.map((agent) => {
        const isSelected = selected === agent.domain;
        const dc = domainColor(agent.domain);
        const apis = apiRequirements(agent, connectedProviders);
        const degraded = apis.some((req) => req.required && !req.satisfied);
        return (
          <button
            key={agent.id}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            onClick={() => onSelect(agent.domain)}
            className={cn(
              cardBase,
              isSelected
                ? cn(dc.borderSelected, dc.glow)
                : cn('border-border', dc.borderHover, dc.glowHover),
            )}
          >
            {!disabled && <BorderGlow rgb={dc.rgb} {...CARD_GLOW} />}
            <CardMotif domain={agent.domain} accentHex={dc.accentHex} />
            <span className="flex items-baseline justify-between gap-2">
              <span className="text-base font-bold text-white">{agent.name}</span>
              <span
                className={cn(
                  'text-micro inline-flex shrink-0 items-center gap-1.5',
                  dc.text,
                )}
              >
                <span className={cn('h-1.5 w-1.5 rounded-full', dc.dot)} aria-hidden />
                {agent.domain}
              </span>
            </span>
            <span className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
              {agent.description}
            </span>
            <span className="mt-3 flex flex-wrap gap-1.5">
              {agent.capabilities.map((capability) => (
                <span
                  key={capability}
                  className="rounded border border-border bg-surface-2 px-2 py-1 text-[11px] text-slate-300"
                >
                  {capability}
                </span>
              ))}
            </span>

            {apis.length > 0 && (
              <span className="mt-3 flex flex-col gap-2 border-t border-border/60 pt-3">
                <span className="text-micro text-muted">[ APIS ]</span>
                {apis.map((req) => (
                  <ApiRow
                    key={req.tool}
                    req={req}
                    connected={connectedProviders}
                    dc={dc}
                  />
                ))}
                {degraded && (
                  <span className="text-[11px] leading-snug text-muted">
                    Without that key the squad still runs, but on web search only —
                    and its report says what it could not reach.
                  </span>
                )}
              </span>
            )}

            {agent.team.length > 0 && (
              <span className="mt-auto flex flex-wrap gap-x-1.5 pt-3 text-[11px] text-muted">
                <span className="text-micro shrink-0 pt-px">[ TEAM ]</span>
                {agent.team.map((member) => member.name).join(' · ')}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
