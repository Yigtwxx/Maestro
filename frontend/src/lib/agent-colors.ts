// Per-group neon color coding. Each *family* of agent domains owns one hue, so
// color carries identity (which kind of work) across the marketplace, agent
// catalog and live graph.
//
// This used to be one hue per domain. That stopped working at forty-three
// domains for two independent reasons. The perceptual one: the dark chart band
// holds nowhere near forty mutually distinguishable hues, so past a dozen the
// "color tells you which domain" promise quietly becomes false and the reader
// is left comparing near-identical pinks. The mechanical one: Tailwind cannot
// see dynamically built class names (`bg-domain-${x}`) and would purge them, so
// every class string has to be a full literal — one hand-written set per hue,
// mirrored twice in `tailwind.config.ts` (color + glow). Six is maintainable;
// forty-three is a file nobody edits correctly.
//
// Color does still separate domains *within* a group where the eye is comparing
// marks rather than recalling an identity: `domainColor().chartHex` steps
// lightness across the group's members. `GROUP_COLOR` is the single source of
// truth; consumers read it through `domainColor()` or `groupColor()`.

import { AGENT_DOMAINS, DOMAIN_GROUPS, DOMAIN_GROUP_OF } from '@/lib/constants';

export type AgentDomain = (typeof AGENT_DOMAINS)[number];
export type AgentDomainGroup = (typeof DOMAIN_GROUPS)[number];

export interface DomainColor {
  /** Foreground hue — icons, titles, domain labels. */
  text: string;
  /** Dim fill at 10% opacity. */
  bg: string;
  /** Hairline border at 40% opacity. */
  border: string;
  /** Solid border for the selected/active state. */
  borderSelected: string;
  /** Border tint that appears on hover. */
  borderHover: string;
  /** Solid dot / pill fill. */
  dot: string;
  /** Neon glow (selected/active). */
  glow: string;
  /** Neon glow applied on hover. */
  glowHover: string;
  /** Dark chart-step hex — data-viz marks on the surface (validated band). */
  chartHex: string;
  /** Bright neon hex — inline SVG / style props that need a raw color. */
  accentHex: string;
  /** Space-separated RGB triplet — CSS custom properties for effects. */
  rgb: string;
}

// The six group hues are inherited from the domains that used to define them,
// so the families most users already recognise keep their color: `build` from
// software's blue, `market` from marketing's pink, `money` from finance's
// green, `operate` from legal's red, `life` from the seo/local amber, and
// `knowledge` from research's violet. Those six were part of the original
// mutually-distinct set validated in the dark chart band.
export const GROUP_COLOR: Record<AgentDomainGroup, DomainColor> = {
  build: {
    text: 'text-domain-build',
    bg: 'bg-domain-build/10',
    border: 'border-domain-build/40',
    borderSelected: 'border-domain-build',
    borderHover: 'hover:border-domain-build/50',
    dot: 'bg-domain-build',
    glow: 'shadow-glow-build',
    glowHover: 'hover:shadow-glow-build',
    chartHex: '#2f86e6',
    accentHex: '#3b9dff',
    rgb: '59 157 255',
  },
  market: {
    text: 'text-domain-market',
    bg: 'bg-domain-market/10',
    border: 'border-domain-market/40',
    borderSelected: 'border-domain-market',
    borderHover: 'hover:border-domain-market/50',
    dot: 'bg-domain-market',
    glow: 'shadow-glow-market',
    glowHover: 'hover:shadow-glow-market',
    chartHex: '#e23aa0',
    accentHex: '#ff5cc8',
    rgb: '255 92 200',
  },
  money: {
    text: 'text-domain-money',
    bg: 'bg-domain-money/10',
    border: 'border-domain-money/40',
    borderSelected: 'border-domain-money',
    borderHover: 'hover:border-domain-money/50',
    dot: 'bg-domain-money',
    glow: 'shadow-glow-money',
    glowHover: 'hover:shadow-glow-money',
    chartHex: '#12a074',
    accentHex: '#2ee6a6',
    rgb: '46 230 166',
  },
  operate: {
    text: 'text-domain-operate',
    bg: 'bg-domain-operate/10',
    border: 'border-domain-operate/40',
    borderSelected: 'border-domain-operate',
    borderHover: 'hover:border-domain-operate/50',
    dot: 'bg-domain-operate',
    glow: 'shadow-glow-operate',
    glowHover: 'hover:shadow-glow-operate',
    chartHex: '#e0344e',
    accentHex: '#ff4d5e',
    rgb: '255 77 94',
  },
  life: {
    text: 'text-domain-life',
    bg: 'bg-domain-life/10',
    border: 'border-domain-life/40',
    borderSelected: 'border-domain-life',
    borderHover: 'hover:border-domain-life/50',
    dot: 'bg-domain-life',
    glow: 'shadow-glow-life',
    glowHover: 'hover:shadow-glow-life',
    chartHex: '#c17d08',
    accentHex: '#ffb02e',
    rgb: '255 176 46',
  },
  knowledge: {
    text: 'text-domain-knowledge',
    bg: 'bg-domain-knowledge/10',
    border: 'border-domain-knowledge/40',
    borderSelected: 'border-domain-knowledge',
    borderHover: 'hover:border-domain-knowledge/50',
    dot: 'bg-domain-knowledge',
    glow: 'shadow-glow-knowledge',
    glowHover: 'hover:shadow-glow-knowledge',
    chartHex: '#8b6bf0',
    accentHex: '#a78bfa',
    rgb: '167 139 250',
  },
};

/** The group an unknown domain falls back to — the one that holds `general`. */
const FALLBACK_GROUP: AgentDomainGroup = 'knowledge';

// How far a chart step may travel from its group hue, in HSL lightness points,
// split either side of it. Wide enough that adjacent bars from one family are
// separable; the clamps keep every step inside the dark band the palette was
// validated in, so a large group cannot walk a hue out into near-black.
const CHART_LIGHTNESS_SPREAD = 24;
const CHART_LIGHTNESS_MIN = 26;
const CHART_LIGHTNESS_MAX = 62;

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  const channel = (v: number) =>
    Math.round(Math.min(255, Math.max(0, v)))
      .toString(16)
      .padStart(2, '0');
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

/** HSL lightness of a hex, 0-100. */
function lightnessOf(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255);
  return ((Math.max(r, g, b) + Math.min(r, g, b)) / 2) * 100;
}

/** Re-render a hex at a different HSL lightness, keeping hue and saturation. */
function withLightness(hex: string, lightness: number): string {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const delta = max - min;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));

  let hue = 0;
  if (delta !== 0) {
    if (max === r) hue = ((g - b) / delta) % 6;
    else if (max === g) hue = (b - r) / delta + 2;
    else hue = (r - g) / delta + 4;
    hue *= 60;
    if (hue < 0) hue += 360;
  }

  const target = Math.min(
    CHART_LIGHTNESS_MAX,
    Math.max(CHART_LIGHTNESS_MIN, lightness),
  );
  const c = (1 - Math.abs((2 * target) / 100 - 1)) * saturation;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = target / 100 - c / 2;
  const [rr, gg, bb] =
    hue < 60
      ? [c, x, 0]
      : hue < 120
        ? [x, c, 0]
        : hue < 180
          ? [0, c, x]
          : hue < 240
            ? [0, x, c]
            : hue < 300
              ? [x, 0, c]
              : [c, 0, x];
  return rgbToHex((rr + m) * 255, (gg + m) * 255, (bb + m) * 255);
}

/** Group id for a domain, defaulting to the group that holds `general`. */
export function groupOf(domain: string | undefined): AgentDomainGroup {
  const group = DOMAIN_GROUP_OF[domain ?? ''];
  return (group as AgentDomainGroup) ?? FALLBACK_GROUP;
}

/** Resolve a group's color set, falling back to the generalist hue. */
export function groupColor(group: string | undefined): DomainColor {
  return GROUP_COLOR[group as AgentDomainGroup] ?? GROUP_COLOR[FALLBACK_GROUP];
}

// Built once at module load: every domain gets its group's palette, with
// `chartHex` stepped by its position within the group so a chart mixing several
// domains from one family stays readable.
const DOMAIN_PALETTE: Record<string, DomainColor> = (() => {
  const byGroup: Record<string, string[]> = {};
  for (const domain of AGENT_DOMAINS) {
    (byGroup[groupOf(domain)] ??= []).push(domain);
  }
  const palette: Record<string, DomainColor> = {};
  for (const [group, domains] of Object.entries(byGroup)) {
    const base = groupColor(group);
    const centre = lightnessOf(base.chartHex);
    domains.forEach((domain, i) => {
      const t = domains.length === 1 ? 0.5 : i / (domains.length - 1);
      palette[domain] = {
        ...base,
        chartHex: withLightness(
          base.chartHex,
          centre + (t - 0.5) * CHART_LIGHTNESS_SPREAD,
        ),
      };
    });
  }
  return palette;
})();

/** Resolve a domain's color set, falling back to the generalist hue. */
export function domainColor(domain: string | undefined): DomainColor {
  return DOMAIN_PALETTE[domain ?? ''] ?? GROUP_COLOR[FALLBACK_GROUP];
}

/** Ordered chart-step hexes, for categorical data-viz keyed by domain index. */
export const DOMAIN_CHART_HEXES: string[] = AGENT_DOMAINS.map(
  (d) => domainColor(d).chartHex,
);
