'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Boxes, Star } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { buttonVariants } from '@/components/ui/Button';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { SectionEyebrow } from '@/components/landing/MarketingSection';
import { useAuthStore } from '@/stores/auth';
import { domainColor } from '@/lib/agent-colors';
import { moduleColor } from '@/lib/module-colors';
import { cn } from '@/lib/cn';
import type { MarketplaceItemPreview } from '@/types';

const ALL_DOMAINS = 'all';

// `buttonVariants` has no `outline` variant — that treatment lives on the Button
// component's module path. Rebuild it here for an anchor: structural base
// classes (variant: null skips the lime default) plus the marketplace hue.
const cardCtaClass = cn(
  buttonVariants({ variant: null }),
  moduleColor('marketplace').btnOutline,
  'w-full justify-center gap-1.5',
);

interface ShowcaseGridProps {
  items: MarketplaceItemPreview[];
}

/**
 * The two showcase bands with a domain filter above them. Anonymous visitors get
 * a sign-up call to action: installing a team requires an account, since it is
 * copied into the caller's own agents.
 */
export function ShowcaseGrid({ items }: ShowcaseGridProps) {
  const [domain, setDomain] = useState<string>(ALL_DOMAINS);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const signedIn = hydrated && isAuthenticated;

  // Only offer filters that would actually match something.
  const domains = useMemo(
    () => Array.from(new Set(items.map((item) => item.domain))).sort(),
    [items],
  );

  const visible = useMemo(
    () => (domain === ALL_DOMAINS ? items : items.filter((i) => i.domain === domain)),
    [items, domain],
  );

  const featured = visible.filter((item) => item.featured);
  const community = visible.filter((item) => !item.featured);

  return (
    <div className="mt-14">
      {domains.length > 1 && (
        <div className="flex flex-wrap justify-center gap-2">
          <FilterChip
            active={domain === ALL_DOMAINS}
            onClick={() => setDomain(ALL_DOMAINS)}
          >
            All
          </FilterChip>
          {domains.map((d) => (
            <FilterChip key={d} domain={d} active={domain === d} onClick={() => setDomain(d)}>
              {d}
            </FilterChip>
          ))}
        </div>
      )}

      {items.length === 0 && (
        <p className="mt-16 text-center font-mono text-sm text-muted">
          &gt; No agent teams have been published yet.
        </p>
      )}

      {featured.length > 0 && (
        <Band
          eyebrow="[ FEATURED ]"
          title="Built by Maestro"
          subtitle="First-party teams, tuned and maintained by us."
        >
          <ShowcaseCards items={featured} signedIn={signedIn} />
        </Band>
      )}

      {community.length > 0 && (
        <Band
          eyebrow="[ COMMUNITY ]"
          title="From the community"
          subtitle="Published by Maestro users. Every one passed the mandatory security scan."
        >
          <ShowcaseCards items={community} signedIn={signedIn} />
        </Band>
      )}

      {items.length > 0 && community.length === 0 && domain === ALL_DOMAINS && (
        <p className="mt-10 text-center font-mono text-xs text-muted/70">
          &gt; No community teams yet — publish the first one.
        </p>
      )}
    </div>
  );
}

function Band({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-14">
      <SectionEyebrow className="text-module-marketplace">{eyebrow}</SectionEyebrow>
      <h2 className="mt-2 font-sans text-xl font-bold tracking-tight text-white">
        {title}
      </h2>
      <p className="mt-1 font-mono text-xs text-muted">{subtitle}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function ShowcaseCards({
  items,
  signedIn,
}: {
  items: MarketplaceItemPreview[];
  signedIn: boolean;
}) {
  return (
    <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => {
        const dc = domainColor(item.domain);
        return (
          <StaggerItem key={item.id} className="h-full">
            <Card glow domain={item.domain} className="flex h-full flex-col p-5">
              <div className="mb-3 flex items-start gap-2.5">
                <Boxes className={cn('h-5 w-5 shrink-0', dc.text)} aria-hidden />
                <h3 className="flex-1 font-sans text-base font-bold text-white">
                  {item.name}
                </h3>
                <Badge domain={item.domain} className="shrink-0 capitalize">
                  {item.domain}
                </Badge>
              </div>

              {/* The clamp needs its own element: a flex item is blockified, which
                  turns `-webkit-box` into `flow-root` and silently kills it. */}
              <div className="mb-4 flex-1">
                <p className="line-clamp-3 font-mono text-xs leading-relaxed text-muted">
                  {item.description}
                </p>
              </div>

              <div className="mb-4 flex items-center justify-between font-mono text-[11px] text-muted">
                <span className="flex items-center gap-1.5">
                  {item.featured && (
                    <Star
                      className="h-3 w-3 fill-primary text-primary"
                      aria-label="Featured"
                    />
                  )}
                  {item.author_label}
                </span>
                <span>
                  <span className="text-slate-300">{item.installs}</span> installs
                </span>
              </div>

              <Link href={signedIn ? '/marketplace' : '/register'} className={cardCtaClass}>
                {signedIn ? 'Deploy' : 'Sign up to install'}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </Card>
          </StaggerItem>
        );
      })}
    </Stagger>
  );
}

function FilterChip({
  domain,
  active,
  onClick,
  children,
}: {
  domain?: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const dc = domain ? domainColor(domain) : undefined;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded border px-2.5 py-1 text-micro capitalize transition-colors',
        active && dc && cn(dc.borderSelected, dc.bg, dc.text),
        active && !dc && 'border-primary bg-primary text-black',
        !active && 'border-border-bright bg-surface-2 text-muted hover:text-white',
      )}
    >
      {children}
    </button>
  );
}
