'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { animate, stagger } from 'animejs';
import type { Target } from 'animejs';
import { domainColor } from '@/lib/agent-colors';
import type { AgentDomain } from '@/lib/agent-colors';
import { cn } from '@/lib/cn';

// Full-bleed cinematic take on the reference "Maestro Landing" design: a central
// MAESTRO CORE card wired to six domain-colored subagents pushed to the screen
// edges, over ambient neon spotlights. Purely decorative (aria-hidden); renders
// a static final frame under reduced motion.

interface SubagentSpec {
  domain: AgentDomain;
  label: string;
  side: 'left' | 'right';
  row: 0 | 1 | 2;
}

// Six subagents, three per side. Each owns a domain hue so color carries
// identity — matching the marketplace, agent catalog and live architect graph.
const SUBAGENTS: readonly SubagentSpec[] = [
  { domain: 'software', label: 'SOFTWARE', side: 'left', row: 0 },
  { domain: 'finance', label: 'FINANCE', side: 'left', row: 1 },
  { domain: 'marketing', label: 'MARKETING', side: 'left', row: 2 },
  { domain: 'seo', label: 'SEO', side: 'right', row: 0 },
  { domain: 'research', label: 'RESEARCH', side: 'right', row: 1 },
  { domain: 'data', label: 'DATA', side: 'right', row: 2 },
] as const;

// Tasks the core cycles through — pure decoration, hints at live orchestration.
const TASKS: readonly string[] = [
  'Analyze Q3 market sentiment',
  'Extract competitor pricing',
  'Generate the weekly content calendar',
] as const;

// Fixed design canvas — the diagram is authored at this size and scaled to fit
// the viewport, so the edge-pushed layout never overlaps or overflows.
const DESIGN_W = 1200;
const DESIGN_H = 680;
const CX = DESIGN_W / 2;
const CY = DESIGN_H / 2;

// Node half-extents (px) used to anchor wires at the subagent edges.
const NODE_HALF_W = 96;
// The central orchestrator card the bonds converge onto. There is no core orb:
// every bundle plugs directly into the card-edge segment facing its subagent, so
// the wires read as feeding the rectangle itself (matching the reference sketch).
const CARD_HALF_W = 118; // 236 / 2 — half the orchestrator card width
const CARD_HALF_H = 95; // 190 / 2 — half the orchestrator card height
const INTAKE_INSET = 18; // strand roots land on the flat edge, not the rounded corner

// Pixel center of each subagent on the design canvas. Middle row is pulled a
// touch further inward so its wire clears the outer rows (echoes the reference).
function nodeCenter(spec: SubagentSpec): { x: number; y: number } {
  const inset = spec.row === 1 ? 200 : 150;
  const x = spec.side === 'left' ? inset : DESIGN_W - inset;
  const y = [140, CY, DESIGN_H - 140][spec.row];
  return { x, y };
}

// A "soul-bond" strand: a single smooth cubic Bézier that flows organically out
// of the subagent and into the core — no rigid circuit elbows. `midOffset` shifts
// both control points vertically while the endpoints stay fixed, so a bundle of
// strands with different offsets converges at both ends and opens in the middle.
function bondPath(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  midOffset: number,
): string {
  const dx = x2 - x1;
  const cx1 = x1 + dx * 0.5;
  const cx2 = x2 - dx * 0.5;
  return `M ${x1} ${y1} C ${cx1} ${y1 + midOffset}, ${cx2} ${y2 + midOffset}, ${x2} ${y2}`;
}

// Bonds root along the card's whole core-facing run — never a single point. The
// run is row-aware, always the edges closest to the central core: the TOP row
// uses the inner vertical edge plus half of its bottom (long) edge; the BOTTOM
// row uses the inner vertical edge plus half of its top edge; the MIDDLE row
// uses the inner vertical edge with a small symmetric wrap onto both edges.
const STRANDS_PER_BOND = 18; // many thin threads across the near side
const NODE_HALF_H = 30; // half-height of the card (short edge)
const LONG_EDGE_REACH = NODE_HALF_W; // roots reach the middle of the long edge
const MID_WRAP = 26; // middle-row wrap onto the top/bottom edges (px)

// Energy-pulse dash pattern: a short bright packet (FLOW_DASH) plus a long gap,
// so pulses read as discrete sparks flowing along the bond into the core.
const FLOW_DASH = 3;
const FLOW_PERIOD = 49; // FLOW_DASH + gap; also the per-loop strokeDashoffset step

// Ordered "near perimeter" polyline for a subagent: the run of card edge that
// faces the core, walked so strand param t (0..1) flows evenly along it.
function nearPerimeter(spec: SubagentSpec): { x: number; y: number }[] {
  const c = nodeCenter(spec);
  const inward = spec.side === 'left' ? -1 : 1; // toward the card center
  const innerX = spec.side === 'left' ? c.x + NODE_HALF_W : c.x - NODE_HALF_W;
  const top = c.y - NODE_HALF_H;
  const bot = c.y + NODE_HALF_H;
  if (spec.row === 0) {
    // Top subagent: down the inner edge, then out along the bottom (long) edge.
    return [
      { x: innerX, y: top },
      { x: innerX, y: bot },
      { x: innerX + inward * LONG_EDGE_REACH, y: bot },
    ];
  }
  if (spec.row === 2) {
    // Bottom subagent: in along the top (long) edge, then down the inner edge.
    return [
      { x: innerX + inward * LONG_EDGE_REACH, y: top },
      { x: innerX, y: top },
      { x: innerX, y: bot },
    ];
  }
  // Middle subagent: inner edge with a small symmetric wrap onto both edges.
  return [
    { x: innerX + inward * MID_WRAP, y: top },
    { x: innerX, y: top },
    { x: innerX, y: bot },
    { x: innerX + inward * MID_WRAP, y: bot },
  ];
}

// Ordered segment of the orchestrator card's perimeter facing a given subagent.
// Strand core-ends spread along this segment (fan-in) the same way their roots
// spread along the subagent's near perimeter (fan-out) — so each bundle plugs
// into the whole facing edge of the rectangle instead of a single point.
function coreIntake(spec: SubagentSpec): { x: number; y: number }[] {
  const left = CX - CARD_HALF_W;
  const right = CX + CARD_HALF_W;
  const top = CY - CARD_HALF_H;
  const bot = CY + CARD_HALF_H;
  if (spec.row === 1) {
    // Middle rows plug into the whole vertical edge on their side.
    const x = spec.side === 'left' ? left : right;
    return [
      { x, y: CY - 42 },
      { x, y: CY + 42 },
    ];
  }
  // Top/bottom rows plug into their half of the horizontal (top/bottom) edge.
  const y = spec.row === 0 ? top : bot;
  return spec.side === 'left'
    ? [
        { x: left + INTAKE_INSET, y },
        { x: CX - 8, y },
      ]
    : [
        { x: CX + 8, y },
        { x: right - INTAKE_INSET, y },
      ];
}

// Point at fraction t (0..1) along a polyline, distributed by arc length.
function pointAlong(
  points: { x: number; y: number }[],
  t: number,
): { x: number; y: number } {
  const lengths = points
    .slice(1)
    .map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
  const total = lengths.reduce((a, b) => a + b, 0);
  let d = t * total;
  for (let i = 0; i < lengths.length; i++) {
    if (d <= lengths[i] || i === lengths.length - 1) {
      const u = lengths[i] === 0 ? 0 : d / lengths[i];
      return {
        x: points[i].x + (points[i + 1].x - points[i].x) * u,
        y: points[i].y + (points[i + 1].y - points[i].y) * u,
      };
    }
    d -= lengths[i];
  }
  return points[points.length - 1];
}

interface Filament {
  d: string;
  width: number;
  opacity: number;
}

interface Wire {
  filaments: Filament[];
  // Single centerline down the middle of the bundle — the track energy pulses
  // travel along from the subagent into the core.
  flowD: string;
  color: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

const WIRES: Wire[] = SUBAGENTS.map((spec) => {
  const c = nodeCenter(spec);
  const fromX = spec.side === 'left' ? c.x + NODE_HALF_W : c.x - NODE_HALF_W;
  // Every bundle plugs into the card-edge segment facing this subagent: strand
  // roots spread along the subagent's near perimeter (fan-out) and their core-ends
  // spread along the intake segment (fan-in) at the same param t.
  const perimeter = nearPerimeter(spec);
  const intake = coreIntake(spec);
  // No core orb to arc around anymore, so bonds run straight into the edge.
  const bow = 0;
  const filaments = Array.from({ length: STRANDS_PER_BOND }, (_, j) => {
    const t = j / (STRANDS_PER_BOND - 1); // 0..1 along both runs
    const centerBias = 1 - Math.abs(t - 0.5) * 2; // fuller mid-run, faint at ends
    const root = pointAlong(perimeter, t);
    const coreEnd = pointAlong(intake, t);
    return {
      d: bondPath(root.x, root.y, coreEnd.x, coreEnd.y, bow),
      width: 0.5 + 0.8 * centerBias, // thin throughout; mid strands a touch fuller
      opacity: 0.3 + 0.5 * centerBias, // faintest at run ends, brightest mid-run
    };
  });
  // Centerline of the bundle (root midpoint → intake midpoint) for the flowing pulse.
  const mid = pointAlong(perimeter, 0.5);
  const intakeMid = pointAlong(intake, 0.5);
  const flowD = bondPath(mid.x, mid.y, intakeMid.x, intakeMid.y, bow);
  return {
    filaments,
    flowD,
    color: domainColor(spec.domain).accentHex,
    x1: fromX,
    y1: c.y,
    x2: intakeMid.x,
    y2: intakeMid.y,
  };
});

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export default function HeroConstellation() {
  const outerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const cardGlowRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<HTMLDivElement[]>([]);
  const pathRefs = useRef<SVGPathElement[]>([]);
  const flowRefs = useRef<SVGPathElement[]>([]);
  // Guards the one-shot entrance so a resize never replays the fly-in.
  const hasEnteredRef = useRef(false);

  const [scale, setScale] = useState(1);
  const [taskIndex, setTaskIndex] = useState(0);
  const [reduced, setReduced] = useState(false);

  // Fresh each render so a resize never animates stale nodes.
  nodeRefs.current = [];
  pathRefs.current = [];
  flowRefs.current = [];

  useEffect(() => {
    setReduced(prefersReducedMotion());
  }, []);

  // Scale the fixed-size diagram to fit the available viewport (never up-scaled).
  useEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setScale(Math.min(1, rect.width / DESIGN_W, rect.height / DESIGN_H));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Rotate the core's task text on a timer (fade handled via re-mount + CSS).
  useEffect(() => {
    const id = window.setInterval(() => {
      setTaskIndex((i) => (i + 1) % TASKS.length);
    }, 2800);
    return () => window.clearInterval(id);
  }, []);

  // Drive the entrance + looping glows once reduced-motion and scale are known.
  useEffect(() => {
    if (scale <= 0) return;
    const paths = pathRefs.current.filter(Boolean);
    const flows = flowRefs.current.filter(Boolean);
    const nodes = nodeRefs.current.filter(Boolean);
    const leftNodes = nodes.filter((_, i) => SUBAGENTS[i]?.side === 'left');
    const rightNodes = nodes.filter((_, i) => SUBAGENTS[i]?.side === 'right');
    const card = cardRef.current;
    const cardGlow = cardGlowRef.current;

    // Draw every wire from full length → 0 so it renders complete when static.
    paths.forEach((p) => {
      const len = p.getTotalLength();
      p.style.strokeDasharray = String(len);
      p.style.strokeDashoffset = reduced ? '0' : String(len);
    });

    // Energy pulses only exist while motion is allowed; hidden under reduced motion.
    flows.forEach((p) => {
      p.style.opacity = reduced ? '0' : '1';
    });

    if (reduced) {
      nodes.forEach((n) => {
        n.style.opacity = '1';
        n.style.transform = 'none';
      });
      if (card) card.style.opacity = '1';
      return;
    }

    const entered = hasEnteredRef.current;
    hasEnteredRef.current = true;

    // Start each node one viewport-width off its own side so it flies in from
    // beyond the edge. Scale cancels the canvas transform, so on-screen travel
    // equals one viewport width regardless of the fit scale.
    const offset = typeof window !== 'undefined' ? window.innerWidth / scale : DESIGN_W;

    // Entrance choreography: nodes fly in slowly by row; each bond draws in as its
    // own node closes in, finishing just after it lands — so no cable ever hangs in
    // empty space before its agent arrives.
    const NODE_START = 260; // first row begins
    const NODE_STAGGER = 150; // gap between rows on each side
    const NODE_DURATION = 1200; // slower, more graceful fly-in

    const instances: ReturnType<typeof animate>[] = [];

    if (!entered) {
      instances.push(
        animate(paths, {
          strokeDashoffset: 0,
          duration: 900,
          // Begin drawing as the bond's own node closes in (~65% through its flight)
          // and finish just after it lands. Filaments of one bond share the delay.
          delay: (_target?: Target, idx = 0) => {
            const bondIndex = Math.floor(idx / STRANDS_PER_BOND);
            const row = SUBAGENTS[bondIndex]?.row ?? 0;
            return NODE_START + row * NODE_STAGGER + NODE_DURATION * 0.65;
          },
          ease: 'inOutQuad',
        }),
        animate(leftNodes, {
          opacity: [0, 1],
          translateX: [-offset, 0],
          duration: NODE_DURATION,
          ease: 'outCubic',
          delay: stagger(NODE_STAGGER, { start: NODE_START }),
        }),
        animate(rightNodes, {
          opacity: [0, 1],
          translateX: [offset, 0],
          duration: NODE_DURATION,
          ease: 'outCubic',
          delay: stagger(NODE_STAGGER, { start: NODE_START }),
        }),
      );
      if (card) {
        instances.push(
          animate(card, {
            opacity: [0, 1],
            scale: [0.86, 1],
            duration: 700,
            ease: 'outBack',
          }),
        );
      }
    }

    // Continuous energy: bright packets travel each bond's centerline from the
    // subagent into the core. Dash period is fixed, so one offset step loops
    // seamlessly on bonds of any length. Starts after the fly-in on first mount
    // (so no pulse rides a cable before its agent lands), immediately thereafter.
    if (flows.length) {
      const flowStart = entered
        ? 0
        : NODE_START + 2 * NODE_STAGGER + NODE_DURATION;
      instances.push(
        animate(flows, {
          strokeDashoffset: [0, -FLOW_PERIOD], // negative → travels toward the core
          duration: 1600,
          ease: 'linear',
          loop: true,
          delay: stagger(140, { start: flowStart }),
        }),
      );
    }

    if (cardGlow) {
      instances.push(
        animate(cardGlow, {
          opacity: [
            { to: 0.85, duration: 1500 },
            { to: 0.35, duration: 1500 },
          ],
          ease: 'inOutSine',
          loop: true,
        }),
      );
    }

    return () => instances.forEach((a) => a.pause());
  }, [reduced, scale]);

  const nodes = useMemo(() => SUBAGENTS.map((spec) => ({ spec, c: nodeCenter(spec) })), []);

  return (
    <div
      ref={outerRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 select-none overflow-hidden"
    >
      {/* Only the core carries an ambient light — the subagents stay crisp so
          just their neon frames and labels glow. */}
      <div className="pointer-events-none absolute inset-0">
        {/* Center core spotlight — soft white bloom, gently pulsing. */}
        <div
          className="absolute left-1/2 top-1/2 h-[26rem] w-[34rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[90px] animate-pulse-glow"
          style={{
            background:
              'radial-gradient(circle, rgba(255,255,255,0.5) 0%, rgba(163,230,53,0.24) 42%, transparent 72%)',
            mixBlendMode: 'screen',
          }}
        />
      </div>

      {/* Fixed-size diagram canvas, scaled to fit and centered. */}
      <div
        className="absolute left-1/2 top-1/2"
        style={{
          width: DESIGN_W,
          height: DESIGN_H,
          transform: `translate(-50%, -50%) scale(${scale})`,
          transformOrigin: 'center',
        }}
      >
        {/* Wire layer — under the nodes so cables appear to plug in. */}
        <svg
          className="absolute inset-0"
          width={DESIGN_W}
          height={DESIGN_H}
          viewBox={`0 0 ${DESIGN_W} ${DESIGN_H}`}
          fill="none"
        >
          <defs>
            <filter id="wireGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Wide, soft bloom for the domain sector glows pooling where each
                bundle meets the card edge. */}
            <filter id="sectorGlow" x="-200%" y="-200%" width="500%" height="500%">
              <feGaussianBlur stdDeviation="10" />
            </filter>
            {/* Each strand fades from its domain hue at the agent into a bright
                white at the core — six threads merging into one soul. */}
            {WIRES.map((wire, i) => (
              <linearGradient
                key={i}
                id={`bond-${i}`}
                gradientUnits="userSpaceOnUse"
                x1={wire.x1}
                y1={wire.y1}
                x2={wire.x2}
                y2={wire.y2}
              >
                <stop offset="0%" stopColor={wire.color} stopOpacity={0.95} />
                <stop offset="70%" stopColor={wire.color} stopOpacity={0.9} />
                <stop offset="100%" stopColor="#ffffff" stopOpacity={0.95} />
              </linearGradient>
            ))}
          </defs>
          {WIRES.map((wire, i) => (
            <g key={i} filter="url(#wireGlow)">
              {/* Multi-filament soul-bond: thin neon strands that converge at both
                  ends and open in the middle. Each is drawn in on entrance. */}
              {wire.filaments.map((f, j) => (
                <path
                  key={j}
                  ref={(node) => {
                    if (node) pathRefs.current[i * STRANDS_PER_BOND + j] = node;
                  }}
                  d={f.d}
                  stroke={`url(#bond-${i})`}
                  strokeWidth={f.width}
                  strokeLinecap="round"
                  opacity={f.opacity}
                />
              ))}
            </g>
          ))}
          {/* Energy-pulse layer: one bright packet-track per bond, animated in the
              entrance effect so sparks stream from each subagent into the core. */}
          <g filter="url(#wireGlow)">
            {WIRES.map((wire, i) => (
              <path
                key={i}
                ref={(node) => {
                  if (node) flowRefs.current[i] = node;
                }}
                d={wire.flowD}
                stroke={wire.color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeDasharray={`${FLOW_DASH} ${FLOW_PERIOD - FLOW_DASH}`}
                style={{ opacity: 0 }}
              />
            ))}
          </g>
          {/* Colored sector glows: each bundle pools its domain hue where it meets
              the card edge, so the rectangle reads as fed by all six domains at once. */}
          {WIRES.map((wire, i) => (
            <circle
              key={`sector-${i}`}
              cx={wire.x2}
              cy={wire.y2}
              r={16}
              fill={wire.color}
              filter="url(#sectorGlow)"
              style={{ mixBlendMode: 'screen', opacity: 0.75 }}
            />
          ))}
        </svg>

        {/* Subagent nodes. Outer wrapper centers on the anchor; the inner box is
            the anime.js target so its transform never fights centering. */}
        {nodes.map(({ spec, c }, i) => {
          const color = domainColor(spec.domain);
          return (
            <div
              key={spec.domain}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: c.x, top: c.y }}
            >
              <div
                ref={(node) => {
                  if (node) nodeRefs.current[i] = node;
                }}
                className={cn(
                  'relative w-[184px] rounded-xl border-2 bg-surface/85 px-4 py-3 backdrop-blur-sm',
                  color.borderSelected,
                )}
                style={{
                  opacity: 0,
                  boxShadow: `0 0 0 1.5px ${color.accentHex}, 0 0 14px -1px ${color.accentHex}, inset 0 0 10px -6px ${color.accentHex}`,
                }}
              >
                <div className="flex items-center justify-between">
                  <span
                    className="font-mono text-[10px] font-semibold tracking-[0.22em]"
                    style={{ color: color.accentHex, opacity: 0.75 }}
                  >
                    AGENT
                  </span>
                  <span
                    className="h-1.5 w-1.5 rounded-full animate-pulse-glow"
                    style={{ backgroundColor: color.accentHex }}
                  />
                </div>
                <div
                  className="mt-1 font-sans text-[16px] font-semibold"
                  style={{ color: color.accentHex, textShadow: `0 0 14px ${color.accentHex}` }}
                >
                  {spec.label}
                </div>
              </div>
            </div>
          );
        })}

        {/* Central MAESTRO CORE card. */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <div
            ref={cardRef}
            className="relative flex h-[190px] w-[236px] flex-col justify-between rounded-2xl border-[1.5px] border-white/70 bg-surface/25 px-6 py-4 text-center"
            style={{
              opacity: 0,
              boxShadow:
                '0 0 60px -12px rgba(255,255,255,0.35), 0 0 90px -20px rgba(163,230,53,0.35), 0 0 90px -20px rgba(34,211,238,0.3)',
            }}
          >
            {/* Slowly rotating multicolor halo behind the card — a round,
                blurred conic sweep so it reads as an energy aura, not a square. */}
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-8 -z-10 rounded-full opacity-50 blur-lg animate-[spin_9s_linear_infinite]"
              style={{
                background:
                  'conic-gradient(from 0deg, transparent, rgba(163,230,53,0.55), transparent 28%, rgba(34,211,238,0.55), transparent 58%, rgba(255,92,200,0.55), transparent)',
              }}
            />
            {/* Soft white glow, pulsing with anime.js. */}
            <span
              ref={cardGlowRef}
              aria-hidden
              className="pointer-events-none absolute inset-0 -z-10 rounded-2xl bg-primary blur-2xl"
              style={{ opacity: 0.35 }}
            />
            <div className="font-mono text-[10px] font-semibold tracking-[0.2em] text-white/55">
              MAESTRO CORE
            </div>
            <div
              className="mt-1.5 font-sans text-[22px] font-bold text-white"
              style={{ textShadow: '0 0 18px rgba(255,255,255,0.55)' }}
            >
              Orchestrator
            </div>
            <p
              key={taskIndex}
              className={cn(
                'mt-3 border-t border-white/10 pt-2.5 font-mono text-[11px] leading-snug text-slate-300',
                !reduced && 'animate-fade-in',
              )}
            >
              {TASKS[taskIndex]}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
