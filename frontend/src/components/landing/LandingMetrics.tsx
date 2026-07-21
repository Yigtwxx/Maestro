'use client';

import { AGENT_DOMAINS, AGENT_ROLES, BRAIN_CHAT_PROVIDERS } from '@/lib/constants';
import { GradientText } from '@/components/effects/GradientText';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';

interface Metric {
  value: string;
  label: string;
}

// Honest capability figures derived from the source of truth — no invented
// usage numbers or testimonials (see the project's BILLING_LIVE honesty flag).
const METRICS: readonly Metric[] = [
  { value: String(AGENT_DOMAINS.length), label: 'Agent domains' },
  { value: String(BRAIN_CHAT_PROVIDERS.size), label: 'LLM providers (BYOK)' },
  { value: 'AES-256', label: 'Encrypted keys' },
  { value: String(AGENT_ROLES.length), label: 'Agent tiers' },
] as const;

/** Restrained capability strip closing the fold — four factual stats. */
export function LandingMetrics() {
  return (
    <section className="border-y border-border/60 bg-surface/30">
      <Stagger className="mx-auto grid max-w-5xl grid-cols-2 sm:grid-cols-4">
        {METRICS.map((metric) => (
          <StaggerItem
            key={metric.label}
            className="border-border/40 px-6 py-10 text-center [&:not(:last-child)]:border-r"
          >
            <div className="font-sans text-3xl font-bold sm:text-4xl">
              <GradientText>{metric.value}</GradientText>
            </div>
            <div className="text-micro mt-2 text-muted">{metric.label}</div>
          </StaggerItem>
        ))}
      </Stagger>
    </section>
  );
}
