import { Gauge } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { SubscriptionPublic } from '@/types';

const mc = MODULE_COLOR.settings;

// Above these fractions of the allowance the bar changes hue.
const WARN_AT = 0.75;
const CRITICAL_AT = 0.95;

const STATUS_LABEL: Record<SubscriptionPublic['status'], string> = {
  trialing: 'Trial',
  active: 'Active',
  past_due: 'Past due',
  canceled: 'Canceled',
  inactive: 'Inactive',
};

function barColor(fraction: number): 'lime' | 'cyan' | 'danger' {
  if (fraction >= CRITICAL_AT) return 'danger';
  if (fraction >= WARN_AT) return 'cyan';
  return 'lime';
}

function formatTokens(tokens: number): string {
  return tokens.toLocaleString('en-US');
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

interface QuotaMeterProps {
  subscription: SubscriptionPublic;
}

export function QuotaMeter({ subscription }: QuotaMeterProps) {
  const { used_tokens, quota_tokens, status, trial_end, current_period_end } = subscription;
  const fraction = quota_tokens > 0 ? used_tokens / quota_tokens : 0;
  const exhausted = used_tokens >= quota_tokens;

  const renewalLabel = status === 'trialing' ? 'Trial ends' : 'Renews';
  const renewalDate = status === 'trialing' && trial_end ? trial_end : current_period_end;

  return (
    <Card module="settings">
      <CardHeader icon={<Gauge className="h-5 w-5" />} module="settings">
        <CardTitle>Monthly token quota</CardTitle>
      </CardHeader>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className={`font-mono text-sm ${mc.text}`}>
          {formatTokens(used_tokens)} / {formatTokens(quota_tokens)}
        </p>
        <Badge module={status === 'active' || status === 'trialing' ? 'settings' : undefined}>
          {STATUS_LABEL[status]}
        </Badge>
      </div>

      <ProgressBar value={Math.min(fraction * 100, 100)} color={barColor(fraction)} />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs text-muted">
          {renewalLabel} {formatDate(renewalDate)}
          {subscription.cancel_at_period_end && ' — will not renew'}
        </p>
        {exhausted && (
          <p className="font-mono text-xs text-danger">
            &gt; Quota exhausted. Upgrade to start new tasks.
          </p>
        )}
      </div>
    </Card>
  );
}
