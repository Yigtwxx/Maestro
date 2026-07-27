import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import type { TraceSpan } from '@/types';
import {
  formatDurationMs,
  formatTimestamp,
  formatUsd,
  spanColorHex,
  spanFinishReason,
  spanIsEstimated,
  spanKindLabel,
  spanModel,
  spanProvider,
  spanStatusLabel,
  spanTokens,
} from '@/lib/trace';

/** One label/value row; value is monospaced. Omitted entirely when empty. */
function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === undefined || value === null || value === '') return undefined;
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-micro shrink-0 text-muted">{label}</span>
      <span className="text-right font-mono text-xs text-slate-200 break-all">{value}</span>
    </div>
  );
}

interface SpanDetailProps {
  span: TraceSpan | undefined;
}

/** Detail panel for the selected span. Renders a hint when nothing is picked. */
export function SpanDetail({ span }: SpanDetailProps) {
  if (!span) {
    return (
      <Card>
        <p className="text-micro mb-2 text-module-traces">[ SPAN DETAIL ]</p>
        <p className="text-sm text-muted">&gt; Select a span to inspect its attributes.</p>
      </Card>
    );
  }

  const tokens = spanTokens(span);
  const model = spanModel(span);
  const provider = spanProvider(span);
  const finish = spanFinishReason(span);
  const isError = span.status === 'error';
  const hex = spanColorHex(span);

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: hex }}
          aria-hidden
        />
        <p className="truncate font-mono text-sm font-bold text-white" title={span.name}>
          {span.name}
        </p>
      </div>

      <div className="divide-y divide-border">
        <DetailRow label="TYPE" value={spanKindLabel(span.kind)} />
        <DetailRow
          label="STATUS"
          value={
            <span className={cn(isError ? 'text-danger' : 'text-slate-200')}>
              {spanStatusLabel(span.status)}
            </span>
          }
        />
        <DetailRow label="DURATION" value={formatDurationMs(span.duration_ms)} />
        <DetailRow label="MODEL" value={model} />
        <DetailRow label="PROVIDER" value={provider} />
        {(tokens.input > 0 || tokens.output > 0) && (
          <DetailRow
            label="TOKENS"
            value={
              <>
                {tokens.input} in / {tokens.output} out
                {spanIsEstimated(span) && <span className="ml-1 text-warning">(est)</span>}
              </>
            }
          />
        )}
        {span.cost_usd > 0 && <DetailRow label="COST" value={formatUsd(span.cost_usd)} />}
        <DetailRow label="FINISH REASON" value={finish} />
        <DetailRow label="STARTED" value={formatTimestamp(span.start_time)} />
      </div>

      {span.attributes['maestro.request.preview'] !== undefined && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-micro mb-1 text-muted">REQUEST PREVIEW</p>
          <p className="font-mono text-xs text-slate-300">
            {String(span.attributes['maestro.request.preview'])}
          </p>
        </div>
      )}

      {isError && span.error_message && (
        <div className="mt-3 rounded-md border border-danger/40 bg-danger/10 p-3">
          <p className="text-micro mb-1 text-danger">ERROR</p>
          <p className="font-mono text-xs text-danger">{span.error_message}</p>
        </div>
      )}
    </Card>
  );
}
