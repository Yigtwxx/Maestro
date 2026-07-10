'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardTitle } from '@/components/ui/Card';
import CountUp from '@/components/CountUp';
import { StatBlock } from '@/components/ui/StatBlock';
import { Sparkline } from '@/components/ui/Sparkline';
import { SkeletonCard, SkeletonStatTile } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { CostSummary, DashboardMetrics, TokenUsage } from '@/types';

const mc = MODULE_COLOR.dashboard;

// Placeholder series: the API exposes only current totals (no history yet),
// so tiles render a decorative flat-ish series until a history endpoint exists.
const PLACEHOLDER_SERIES = [4, 7, 5, 9, 6, 8, 10, 7];

interface BarRow {
  label: string;
  value: number;
  display: string;
}

/** Horizontal single-hue bar list (magnitude ranking). Values stay in text ink. */
function BarList({ rows, color }: { rows: BarRow[]; color: 'lime' | 'cyan' }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const fill = color === 'lime' ? 'bg-primary' : 'bg-accent';
  return (
    <ul className="space-y-3">
      {rows.map((row, i) => (
        <li key={row.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="text-sm capitalize text-slate-200">{row.label}</span>
            <span className="font-mono text-xs text-muted">{row.display}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-sm bg-surface-2">
            {/* One-shot grow on mount; re-renders reuse the DOM so it never replays. */}
            <div
              className={`bar-grow h-full rounded-sm ${fill}`}
              style={{
                width: `${Math.max((row.value / max) * 100, 2)}%`,
                animationDelay: `${(i * 0.05).toFixed(2)}s`,
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
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

  const tiles = metrics
    ? [
        { label: 'Total Tasks', value: metrics.total_tasks },
        { label: 'Running', value: metrics.running_tasks },
        { label: 'Success Rate', value: `${successPct}%` },
        { label: 'Total Tokens', value: metrics.total_tokens },
        { label: 'Completed', value: metrics.completed_tasks },
        { label: 'Failed', value: metrics.failed_tasks },
        { label: 'Tokens per Task', value: metrics.avg_tokens_per_task },
        { label: 'Estimated Cost', value: `$${(cost?.total_cost ?? 0).toFixed(4)}` },
      ]
    : [];

  return (
    <div className="mx-auto max-w-5xl px-6 pt-5 pb-8">
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
                    <Sparkline
                      animate
                      values={PLACEHOLDER_SERIES}
                      hex={mc.hex}
                      className="h-7 w-14 shrink-0 opacity-60"
                    />
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
                <p className="text-sm text-muted">&gt; No cost yet (free tier).</p>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
