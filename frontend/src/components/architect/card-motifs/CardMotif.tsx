import { cn } from '@/lib/cn';
import { motifFor, PLACEMENT_CLASS } from './registry';

interface CardMotifProps {
  /** The squad's domain id; resolves its own motif, else its group's. */
  domain: string;
  /** The domain's bright neon (`dc.accentHex`), applied via `currentColor`. */
  accentHex: string;
}

/**
 * Domain-themed micro-animation that plays while the parent card (a `.group`)
 * is hovered. It is a pure CSS effect: invisible and paused at rest, it fades in
 * to a faint watermark and its keyframes resume on `group-hover`, and it freezes
 * at its static frame under `prefers-reduced-motion` (see `.card-motif` rules in
 * `globals.css`). The layer sits behind the card text (`-z-10`, which requires
 * the card to carry `isolate`) and never intercepts pointer events, so the whole
 * `<button>` stays the click/hover target. It clips itself rather than forcing
 * `overflow-hidden` on the card, which would otherwise crop the `BorderGlow`
 * bloom. No hooks — safe to render anywhere.
 */
export function CardMotif({ domain, accentHex }: CardMotifProps) {
  const entry = motifFor(domain);
  const Motif = entry.Motif;
  return (
    <span
      aria-hidden
      style={{ color: accentHex }}
      className="card-motif pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-[inherit]"
    >
      <span className={cn('absolute block', PLACEMENT_CLASS[entry.placement])}>
        <Motif />
      </span>
    </span>
  );
}
