import { Gauge } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { formatDate, useTimeZone } from '@/lib/date';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { SubscriptionPublic } from '@/types';

const mc = MODULE_COLOR.billing;

// Above these fractions of the allowance the bar changes hue.
const WARN_AT = 0.75;
const CRITICAL_AT = 0.95;

const STATUS_LABEL: Record<SubscriptionPublic['status'], string> = {
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

interface QuotaMeterProps {
  subscription: SubscriptionPublic;
}

export function QuotaMeter({ subscription }: QuotaMeterProps) {
  const tz = useTimeZone();
  const { used_tokens, quota_tokens, status, current_period_end } = subscription;
  const fraction = quota_tokens > 0 ? used_tokens / quota_tokens : 0;
  const exhausted = used_tokens >= quota_tokens;

  return (
    <Card module="billing">
      <CardHeader icon={<Gauge className="h-5 w-5" />} module="billing">
        <CardTitle>Monthly token quota</CardTitle>
      </CardHeader>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className={`font-mono text-sm ${mc.text}`}>
          {formatTokens(used_tokens)} / {formatTokens(quota_tokens)}
        </p>
        <Badge module={status === 'active' ? 'billing' : undefined}>
          {STATUS_LABEL[status]}
        </Badge>
      </div>

      <ProgressBar value={Math.min(fraction * 100, 100)} color={barColor(fraction)} />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs text-muted">
          Renews {formatDate(current_period_end, tz)}
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
