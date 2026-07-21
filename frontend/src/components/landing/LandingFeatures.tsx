'use client';

import Link from 'next/link';
import { Activity, ArrowRight, Layers, ShieldCheck, Store } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { domainColor } from '@/lib/agent-colors';
import type { AgentDomain } from '@/lib/agent-colors';
import { GradientText } from '@/components/effects/GradientText';
import { Reveal } from '@/components/effects/Reveal';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { BorderGlow } from '@/components/effects/BorderGlow';
import { SectionEyebrow } from '@/components/landing/MarketingSection';
import { cn } from '@/lib/cn';

interface Feature {
  domain: AgentDomain;
  icon: LucideIcon;
  title: string;
  body: string;
  href: string;
}

// High-level value props only — each links out to the tab that covers it in
// full, so the home page never duplicates the marketing sections above it.
const FEATURES: readonly Feature[] = [
  {
    domain: 'software',
    icon: Layers,
    title: 'Multi-layer orchestration',
    body: 'Orchestrator routes, a main agent plans, subagents execute, a reviewer checks.',
    href: '/how-it-works',
  },
  {
    domain: 'finance',
    icon: ShieldCheck,
    title: 'BYOK, keys encrypted',
    body: 'Bring your own provider keys — sealed with AES-256-GCM, never shown again.',
    href: '/security',
  },
  {
    domain: 'marketing',
    icon: Store,
    title: 'Marketplace teams',
    body: 'Install a community agent team in one click, or publish your own.',
    href: '/templates',
  },
  {
    domain: 'research',
    icon: Activity,
    title: 'Live architect view',
    body: 'Watch every agent, message and hand-off stream in real time.',
    href: '/architect',
  },
] as const;

/** Below-the-fold feature grid: four domain-tinted cards linking to their tab. */
export function LandingFeatures() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 sm:py-24">
      <Reveal className="text-center">
        <SectionEyebrow>[ WHY MAESTRO ]</SectionEyebrow>
        <h2 className="mt-3 font-sans text-2xl font-bold tracking-tight text-white sm:text-3xl">
          Multi-layer by design,{' '}
          <GradientText>not a single prompt</GradientText>
        </h2>
      </Reveal>

      <Stagger className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((feature) => {
          const color = domainColor(feature.domain);
          const Icon = feature.icon;
          return (
            <StaggerItem key={feature.href} className="h-full">
              <Link
                href={feature.href}
                className={cn(
                  'group relative flex h-full flex-col rounded-xl border border-border bg-surface/60 p-5 shimmer-hover transition-colors',
                  color.borderHover,
                )}
              >
                <BorderGlow rgb={color.rgb} />
                <Icon
                  className={cn('h-6 w-6', color.text)}
                  style={{ filter: `drop-shadow(0 0 10px ${color.accentHex})` }}
                  aria-hidden
                />
                <h3 className="mt-4 font-sans text-base font-semibold text-white">
                  {feature.title}
                </h3>
                <p className="mt-2 flex-1 font-mono text-xs leading-relaxed text-muted">
                  {feature.body}
                </p>
                <span
                  className="mt-4 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-wide transition-colors"
                  style={{ color: color.accentHex }}
                >
                  Learn more
                  <ArrowRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </span>
              </Link>
            </StaggerItem>
          );
        })}
      </Stagger>
    </section>
  );
}
