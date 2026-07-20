import Link from 'next/link';
import { AlertTriangle, ArrowRight, Check } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { buttonVariants } from '@/components/ui/Button';
import { Reveal } from '@/components/effects/Reveal';
import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import { api } from '@/lib/api';
import { formatPrice, formatQuota } from '@/lib/billing-format';
import { RECOMMENDED_PLAN, SUBSCRIPTION_PLANS } from '@/lib/constants';
import { BILLING_LIVE, BILLING_PRERELEASE_NOTICE } from '@/lib/legal';
import { cn } from '@/lib/cn';
import { buildPageMetadata } from '@/lib/seo/metadata';
import type { PlanPublicListing } from '@/types';

export const metadata = buildPageMetadata({
  title: 'Pricing',
  description:
    'Three paid plans. Subscribe to run tasks — bring your own API keys or use the local model.',
  path: '/pricing',
});

// Prices are read from the backend, the one source of truth, rather than baked
// into the build — so a price change can never ship a stale page.
export const dynamic = 'force-dynamic';

export default async function PricingPage() {
  let plans: PlanPublicListing[] = [];
  let unreachable = false;

  try {
    plans = await api.getPublicPlans();
  } catch {
    unreachable = true;
  }

  const priced = new Map(plans.map((plan) => [plan.plan, plan]));

  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ PRICING ]"
        title="Pay for tokens, not"
        titleAccent="seats"
        description="Subscribe to a plan to run tasks. Bring your own API keys, or drive everything with the local model through Ollama."
      />

      {!BILLING_LIVE && (
        <Reveal className="mt-8">
          <div className="mx-auto flex max-w-2xl gap-3 rounded-lg border border-danger/40 bg-danger/5 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
            <p className="font-mono text-xs leading-relaxed text-slate-200">
              {BILLING_PRERELEASE_NOTICE}
            </p>
          </div>
        </Reveal>
      )}

      {unreachable ? (
        <p className="mt-16 text-center font-mono text-sm text-muted">
          &gt; Live pricing is unreachable right now. Please try again shortly.
        </p>
      ) : (
        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          {SUBSCRIPTION_PLANS.map((copy, i) => {
            const pricing = priced.get(copy.plan);
            if (!pricing) return undefined;
            const recommended = copy.plan === RECOMMENDED_PLAN;

            return (
              <Reveal key={copy.plan} delay={i * 0.06}>
                <div
                  className={cn(
                    'flex h-full flex-col rounded-lg border bg-surface p-6 transition-all',
                    recommended
                      ? 'border-primary/50 shadow-glow-primary'
                      : 'border-border hover:border-border-bright',
                  )}
                >
                  {/* Fixed height so the badge on the recommended plan does not
                      push its title and price out of line with its neighbours. */}
                  <div className="mb-3 flex min-h-8 items-center justify-between gap-2">
                    <h2 className="font-sans text-base font-bold text-white">{copy.name}</h2>
                    {recommended && <Badge tone="lime">Popular</Badge>}
                  </div>

                  <div className="mb-1 flex items-baseline gap-1.5">
                    <p className="font-mono text-2xl text-primary">
                      {formatPrice(pricing.price_cents, pricing.currency)}
                    </p>
                    <span className="font-mono text-xs text-muted">/ mo</span>
                  </div>

                  <p className="mb-4 font-mono text-xs text-muted">
                    {formatQuota(pricing.quota_tokens)}
                  </p>

                  <p className="mb-5 text-xs leading-relaxed text-muted">{copy.tagline}</p>

                  <ul className="mb-6 flex-1 space-y-2">
                    {copy.features.map((feature) => (
                      <li
                        key={feature}
                        className="flex gap-2 font-mono text-xs leading-relaxed text-muted"
                      >
                        <Check className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                        {feature}
                      </li>
                    ))}
                  </ul>

                  <Link
                    href="/register"
                    className={cn(
                      buttonVariants({
                        variant: recommended ? 'lime' : 'lime-outline',
                      }),
                      'w-full justify-center',
                    )}
                  >
                    Get started
                  </Link>
                </div>
              </Reveal>
            );
          })}
        </div>
      )}

      <Reveal className="mt-14">
        <div className="rounded-lg border border-border bg-surface/50 p-6 text-center">
          <p className="font-mono text-xs leading-relaxed text-muted">
            Quota is measured in tokens across every agent in a task — the
            orchestrator, the planner, each subagent and the reviewer. Tasks that fail
            or time out still account for what they spent. When the quota runs out, new
            tasks are refused until the period rolls over.
          </p>
          <Link
            href="/how-it-works"
            className={cn(buttonVariants({ variant: 'ghost' }), 'mt-4 gap-1.5')}
          >
            See how a task runs
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </Reveal>
    </MarketingPage>
  );
}
