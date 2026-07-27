// Per-domain squad-card hover motifs. Each domain owns a tiny, self-contained
// SVG animation that plays only while its catalog card is hovered (§CardMotif).
// The motif is a pure presentational fragment: color arrives through
// `currentColor` (set by the wrapper from the domain's `accentHex`), motion is
// entirely CSS-driven (classes + keyframes live in `globals.css`), and animated
// nodes carry `data-play` so the wrapper's `group-hover` rule can pause/resume
// them without any React state. No hooks here — these render server-side too.
//
// A full `Record<AgentDomain, MotifEntry>` gives compile-time exhaustiveness:
// add a domain to `AGENT_DOMAINS` and forget its motif and the build fails.

import type { ComponentType } from 'react';
import type { AgentDomain } from '@/lib/agent-colors';

/**
 * Where a motif sits on the card. Placement is intentionally varied per domain
 * so the grid never reads as one repeated effect: some motifs tuck into an empty
 * corner, one runs along the bottom edge, some trace the frame, and some sit as
 * an ambient wash behind the card text.
 */
export type MotifPlacement =
  | 'corner-tr'
  | 'corner-br'
  | 'corner-bl'
  | 'edge-bottom'
  | 'frame'
  | 'behind';

/** Positioning classes the wrapper applies to the inner motif box per placement. */
export const PLACEMENT_CLASS: Record<MotifPlacement, string> = {
  'corner-tr': 'top-3 right-3 h-14 w-14 [&>svg]:h-full [&>svg]:w-full',
  'corner-br': 'bottom-3 right-3 h-14 w-14 [&>svg]:h-full [&>svg]:w-full',
  'corner-bl': 'bottom-3 left-3 h-14 w-14 [&>svg]:h-full [&>svg]:w-full',
  'edge-bottom': 'inset-x-0 bottom-0 h-8 [&>svg]:h-full [&>svg]:w-full',
  'frame': 'inset-0 [&>svg]:h-full [&>svg]:w-full',
  'behind': 'inset-0 [&>svg]:h-full [&>svg]:w-full',
};

/** One domain's motif: the SVG component plus where it is placed on the card. */
export interface MotifEntry {
  Motif: ComponentType;
  placement: MotifPlacement;
}

// ---------------------------------------------------------------------------
// Motifs. Each SVG's natural (un-animated) state is a complete, pleasant frame,
// so under `prefers-reduced-motion` — where the wrapper disables the animations
// — the card still shows a tasteful static watermark rather than a blank 0%.
// ---------------------------------------------------------------------------

/** Software: three code lines type in left-to-right, with a blinking caret. */
function SoftwareMotif() {
  const lines = [
    { y: 18, w: 40, d: '0s' },
    { y: 30, w: 30, d: '0.35s' },
    { y: 42, w: 46, d: '0.7s' },
  ];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      {lines.map((l) => (
        <rect
          key={l.y}
          data-play
          className="motif-codeline"
          x="10"
          y={l.y}
          width={l.w}
          height="4"
          rx="2"
          fill="currentColor"
          style={{ transformOrigin: 'left center', animationDelay: l.d }}
        />
      ))}
      <rect
        data-play
        className="motif-caret"
        x="12"
        y="52"
        width="4"
        height="6"
        fill="currentColor"
      />
    </svg>
  );
}

/** Finance: candles grow in 1,2,3,4; the oldest fades — a looping conveyor. */
function FinanceMotif() {
  const candles = [
    { x: 6, y: 30, h: 22, w1: 22, w2: 58, d: '0s' },
    { x: 20, y: 22, h: 30, w1: 14, w2: 58, d: '0.25s' },
    { x: 34, y: 34, h: 16, w1: 26, w2: 56, d: '0.5s' },
    { x: 48, y: 18, h: 34, w1: 12, w2: 58, d: '0.75s' },
  ];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      {candles.map((c) => (
        <g
          key={c.x}
          data-play
          className="motif-candle"
          style={{ transformOrigin: 'bottom', animationDelay: c.d }}
        >
          <line
            x1={c.x + 4}
            x2={c.x + 4}
            y1={c.w1}
            y2={c.w2}
            stroke="currentColor"
            strokeWidth="1"
          />
          <rect x={c.x} y={c.y} width="8" height={c.h} rx="1" fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}

/** Marketing: a source dot broadcasts expanding, fading signal rings. */
function MarketingMotif() {
  const rings = ['0s', '0.5s', '1s'];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <circle cx="20" cy="44" r="4" fill="currentColor" />
      {rings.map((d, i) => (
        <circle
          key={i}
          data-play
          className="motif-ping"
          cx="20"
          cy="44"
          r="10"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{ animationDelay: d }}
        />
      ))}
    </svg>
  );
}

/** SEO: a magnifier sweeps across result rows and a rank arrow ticks up. */
function SeoMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <rect x="8" y="20" width="30" height="3" rx="1.5" fill="currentColor" opacity="0.7" />
      <rect x="8" y="30" width="22" height="3" rx="1.5" fill="currentColor" opacity="0.7" />
      <rect x="8" y="40" width="26" height="3" rx="1.5" fill="currentColor" opacity="0.7" />
      <g data-play className="motif-scan">
        <circle cx="44" cy="30" r="9" fill="none" stroke="currentColor" strokeWidth="2.5" />
        <line x1="51" y1="37" x2="58" y2="44" stroke="currentColor" strokeWidth="2.5" />
      </g>
      <path
        data-play
        className="motif-rankup"
        d="M50 20 l4 -6 l4 6 M54 14 v10"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Searching: a radar dish with a rotating sweep and pinging blips. */
function SearchingMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4" />
      <circle cx="32" cy="32" r="12" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4" />
      <line x1="10" y1="32" x2="54" y2="32" stroke="currentColor" strokeWidth="0.75" opacity="0.3" />
      <line x1="32" y1="10" x2="32" y2="54" stroke="currentColor" strokeWidth="0.75" opacity="0.3" />
      <line
        data-play
        className="motif-spin"
        x1="32"
        y1="32"
        x2="32"
        y2="10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle data-play className="motif-ping" cx="44" cy="24" r="3" fill="currentColor" style={{ animationDelay: '0.4s' }} />
      <circle data-play className="motif-ping" cx="24" cy="42" r="3" fill="currentColor" style={{ animationDelay: '1.1s' }} />
    </svg>
  );
}

/** Research: an atom — a nucleus with an electron orbiting on a tilted ellipse. */
function ResearchMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <circle cx="32" cy="32" r="4" fill="currentColor" />
      <g data-play className="motif-spin">
        <ellipse cx="32" cy="32" rx="22" ry="9" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5" transform="rotate(30 32 32)" />
        <circle cx="54" cy="32" r="3.5" fill="currentColor" transform="rotate(30 32 32)" />
      </g>
    </svg>
  );
}

/** Data: a row of bars rippling up and down like a wave along the bottom edge. */
function DataMotif() {
  const bars = Array.from({ length: 9 }, (_, i) => i);
  return (
    <svg viewBox="0 0 128 32" fill="none" preserveAspectRatio="none" aria-hidden>
      {bars.map((i) => (
        <rect
          key={i}
          data-play
          className="motif-bar"
          x={8 + i * 13}
          y="6"
          width="7"
          height="24"
          rx="1.5"
          fill="currentColor"
          style={{ transformOrigin: 'bottom', animationDelay: `${i * 0.1}s` }}
        />
      ))}
    </svg>
  );
}

/** Content: a highlight traces the card frame, like a pen underlining the page. */
function ContentMotif() {
  return (
    <svg viewBox="0 0 100 100" fill="none" preserveAspectRatio="none" aria-hidden>
      <rect
        data-play
        className="motif-draw"
        x="3"
        y="3"
        width="94"
        height="94"
        rx="7"
        pathLength={1}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/** Legal: a balance scale tipping gently back and forth. */
function LegalMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <line x1="32" y1="14" x2="32" y2="50" stroke="currentColor" strokeWidth="2" />
      <path d="M20 50 h24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <g data-play className="motif-tip">
        <line x1="14" y1="18" x2="50" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M14 18 l-5 10 h10 z" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M50 18 l-5 10 h10 z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </g>
    </svg>
  );
}

/** Education: a graduation cap whose tassel swings like a pendulum. */
function EducationMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <path d="M12 26 L32 18 L52 26 L32 34 Z" fill="currentColor" />
      <path d="M20 30 v8 a12 6 0 0 0 24 0 v-8" fill="none" stroke="currentColor" strokeWidth="2" />
      <g data-play className="motif-swing">
        <line x1="48" y1="26" x2="48" y2="40" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="48" cy="42" r="2.5" fill="currentColor" />
      </g>
    </svg>
  );
}

/** Social: a chat "typing…" indicator — three dots pulsing in sequence. */
function SocialMotif() {
  const dots = [
    { cx: 20, d: '0s' },
    { cx: 32, d: '0.2s' },
    { cx: 44, d: '0.4s' },
  ];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <path
        d="M12 22 h40 a6 6 0 0 1 6 6 v10 a6 6 0 0 1 -6 6 h-26 l-8 8 v-8 h-6 a6 6 0 0 1 -6 -6 v-10 a6 6 0 0 1 6 -6 z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.5"
      />
      {dots.map((dot) => (
        <circle
          key={dot.cx}
          data-play
          className="motif-typedot"
          cx={dot.cx}
          cy="33"
          r="3.5"
          fill="currentColor"
          style={{ transformOrigin: 'center', animationDelay: dot.d }}
        />
      ))}
    </svg>
  );
}

/** Community: three member nodes with connective links pulsing between them. */
function CommunityMotif() {
  const nodes = [
    { cx: 32, cy: 16, d: '0s' },
    { cx: 16, cy: 46, d: '0.25s' },
    { cx: 48, cy: 46, d: '0.5s' },
  ];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <line data-play className="motif-link" x1="32" y1="16" x2="16" y2="46" stroke="currentColor" strokeWidth="1.5" />
      <line data-play className="motif-link" x1="16" y1="46" x2="48" y2="46" stroke="currentColor" strokeWidth="1.5" style={{ animationDelay: '0.4s' }} />
      <line data-play className="motif-link" x1="48" y1="46" x2="32" y2="16" stroke="currentColor" strokeWidth="1.5" style={{ animationDelay: '0.8s' }} />
      {nodes.map((n) => (
        <circle
          key={`${n.cx}-${n.cy}`}
          data-play
          className="motif-typedot"
          cx={n.cx}
          cy={n.cy}
          r="5"
          fill="currentColor"
          style={{ transformOrigin: 'center', animationDelay: n.d }}
        />
      ))}
    </svg>
  );
}

/** Open source: a git branch drawn along the frame, with a commit dot and merge ping. */
function OpensourceMotif() {
  return (
    <svg viewBox="0 0 100 100" fill="none" preserveAspectRatio="none" aria-hidden>
      <path
        data-play
        className="motif-draw"
        d="M14 6 V60 Q14 82 40 82 H86"
        pathLength={1}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle data-play className="motif-ping" cx="86" cy="82" r="4" fill="currentColor" style={{ animationDelay: '0.8s' }} />
      <circle cx="14" cy="6" r="3" fill="currentColor" />
    </svg>
  );
}

/** Local: a map pin drops in and settles, landing on a rippling ring. */
function LocalMotif() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      <circle data-play className="motif-ping" cx="32" cy="48" r="6" fill="none" stroke="currentColor" strokeWidth="2" style={{ animationDelay: '0.55s' }} />
      <g data-play className="motif-drop" style={{ transformOrigin: 'center bottom' }}>
        <path
          d="M32 12 a12 12 0 0 1 12 12 c0 9 -12 22 -12 22 s-12 -13 -12 -22 a12 12 0 0 1 12 -12 z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
        <circle cx="32" cy="24" r="4" fill="currentColor" />
      </g>
    </svg>
  );
}

/** General: a scattered cluster of sparkles twinkling out of phase. */
function GeneralMotif() {
  const stars = [
    { x: 20, y: 20, s: 1, d: '0s' },
    { x: 44, y: 28, s: 0.7, d: '0.5s' },
    { x: 30, y: 44, s: 0.85, d: '1s' },
    { x: 48, y: 46, s: 0.55, d: '1.4s' },
  ];
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden>
      {stars.map((star) => (
        <path
          key={`${star.x}-${star.y}`}
          data-play
          className="motif-twinkle"
          d="M0 -6 L1.6 -1.6 L6 0 L1.6 1.6 L0 6 L-1.6 1.6 L-6 0 L-1.6 -1.6 Z"
          fill="currentColor"
          transform={`translate(${star.x} ${star.y}) scale(${star.s})`}
          style={{ transformOrigin: 'center', animationDelay: star.d }}
        />
      ))}
    </svg>
  );
}

/**
 * Full domain → motif map. Placements are deliberately mixed so adjacent cards
 * in the grid animate in different regions (corner / edge / frame / behind).
 */
export const CARD_MOTIFS: Record<AgentDomain, MotifEntry> = {
  software: { Motif: SoftwareMotif, placement: 'behind' },
  finance: { Motif: FinanceMotif, placement: 'corner-br' },
  marketing: { Motif: MarketingMotif, placement: 'corner-tr' },
  seo: { Motif: SeoMotif, placement: 'corner-br' },
  searching: { Motif: SearchingMotif, placement: 'behind' },
  research: { Motif: ResearchMotif, placement: 'corner-tr' },
  data: { Motif: DataMotif, placement: 'edge-bottom' },
  content: { Motif: ContentMotif, placement: 'frame' },
  legal: { Motif: LegalMotif, placement: 'corner-bl' },
  education: { Motif: EducationMotif, placement: 'corner-br' },
  social: { Motif: SocialMotif, placement: 'corner-bl' },
  community: { Motif: CommunityMotif, placement: 'behind' },
  opensource: { Motif: OpensourceMotif, placement: 'frame' },
  local: { Motif: LocalMotif, placement: 'corner-tr' },
  general: { Motif: GeneralMotif, placement: 'behind' },
};
