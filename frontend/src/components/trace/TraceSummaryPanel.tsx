import { Card } from '@/components/ui/Card';
import { StatBlock } from '@/components/ui/StatBlock';
import CountUp from '@/components/CountUp';
import type { TraceSummary } from '@/types';
import { formatCount, formatDurationMs, formatUsd, kindColorHex } from '@/lib/trace';

interface TraceSummaryPanelProps {
  summary: TraceSummary;
}

/** Trace-level KPI tiles + a per-node (per span-name) token/cost rollup table. */
export function TraceSummaryPanel({ summary }: TraceSummaryPanelProps) {
  const totalTokens = summary.input_tokens + summary.output_tokens;
  // Heaviest cost first; ties broken by duration so the hot path floats up.
  const nodes = [...summary.nodes].sort(
    (a, b) => b.cost_usd - a.cost_usd || b.duration_ms - a.duration_ms,
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card glow module="traces" className="p-5">
          <StatBlock
            label="Spans"
            value={<CountUp to={summary.span_count} duration={1} separator="." />}
          />
        </Card>
        <Card glow module="traces" className="p-5">
          <StatBlock
            label="Total Tokens"
            value={<CountUp to={totalTokens} duration={1} separator="." />}
            detail={`${formatCount(summary.input_tokens)} in / ${formatCount(summary.output_tokens)} out`}
          />
        </Card>
        <Card glow module="traces" className="p-5">
          <StatBlock label="Trace Cost" value={formatUsd(summary.cost_usd)} />
        </Card>
      </div>

      <Card module="traces">
        <p className="text-micro mb-3 text-module-traces">[ NODE ROLLUP ]</p>
        {nodes.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left">
              <thead>
                <tr className="border-b border-border text-micro text-muted">
                  <th className="py-2 pr-3 font-medium">NODE</th>
                  <th className="py-2 pr-3 text-right font-medium">COUNT</th>
                  <th className="py-2 pr-3 text-right font-medium">IN</th>
                  <th className="py-2 pr-3 text-right font-medium">OUT</th>
                  <th className="py-2 pr-3 text-right font-medium">COST</th>
                  <th className="py-2 text-right font-medium">DURATION</th>
                </tr>
              </thead>
              <tbody className="font-mono text-xs">
                {nodes.map((node) => (
                  <tr key={node.name} className="border-b border-border/50 last:border-0">
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: kindColorHex(node.kind) }}
                          aria-hidden
                        />
                        <span className="truncate text-slate-200" title={node.name}>
                          {node.name}
                        </span>
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-right text-muted">{node.count}</td>
                    <td className="py-2 pr-3 text-right text-muted">
                      {formatCount(node.input_tokens)}
                    </td>
                    <td className="py-2 pr-3 text-right text-muted">
                      {formatCount(node.output_tokens)}
                    </td>
                    <td className="py-2 pr-3 text-right text-slate-200">
                      {formatUsd(node.cost_usd)}
                    </td>
                    <td className="py-2 text-right text-muted">
                      {formatDurationMs(node.duration_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">&gt; No nodes recorded.</p>
        )}
      </Card>
    </div>
  );
}
