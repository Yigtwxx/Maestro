// Per-module chrome accents. Each app module owns one neon hue so the chrome
// (buttons, focus rings, glows, sidebar nav, section headers) shifts color per
// section — lime stays the brand (logo, landing, auth) instead of tinting
// everything. Domain coloring for agents lives in agent-colors.ts and is a
// separate system.
//
// Tailwind cannot see dynamically built class names (`bg-module-${x}`) and
// would purge them, so every class string below is a full literal. The
// `MODULE_COLOR` map is the single source of truth; consumers read it via
// `moduleColor()` or resolve a route with `moduleFromPathname()`.

export type ModuleKey =
  | 'dashboard'
  | 'marketplace'
  | 'architect'
  | 'agents'
  | 'documents'
  | 'api-keys'
  | 'billing'
  | 'profile'
  | 'settings'
  | 'admin'
  | 'traces'
  | 'brand';

export interface ModuleColor {
  /** Foreground hue — labels, eyebrows, icons, loading prompts. */
  text: string;
  /** Dim fill at 10% opacity. */
  bg: string;
  /** Solid fill — dots, bars, pills. */
  bgSolid: string;
  /** Hairline border at 40% opacity. */
  border: string;
  /** Border tint that appears on hover. */
  borderHover: string;
  /** Form-control focus treatment (border + ring). */
  focus: string;
  /** Neon glow ramp on focus (pair with a box-shadow transition). */
  focusGlow: string;
  /** Focus-visible ring for buttons/links. */
  ring: string;
  /** Neon glow (selected/active). */
  glow: string;
  /** Neon glow applied on hover. */
  glowHover: string;
  /** Solid CTA button treatment (black text on the neon hue). */
  btnSolid: string;
  /** Outline button treatment (hue text on dim fill). */
  btnOutline: string;
  /** Sidebar active nav item treatment. */
  navActive: string;
  /** Sidebar inactive nav icon tint on hover (requires `group` on the link). */
  navIconHover: string;
  /** Bright neon hex — inline SVG / style props that need a raw color. */
  hex: string;
  /** Space-separated RGB triplet — CSS custom properties for effects. */
  rgb: string;
}

export const MODULE_COLOR: Record<ModuleKey, ModuleColor> = {
  dashboard: {
    text: 'text-module-dashboard',
    bg: 'bg-module-dashboard/10',
    bgSolid: 'bg-module-dashboard',
    border: 'border-module-dashboard/40',
    borderHover: 'hover:border-module-dashboard/50',
    focus: 'focus:border-module-dashboard focus-visible:ring-module-dashboard/60',
    focusGlow: 'focus:shadow-glow-mod-dashboard',
    ring: 'focus-visible:ring-module-dashboard',
    glow: 'shadow-glow-mod-dashboard',
    glowHover: 'hover:shadow-glow-mod-dashboard',
    btnSolid:
      'bg-module-dashboard text-black hover:brightness-110 hover:shadow-glow-mod-dashboard focus-visible:ring-module-dashboard',
    btnOutline:
      'border border-module-dashboard/60 bg-module-dashboard/10 text-module-dashboard hover:border-module-dashboard hover:shadow-glow-mod-dashboard focus-visible:ring-module-dashboard',
    navActive: 'bg-module-dashboard text-black shadow-glow-mod-dashboard',
    navIconHover: 'group-hover:text-module-dashboard',
    hex: '#22d3ee',
    rgb: '34 211 238',
  },
  marketplace: {
    text: 'text-module-marketplace',
    bg: 'bg-module-marketplace/10',
    bgSolid: 'bg-module-marketplace',
    border: 'border-module-marketplace/40',
    borderHover: 'hover:border-module-marketplace/50',
    focus: 'focus:border-module-marketplace focus-visible:ring-module-marketplace/60',
    focusGlow: 'focus:shadow-glow-mod-marketplace',
    ring: 'focus-visible:ring-module-marketplace',
    glow: 'shadow-glow-mod-marketplace',
    glowHover: 'hover:shadow-glow-mod-marketplace',
    btnSolid:
      'bg-module-marketplace text-black hover:brightness-110 hover:shadow-glow-mod-marketplace focus-visible:ring-module-marketplace',
    btnOutline:
      'border border-module-marketplace/60 bg-module-marketplace/10 text-module-marketplace hover:border-module-marketplace hover:shadow-glow-mod-marketplace focus-visible:ring-module-marketplace',
    navActive: 'bg-module-marketplace text-black shadow-glow-mod-marketplace',
    navIconHover: 'group-hover:text-module-marketplace',
    hex: '#ff5cc8',
    rgb: '255 92 200',
  },
  architect: {
    text: 'text-module-architect',
    bg: 'bg-module-architect/10',
    bgSolid: 'bg-module-architect',
    border: 'border-module-architect/40',
    borderHover: 'hover:border-module-architect/50',
    focus: 'focus:border-module-architect focus-visible:ring-module-architect/60',
    focusGlow: 'focus:shadow-glow-mod-architect',
    ring: 'focus-visible:ring-module-architect',
    glow: 'shadow-glow-mod-architect',
    glowHover: 'hover:shadow-glow-mod-architect',
    btnSolid:
      'bg-module-architect text-black hover:brightness-110 hover:shadow-glow-mod-architect focus-visible:ring-module-architect',
    btnOutline:
      'border border-module-architect/60 bg-module-architect/10 text-module-architect hover:border-module-architect hover:shadow-glow-mod-architect focus-visible:ring-module-architect',
    navActive: 'bg-module-architect text-black shadow-glow-mod-architect',
    navIconHover: 'group-hover:text-module-architect',
    hex: '#9d4dff',
    rgb: '157 77 255',
  },
  agents: {
    text: 'text-module-agents',
    bg: 'bg-module-agents/10',
    bgSolid: 'bg-module-agents',
    border: 'border-module-agents/40',
    borderHover: 'hover:border-module-agents/50',
    focus: 'focus:border-module-agents focus-visible:ring-module-agents/60',
    focusGlow: 'focus:shadow-glow-mod-agents',
    ring: 'focus-visible:ring-module-agents',
    glow: 'shadow-glow-mod-agents',
    glowHover: 'hover:shadow-glow-mod-agents',
    btnSolid:
      'bg-module-agents text-black hover:brightness-110 hover:shadow-glow-mod-agents focus-visible:ring-module-agents',
    btnOutline:
      'border border-module-agents/60 bg-module-agents/10 text-module-agents hover:border-module-agents hover:shadow-glow-mod-agents focus-visible:ring-module-agents',
    navActive: 'bg-module-agents text-black shadow-glow-mod-agents',
    navIconHover: 'group-hover:text-module-agents',
    hex: '#3b9dff',
    rgb: '59 157 255',
  },
  documents: {
    text: 'text-module-documents',
    bg: 'bg-module-documents/10',
    bgSolid: 'bg-module-documents',
    border: 'border-module-documents/40',
    borderHover: 'hover:border-module-documents/50',
    focus: 'focus:border-module-documents focus-visible:ring-module-documents/60',
    focusGlow: 'focus:shadow-glow-mod-documents',
    ring: 'focus-visible:ring-module-documents',
    glow: 'shadow-glow-mod-documents',
    glowHover: 'hover:shadow-glow-mod-documents',
    btnSolid:
      'bg-module-documents text-black hover:brightness-110 hover:shadow-glow-mod-documents focus-visible:ring-module-documents',
    btnOutline:
      'border border-module-documents/60 bg-module-documents/10 text-module-documents hover:border-module-documents hover:shadow-glow-mod-documents focus-visible:ring-module-documents',
    navActive: 'bg-module-documents text-black shadow-glow-mod-documents',
    navIconHover: 'group-hover:text-module-documents',
    hex: '#ff7a45',
    rgb: '255 122 69',
  },
  'api-keys': {
    text: 'text-module-api-keys',
    bg: 'bg-module-api-keys/10',
    bgSolid: 'bg-module-api-keys',
    border: 'border-module-api-keys/40',
    borderHover: 'hover:border-module-api-keys/50',
    focus: 'focus:border-module-api-keys focus-visible:ring-module-api-keys/60',
    focusGlow: 'focus:shadow-glow-mod-api-keys',
    ring: 'focus-visible:ring-module-api-keys',
    glow: 'shadow-glow-mod-api-keys',
    glowHover: 'hover:shadow-glow-mod-api-keys',
    btnSolid:
      'bg-module-api-keys text-black hover:brightness-110 hover:shadow-glow-mod-api-keys focus-visible:ring-module-api-keys',
    btnOutline:
      'border border-module-api-keys/60 bg-module-api-keys/10 text-module-api-keys hover:border-module-api-keys hover:shadow-glow-mod-api-keys focus-visible:ring-module-api-keys',
    navActive: 'bg-module-api-keys text-black shadow-glow-mod-api-keys',
    navIconHover: 'group-hover:text-module-api-keys',
    hex: '#2ee6a6',
    rgb: '46 230 166',
  },
  billing: {
    text: 'text-module-billing',
    bg: 'bg-module-billing/10',
    bgSolid: 'bg-module-billing',
    border: 'border-module-billing/40',
    borderHover: 'hover:border-module-billing/50',
    focus: 'focus:border-module-billing focus-visible:ring-module-billing/60',
    focusGlow: 'focus:shadow-glow-mod-billing',
    ring: 'focus-visible:ring-module-billing',
    glow: 'shadow-glow-mod-billing',
    glowHover: 'hover:shadow-glow-mod-billing',
    btnSolid:
      'bg-module-billing text-black hover:brightness-110 hover:shadow-glow-mod-billing focus-visible:ring-module-billing',
    btnOutline:
      'border border-module-billing/60 bg-module-billing/10 text-module-billing hover:border-module-billing hover:shadow-glow-mod-billing focus-visible:ring-module-billing',
    navActive: 'bg-module-billing text-black shadow-glow-mod-billing',
    navIconHover: 'group-hover:text-module-billing',
    hex: '#ffb02e',
    rgb: '255 176 46',
  },
  profile: {
    text: 'text-module-profile',
    bg: 'bg-module-profile/10',
    bgSolid: 'bg-module-profile',
    border: 'border-module-profile/40',
    borderHover: 'hover:border-module-profile/50',
    focus: 'focus:border-module-profile focus-visible:ring-module-profile/60',
    focusGlow: 'focus:shadow-glow-mod-profile',
    ring: 'focus-visible:ring-module-profile',
    glow: 'shadow-glow-mod-profile',
    glowHover: 'hover:shadow-glow-mod-profile',
    btnSolid:
      'bg-module-profile text-black hover:brightness-110 hover:shadow-glow-mod-profile focus-visible:ring-module-profile',
    btnOutline:
      'border border-module-profile/60 bg-module-profile/10 text-module-profile hover:border-module-profile hover:shadow-glow-mod-profile focus-visible:ring-module-profile',
    navActive: 'bg-module-profile text-black shadow-glow-mod-profile',
    navIconHover: 'group-hover:text-module-profile',
    hex: '#e879f9',
    rgb: '232 121 249',
  },
  settings: {
    text: 'text-module-settings',
    bg: 'bg-module-settings/10',
    bgSolid: 'bg-module-settings',
    border: 'border-module-settings/40',
    borderHover: 'hover:border-module-settings/50',
    focus: 'focus:border-module-settings focus-visible:ring-module-settings/60',
    focusGlow: 'focus:shadow-glow-mod-settings',
    ring: 'focus-visible:ring-module-settings',
    glow: 'shadow-glow-mod-settings',
    glowHover: 'hover:shadow-glow-mod-settings',
    btnSolid:
      'bg-module-settings text-black hover:brightness-110 hover:shadow-glow-mod-settings focus-visible:ring-module-settings',
    btnOutline:
      'border border-module-settings/60 bg-module-settings/10 text-module-settings hover:border-module-settings hover:shadow-glow-mod-settings focus-visible:ring-module-settings',
    navActive: 'bg-module-settings text-black shadow-glow-mod-settings',
    navIconHover: 'group-hover:text-module-settings',
    hex: '#2ee6a6',
    rgb: '46 230 166',
  },
  admin: {
    text: 'text-module-admin',
    bg: 'bg-module-admin/10',
    bgSolid: 'bg-module-admin',
    border: 'border-module-admin/40',
    borderHover: 'hover:border-module-admin/50',
    focus: 'focus:border-module-admin focus-visible:ring-module-admin/60',
    focusGlow: 'focus:shadow-glow-mod-admin',
    ring: 'focus-visible:ring-module-admin',
    glow: 'shadow-glow-mod-admin',
    glowHover: 'hover:shadow-glow-mod-admin',
    btnSolid:
      'bg-module-admin text-black hover:brightness-110 hover:shadow-glow-mod-admin focus-visible:ring-module-admin',
    btnOutline:
      'border border-module-admin/60 bg-module-admin/10 text-module-admin hover:border-module-admin hover:shadow-glow-mod-admin focus-visible:ring-module-admin',
    navActive: 'bg-module-admin text-black shadow-glow-mod-admin',
    navIconHover: 'group-hover:text-module-admin',
    hex: '#ff4d5e',
    rgb: '255 77 94',
  },
  traces: {
    text: 'text-module-traces',
    bg: 'bg-module-traces/10',
    bgSolid: 'bg-module-traces',
    border: 'border-module-traces/40',
    borderHover: 'hover:border-module-traces/50',
    focus: 'focus:border-module-traces focus-visible:ring-module-traces/60',
    focusGlow: 'focus:shadow-glow-mod-traces',
    ring: 'focus-visible:ring-module-traces',
    glow: 'shadow-glow-mod-traces',
    glowHover: 'hover:shadow-glow-mod-traces',
    btnSolid:
      'bg-module-traces text-black hover:brightness-110 hover:shadow-glow-mod-traces focus-visible:ring-module-traces',
    btnOutline:
      'border border-module-traces/60 bg-module-traces/10 text-module-traces hover:border-module-traces hover:shadow-glow-mod-traces focus-visible:ring-module-traces',
    navActive: 'bg-module-traces text-black shadow-glow-mod-traces',
    navIconHover: 'group-hover:text-module-traces',
    hex: '#6d7cff',
    rgb: '109 124 255',
  },
  brand: {
    text: 'text-module-brand',
    bg: 'bg-module-brand/10',
    bgSolid: 'bg-module-brand',
    border: 'border-module-brand/40',
    borderHover: 'hover:border-module-brand/50',
    focus: 'focus:border-module-brand focus-visible:ring-module-brand/60',
    focusGlow: 'focus:shadow-glow-mod-brand',
    ring: 'focus-visible:ring-module-brand',
    glow: 'shadow-glow-mod-brand',
    glowHover: 'hover:shadow-glow-mod-brand',
    btnSolid:
      'bg-module-brand text-black hover:brightness-110 hover:shadow-glow-mod-brand focus-visible:ring-module-brand',
    btnOutline:
      'border border-module-brand/60 bg-module-brand/10 text-module-brand hover:border-module-brand hover:shadow-glow-mod-brand focus-visible:ring-module-brand',
    navActive: 'bg-module-brand text-black shadow-glow-mod-brand',
    navIconHover: 'group-hover:text-module-brand',
    hex: '#d3cbc0',
    rgb: '211 203 192',
  },
};

/** Resolve a module's colors, falling back to the champagne brand. */
export function moduleColor(key: ModuleKey | undefined): ModuleColor {
  return MODULE_COLOR[key ?? 'brand'];
}

const MODULE_ROUTES: ReadonlyArray<[prefix: string, key: ModuleKey]> = [
  ['/dashboard', 'dashboard'],
  ['/marketplace', 'marketplace'],
  ['/architect', 'architect'],
  ['/traces', 'traces'],
  ['/agents', 'agents'],
  ['/documents', 'documents'],
  // Settings sub-sections resolve to their own hue; more specific prefixes
  // must precede the bare '/settings' fallback since matching is first-hit.
  ['/settings/api-keys', 'api-keys'],
  ['/settings/billing', 'billing'],
  ['/settings/profile', 'profile'],
  ['/settings', 'settings'],
  ['/admin', 'admin'],
];

/** Resolve the module owning a pathname — used by Sidebar/TopBar chrome. */
export function moduleFromPathname(pathname: string): ModuleKey {
  const match = MODULE_ROUTES.find(([prefix]) => pathname.startsWith(prefix));
  return match ? match[1] : 'brand';
}
