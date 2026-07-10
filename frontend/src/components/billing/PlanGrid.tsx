import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/cn';
import { formatPrice, formatQuota } from '@/lib/billing-format';
import { PUBLIC_DISCOUNT_PCT, RECOMMENDED_PLAN, SUBSCRIPTION_PLANS } from '@/lib/constants';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { PlanPublic, SubscriptionPlan } from '@/types';

const mc = MODULE_COLOR.settings;

interface PlanGridProps {
  plans: PlanPublic[];
  currentPlan: SubscriptionPlan | undefined;
  /** True while the user is still on a trial, so no plan is really "current". */
  onTrial: boolean;
  selectedPlan: SubscriptionPlan | undefined;
  onSelect: (plan: SubscriptionPlan) => void;
}

export function PlanGrid({
  plans,
  currentPlan,
  onTrial,
  selectedPlan,
  onSelect,
}: PlanGridProps) {
  const priced = new Map(plans.map((p) => [p.plan, p]));

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {SUBSCRIPTION_PLANS.map((copy) => {
        const pricing = priced.get(copy.plan);
        if (!pricing) return undefined;

        const isCurrent = !onTrial && currentPlan === copy.plan;
        const isSelected = selectedPlan === copy.plan;
        const isRecommended = copy.plan === RECOMMENDED_PLAN;
        const discounted =
          pricing.discount_eligible &&
          pricing.discounted_price_cents < pricing.price_cents;

        return (
          <div
            key={copy.plan}
            className={cn(
              'flex flex-col rounded-lg border border-border bg-surface-2 p-4',
              isRecommended && !isSelected && 'border-border-bright',
              isSelected && `border-l-2 border-l-module-settings ${mc.glow}`,
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-bold text-white">{copy.name}</p>
              {isCurrent && <Badge module="settings">Current</Badge>}
              {!isCurrent && isRecommended && <Badge tone="gray">Popular</Badge>}
            </div>

            <div className="mb-1 flex items-baseline gap-2">
              <p className={`font-mono text-lg ${mc.text}`}>
                {formatPrice(
                  discounted ? pricing.discounted_price_cents : pricing.price_cents,
                  pricing.currency,
                )}
              </p>
              {discounted && (
                <p className="font-mono text-xs text-muted line-through">
                  {formatPrice(pricing.price_cents, pricing.currency)}
                </p>
              )}
              <span className="font-mono text-xs text-muted">/ mo</span>
            </div>

            {discounted && (
              <p className="text-micro mb-2 text-primary">
                {PUBLIC_DISCOUNT_PCT}% off your first month
              </p>
            )}

            <p className="mb-3 font-mono text-xs text-muted">
              {formatQuota(pricing.quota_tokens)}
            </p>

            <p className="mb-3 text-xs text-muted">{copy.tagline}</p>

            <ul className="mb-4 flex-1 space-y-1">
              {copy.features.map((feature) => (
                <li key={feature} className="font-mono text-xs text-muted">
                  &gt; {feature}
                </li>
              ))}
            </ul>

            <Button
              variant={isSelected ? 'solid' : 'outline'}
              module="settings"
              onClick={() => onSelect(copy.plan)}
            >
              {isSelected ? 'Selected' : isCurrent ? 'Renew' : 'Choose'}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
