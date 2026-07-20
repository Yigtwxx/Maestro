'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardTitle } from '@/components/ui/Card';
import CountUp from '@/components/CountUp';
import { StatBlock } from '@/components/ui/StatBlock';
import { Sparkline } from '@/components/ui/Sparkline';
import { BarList } from '@/components/ui/BarList';
import { SkeletonCard, SkeletonStatTile } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { PageShell } from '@/components/layout/PageShell';
import { CostExplorer } from '@/components/trace/CostExplorer';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { CostSummary, DashboardMetrics, TokenUsage } from '@/types';

const mc = MODULE_COLOR.dashboard;

interface Tile {
  label: string;
  value: number | string;
  /** Daily trend series; omitted for point-in-time metrics (no sparkline). */
  series?: (number | null)[];
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | undefined>();
  const [usage, setUsage] = useState<TokenUsage | undefined>();
  const [cost, setCost] = useState<CostSummary | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [m, u, c] = await Promise.all([
        api.dashboardMetrics(),
        api.tokenUsage(),
        api.costSummary(),
      ]);
      setMetrics(m);
      setUsage(u);
      setCost(c);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Metrics could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const successPct = metrics ? Math.round(metrics.success_rate * 100) : 0;

  // Running and Estimated Cost are point-in-time values with no daily series.
  const tiles: Tile[] = metrics
    ? [
        { label: 'Total Tasks', value: metrics.total_tasks, series: metrics.trends.tasks },
        { label: 'Running', value: metrics.running_tasks },
        { label: 'Success Rate', value: `${successPct}%`, series: metrics.trends.success_rate },
        { label: 'Total Tokens', value: metrics.total_tokens, series: metrics.trends.tokens },
        { label: 'Completed', value: metrics.completed_tasks, series: metrics.trends.completed },
        { label: 'Failed', value: metrics.failed_tasks, series: metrics.trends.failed },
        {
          label: 'Tokens per Task',
          value: metrics.avg_tokens_per_task,
          series: metrics.trends.avg_tokens_per_task,
        },
        { label: 'Estimated Cost', value: `$${(cost?.total_cost ?? 0).toFixed(4)}` },
      ]
    : [];

  return (
    <PageShell>
      {error && <p className="mb-4 text-sm text-danger">&gt; ERROR: {error}</p>}
      {loading && (
        <>
          <p className={`font-mono text-sm ${mc.text}`}>
            &gt; LOADING METRICS<span className="animate-blink">_</span>
          </p>
          <section className="mb-8 mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <SkeletonStatTile key={i} module="dashboard" />
            ))}
          </section>
          <section className="grid gap-6 lg:grid-cols-2">
            <SkeletonCard module="dashboard" />
            <SkeletonCard module="dashboard" />
          </section>
        </>
      )}

      {metrics && (
        <>
          <Stagger onMount className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {tiles.map((tile) => (
              <StaggerItem key={tile.label}>
                <Card glow module="dashboard" className="h-full p-5">
                  <div className="flex items-end justify-between gap-2">
                    <StatBlock
                      label={tile.label}
                      value={
                        typeof tile.value === 'number' ? (
                          <CountUp to={tile.value} duration={1} separator="." />
                        ) : (
                          tile.value
                        )
                      }
                    />
                    {tile.series && (
                      <Sparkline
                        animate
                        values={tile.series}
                        hex={mc.hex}
                        className="h-7 w-14 shrink-0 opacity-60"
                      />
                    )}
                  </div>
                </Card>
              </StaggerItem>
            ))}
          </Stagger>

          <section className="grid gap-6 lg:grid-cols-2">
            <Card glow module="dashboard">
              <p className={`text-micro mb-1 ${mc.text}`}>[ TOKEN USAGE ]</p>
              <CardTitle className="mb-4 text-base">Tokens by provider</CardTitle>
              {usage && Object.keys(usage.by_provider).length > 0 ? (
                <BarList
                  color="cyan"
                  rows={Object.entries(usage.by_provider).map(([provider, stats]) => ({
                    label: provider,
                    value: stats.tokens,
                    display: `${stats.tasks} tasks · ${stats.tokens} tokens`,
                  }))}
                />
              ) : (
                <p className="text-sm text-muted">&gt; No data yet.</p>
              )}
            </Card>

            <Card glow module="dashboard">
              <p className="text-micro mb-1 text-accent">[ COST ]</p>
              <CardTitle className="mb-4 text-base">
                Cost by provider ({cost?.currency ?? 'USD'})
              </CardTitle>
              {cost && Object.keys(cost.by_provider).length > 0 ? (
                <BarList
                  color="cyan"
                  rows={Object.entries(cost.by_provider).map(([provider, amount]) => ({
                    label: provider,
                    value: amount,
                    display: `$${amount.toFixed(6)}`,
                  }))}
                />
              ) : (
                <p className="text-sm text-muted">&gt; No cost yet.</p>
              )}
            </Card>
          </section>

          <section className="mt-6">
            <CostExplorer />
          </section>
        </>
      )}
    </PageShell>
  );
}
