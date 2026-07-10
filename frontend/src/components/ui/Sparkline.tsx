import { cn } from '@/lib/cn';

const strokeColor = {
  lime: 'text-primary',
  cyan: 'text-accent',
  danger: 'text-danger',
} as const;

interface SparklineProps {
  values: number[];
  color?: keyof typeof strokeColor;
  /** Raw hue override (e.g. a per-domain hex); wins over `color` when set. */
  hex?: string;
  /** Grow bars from the baseline on mount (staggered per bar). */
  animate?: boolean;
  className?: string;
}

/** Tiny inline SVG bar series (mockup-style mini chart). Pure presentational. */
export function Sparkline({ values, color = 'lime', hex, animate, className }: SparklineProps) {
  if (values.length === 0) return null;
  const max = Math.max(...values, 1);
  const barWidth = 100 / values.length;
  // Whole series settles within ~0.6s regardless of bar count.
  const delayStep = Math.min(0.04, 0.6 / values.length);
  return (
    <svg
      viewBox="0 0 100 32"
      preserveAspectRatio="none"
      className={cn('h-8 w-20', !hex && strokeColor[color], animate && 'spark-grow', className)}
      style={hex ? { color: hex } : undefined}
      aria-hidden
    >
      {values.map((v, i) => {
        const h = Math.max((v / max) * 30, 2);
        return (
          <rect
            key={i}
            x={i * barWidth + barWidth * 0.15}
            y={32 - h}
            width={barWidth * 0.7}
            height={h}
            rx={1}
            className="fill-current"
            opacity={0.35 + (v / max) * 0.65}
            style={animate ? { animationDelay: `${(i * delayStep).toFixed(2)}s` } : undefined}
          />
        );
      })}
    </svg>
  );
}
