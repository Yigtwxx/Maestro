// Per-domain neon color coding. Each agent domain owns one hue so color carries
// identity (which domain) across the marketplace, agent catalog and live graph.
//
// Tailwind cannot see dynamically built class names (`bg-domain-${x}`) and would
// purge them, so every class string below is a full literal. The `DOMAIN_COLOR`
// map is the single source of truth; consumers read it via `domainColor()`.

import { AGENT_DOMAINS } from '@/lib/constants';

export type AgentDomain = (typeof AGENT_DOMAINS)[number];

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

export const DOMAIN_COLOR: Record<AgentDomain, DomainColor> = {
  software: {
    text: 'text-domain-software',
    bg: 'bg-domain-software/10',
    border: 'border-domain-software/40',
    borderSelected: 'border-domain-software',
    borderHover: 'hover:border-domain-software/50',
    dot: 'bg-domain-software',
    glow: 'shadow-glow-software',
    glowHover: 'hover:shadow-glow-software',
    chartHex: '#2f86e6',
    accentHex: '#3b9dff',
    rgb: '59 157 255',
  },
  finance: {
    text: 'text-domain-finance',
    bg: 'bg-domain-finance/10',
    border: 'border-domain-finance/40',
    borderSelected: 'border-domain-finance',
    borderHover: 'hover:border-domain-finance/50',
    dot: 'bg-domain-finance',
    glow: 'shadow-glow-finance',
    glowHover: 'hover:shadow-glow-finance',
    chartHex: '#12a074',
    accentHex: '#2ee6a6',
    rgb: '46 230 166',
  },
  marketing: {
    text: 'text-domain-marketing',
    bg: 'bg-domain-marketing/10',
    border: 'border-domain-marketing/40',
    borderSelected: 'border-domain-marketing',
    borderHover: 'hover:border-domain-marketing/50',
    dot: 'bg-domain-marketing',
    glow: 'shadow-glow-marketing',
    glowHover: 'hover:shadow-glow-marketing',
    chartHex: '#e23aa0',
    accentHex: '#ff5cc8',
    rgb: '255 92 200',
  },
  seo: {
    text: 'text-domain-seo',
    bg: 'bg-domain-seo/10',
    border: 'border-domain-seo/40',
    borderSelected: 'border-domain-seo',
    borderHover: 'hover:border-domain-seo/50',
    dot: 'bg-domain-seo',
    glow: 'shadow-glow-seo',
    glowHover: 'hover:shadow-glow-seo',
    chartHex: '#c17d08',
    accentHex: '#ffb02e',
    rgb: '255 176 46',
  },
  searching: {
    text: 'text-domain-searching',
    bg: 'bg-domain-searching/10',
    border: 'border-domain-searching/40',
    borderSelected: 'border-domain-searching',
    borderHover: 'hover:border-domain-searching/50',
    dot: 'bg-domain-searching',
    glow: 'shadow-glow-searching',
    glowHover: 'hover:shadow-glow-searching',
    chartHex: '#1594ae',
    accentHex: '#22d3ee',
    rgb: '34 211 238',
  },
  research: {
    text: 'text-domain-research',
    bg: 'bg-domain-research/10',
    border: 'border-domain-research/40',
    borderSelected: 'border-domain-research',
    borderHover: 'hover:border-domain-research/50',
    dot: 'bg-domain-research',
    glow: 'shadow-glow-research',
    glowHover: 'hover:shadow-glow-research',
    chartHex: '#8b6bf0',
    accentHex: '#a78bfa',
    rgb: '167 139 250',
  },
  data: {
    text: 'text-domain-data',
    bg: 'bg-domain-data/10',
    border: 'border-domain-data/40',
    borderSelected: 'border-domain-data',
    borderHover: 'hover:border-domain-data/50',
    dot: 'bg-domain-data',
    glow: 'shadow-glow-data',
    glowHover: 'hover:shadow-glow-data',
    chartHex: '#e8641f',
    accentHex: '#ff7a45',
    rgb: '255 122 69',
  },
  content: {
    text: 'text-domain-content',
    bg: 'bg-domain-content/10',
    border: 'border-domain-content/40',
    borderSelected: 'border-domain-content',
    borderHover: 'hover:border-domain-content/50',
    dot: 'bg-domain-content',
    glow: 'shadow-glow-content',
    glowHover: 'hover:shadow-glow-content',
    chartHex: '#c026d3',
    accentHex: '#e879f9',
    rgb: '232 121 249',
  },
  legal: {
    text: 'text-domain-legal',
    bg: 'bg-domain-legal/10',
    border: 'border-domain-legal/40',
    borderSelected: 'border-domain-legal',
    borderHover: 'hover:border-domain-legal/50',
    dot: 'bg-domain-legal',
    glow: 'shadow-glow-legal',
    glowHover: 'hover:shadow-glow-legal',
    chartHex: '#e0344e',
    accentHex: '#ff4d5e',
    rgb: '255 77 94',
  },
  education: {
    text: 'text-domain-education',
    bg: 'bg-domain-education/10',
    border: 'border-domain-education/40',
    borderSelected: 'border-domain-education',
    borderHover: 'hover:border-domain-education/50',
    dot: 'bg-domain-education',
    glow: 'shadow-glow-education',
    glowHover: 'hover:shadow-glow-education',
    chartHex: '#bfa50f',
    accentHex: '#ffe14d',
    rgb: '255 225 77',
  },
  // Connected-API squads. Tonal variants of their functional sibling rather
  // than new hues — social/community share the marketing pink, opensource the
  // software blue, local the seo amber. Similar job, similar colour.
  social: {
    text: 'text-domain-social',
    bg: 'bg-domain-social/10',
    border: 'border-domain-social/40',
    borderSelected: 'border-domain-social',
    borderHover: 'hover:border-domain-social/50',
    dot: 'bg-domain-social',
    glow: 'shadow-glow-social',
    glowHover: 'hover:shadow-glow-social',
    chartHex: '#e86bb4',
    accentHex: '#ff8ad8',
    rgb: '255 138 216',
  },
  community: {
    text: 'text-domain-community',
    bg: 'bg-domain-community/10',
    border: 'border-domain-community/40',
    borderSelected: 'border-domain-community',
    borderHover: 'hover:border-domain-community/50',
    dot: 'bg-domain-community',
    glow: 'shadow-glow-community',
    glowHover: 'hover:shadow-glow-community',
    chartHex: '#b82d85',
    accentHex: '#d63da6',
    rgb: '214 61 166',
  },
  opensource: {
    text: 'text-domain-opensource',
    bg: 'bg-domain-opensource/10',
    border: 'border-domain-opensource/40',
    borderSelected: 'border-domain-opensource',
    borderHover: 'hover:border-domain-opensource/50',
    dot: 'bg-domain-opensource',
    glow: 'shadow-glow-opensource',
    glowHover: 'hover:shadow-glow-opensource',
    chartHex: '#5ea8f0',
    accentHex: '#7ec4ff',
    rgb: '126 196 255',
  },
  local: {
    text: 'text-domain-local',
    bg: 'bg-domain-local/10',
    border: 'border-domain-local/40',
    borderSelected: 'border-domain-local',
    borderHover: 'hover:border-domain-local/50',
    dot: 'bg-domain-local',
    glow: 'shadow-glow-local',
    glowHover: 'hover:shadow-glow-local',
    chartHex: '#d69a3a',
    accentHex: '#ffcd7a',
    rgb: '255 205 122',
  },
  general: {
    text: 'text-domain-general',
    bg: 'bg-domain-general/10',
    border: 'border-domain-general/40',
    borderSelected: 'border-domain-general',
    borderHover: 'hover:border-domain-general/50',
    dot: 'bg-domain-general',
    glow: 'shadow-glow-general',
    glowHover: 'hover:shadow-glow-general',
    chartHex: '#749f10',
    accentHex: '#a3e635',
    rgb: '163 230 53',
  },
};

/** Resolve a domain's color set, falling back to the generalist hue. */
export function domainColor(domain: string | undefined): DomainColor {
  return DOMAIN_COLOR[domain as AgentDomain] ?? DOMAIN_COLOR.general;
}

/** Ordered chart-step hexes, for categorical data-viz keyed by domain index. */
export const DOMAIN_CHART_HEXES: string[] = AGENT_DOMAINS.map(
  (d) => DOMAIN_COLOR[d].chartHex,
);
