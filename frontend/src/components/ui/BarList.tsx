// Horizontal single-hue magnitude bars (ranking). Values stay in text ink.
// Shared by the dashboard token/cost cards and the trace cost explorer.

export interface BarRow {
  label: string;
  value: number;
  display: string;
  /** Per-row bar color (categorical breakdowns); overrides `color` when set. */
  hex?: string;
}

interface BarListProps {
  rows: BarRow[];
  /** Uniform fill when a row carries no `hex`. */
  color?: 'lime' | 'cyan';
}

export function BarList({ rows, color = 'cyan' }: BarListProps) {
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
              className={`bar-grow h-full rounded-sm ${row.hex ? '' : fill}`}
              style={{
                width: `${Math.max((row.value / max) * 100, 2)}%`,
                animationDelay: `${(i * 0.05).toFixed(2)}s`,
                backgroundColor: row.hex,
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
