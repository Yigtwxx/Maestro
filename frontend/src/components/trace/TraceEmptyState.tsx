import { Card } from '@/components/ui/Card';

interface TraceEmptyStateProps {
  /** Eyebrow label; defaults to the tracing-off state. */
  eyebrow?: string;
  title?: string;
  message?: string;
}

/**
 * Shown when a trace query succeeds but returns no spans. Distinct from an
 * error: nothing failed, this task simply ran with tracing off. The copy points
 * at the per-task toggle rather than the server setting, because that is the
 * one the reader can actually change (the spans may also have aged out of the
 * TTL, which looks identical from here).
 */
export function TraceEmptyState({
  eyebrow = '[ TRACING OFF ]',
  title = 'No spans recorded for this task',
  message = 'This task ran with execution tracing off. Turn on "Execution tracing" in Task Configuration before starting a task to capture the span waterfall, token usage and cost per model call — or enable it for every task from Settings → Preferences.',
}: TraceEmptyStateProps) {
  return (
    <Card className="text-center">
      <p className="text-micro mb-2 text-module-traces">{eyebrow}</p>
      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">{message}</p>
    </Card>
  );
}
