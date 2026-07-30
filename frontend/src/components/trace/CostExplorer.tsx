'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardTitle } from '@/components/ui/Card';
import { StatBlock } from '@/components/ui/StatBlock';
import CountUp from '@/components/CountUp';
import { Sparkline } from '@/components/ui/Sparkline';
import { BarList } from '@/components/ui/BarList';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Select } from '@/components/ui/Select';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import { DOMAIN_CHART_HEXES, domainColor } from '@/lib/agent-colors';
import { formatCount, formatUsd } from '@/lib/trace';
import type { CostBreakdown, CostGroupBy } from '@/types';

const mc = MODULE_COLOR.dashboard;

const GROUP_OPTIONS: { value: CostGroupBy; label: string }[] = [
  { value: 'day', label: 'By day' },
  { value: 'model', label: 'By model' },
  { value: 'domain', label: 'By domain' },
];

const RANGE_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
];

/**
 * Account-wide, trace-derived spend. Lives on the dashboard (cyan module hue).
 * Reads from `/dashboard/costs`, which returns zero/empty when server-side
 * tracing is off — rendered as a muted empty line, not an error.
 */
export function CostExplorer() {
  const [groupBy, setGroupBy] = useState<CostGroupBy>('day');
  const [days, setDays] = useState(30);
  const [data, setData] = useState<CostBreakdown | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setData(await api.costBreakdown(days, groupBy));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Cost data could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [days, groupBy]);

  useEffect(() => {
    void load();
  }, [load]);

  const buckets = data?.buckets ?? [];
  const hasData = buckets.length > 0;

  return (
    <Card glow module="dashboard">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className={`text-micro mb-1 ${mc.text}`}>[ COST EXPLORER ]</p>
          <CardTitle className="text-base">Spend by {groupBy}</CardTitle>
        </div>
        <div className="flex items-end gap-3">
          <Select
            module="dashboard"
            aria-label="Group cost by"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as CostGroupBy)}
            options={GROUP_OPTIONS}
          />
          <Select
            module="dashboard"
            aria-label="Date range"
            value={String(days)}
            onChange={(e) => setDays(Number(e.target.value))}
            options={RANGE_OPTIONS}
          />
        </div>
      </div>

      <div className="mb-5">
        <StatBlock
          label="Total Cost"
          module="dashboard"
          value={
            data ? (
              formatUsd(data.total_cost_usd, 4)
            ) : (
              <CountUp to={0} duration={0.5} />
            )
          }
        />
      </div>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}

      {loading && !data && <SkeletonCard module="dashboard" lines={5} />}

      {!loading && !error && !hasData && (
        <p className="text-sm text-muted">
          &gt; No cost recorded. Turn on &quot;Execution tracing&quot; before starting a task — per task
          in Task Configuration, or for every task from Settings → Preferences.
        </p>
      )}

      {hasData && groupBy === 'day' && <DaySeries data={data as CostBreakdown} />}

      {hasData && groupBy !== 'day' && (
        <BarList
          rows={buckets.map((b, i) => ({
            label: b.key,
            value: b.cost_usd,
            display: `${formatUsd(b.cost_usd)} · ${formatCount(b.input_tokens + b.output_tokens)} tok`,
            hex:
              groupBy === 'domain'
                ? domainColor(b.key).chartHex
                : DOMAIN_CHART_HEXES[i % DOMAIN_CHART_HEXES.length],
          }))}
        />
      )}
    </Card>
  );
}

/** Daily cost as a bar series, oldest first, with first/last date labels. */
function DaySeries({ data }: { data: CostBreakdown }) {
  const values = data.buckets.map((b) => b.cost_usd);
  const first = data.buckets[0]?.key;
  const last = data.buckets[data.buckets.length - 1]?.key;
  return (
    <div>
      <Sparkline values={values} hex={mc.hex} animate className="h-24 w-full" />
      <div className="mt-1 flex justify-between font-mono text-micro text-muted">
        <span>{first}</span>
        <span>{last}</span>
      </div>
    </div>
  );
}
