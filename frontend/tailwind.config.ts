import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Maestro palette — "neon arcade / synthwave" full-spectrum. Near-black
        // base, warm champagne brand + cyan, with a per-domain neon spectrum.
        background: '#0a0a10',
        surface: '#12121c',
        'surface-2': '#171724',
        border: {
          DEFAULT: '#26263a',
          bright: '#3d3d5c',
        },
        primary: {
          DEFAULT: '#d3cbc0',
          hover: '#e0dbd3',
          dim: 'rgba(211,203,192,0.10)',
        },
        accent: {
          DEFAULT: '#22d3ee',
          dim: 'rgba(34,211,238,0.10)',
        },
        danger: {
          DEFAULT: '#ff4d6d',
          dim: 'rgba(255,77,109,0.10)',
        },
        // Orange caution hue — user-initiated stops (cancelled tasks), kept
        // distinct from danger red. Same hex as domain.data, separate semantic.
        warning: {
          DEFAULT: '#ff7a45',
          dim: 'rgba(255,122,69,0.10)',
        },
        // Neon mint for successful outcomes. Same hex as domain.finance —
        // Tailwind's emerald-* reads washed-out against the near-black base and
        // sits outside this palette.
        success: {
          DEFAULT: '#2ee6a6',
          dim: 'rgba(46,230,166,0.10)',
        },
        // GitHub Sponsors brand pink — used only by the Sponsor CTA.
        sponsor: {
          DEFAULT: '#db61a2',
          dim: 'rgba(219,97,162,0.10)',
        },
        muted: '#8b8fa3',
        // Per-domain neon hues (bright — UI accents, glows, chips, active state).
        // Opacity modifiers (bg-domain-x/10, border-domain-x/40) supply the dim
        // fills, so no separate -dim tokens are needed.
        domain: {
          software: '#3b9dff',
          finance: '#2ee6a6',
          marketing: '#ff5cc8',
          seo: '#ffb02e',
          searching: '#22d3ee',
          research: '#a78bfa',
          data: '#ff7a45',
          content: '#e879f9',
          legal: '#ff4d5e',
          education: '#ffe14d',
          // Connected-API squads. Each is a tonal variant of its functional
          // sibling rather than a new hue: kinship is the signal, and the
          // spectrum is already dense at eleven domains. social/community are
          // the two listening squads (marketing pink), opensource belongs to
          // the software blue family, local to the seo amber family.
          social: '#ff8ad8',
          community: '#d63da6',
          opensource: '#7ec4ff',
          local: '#ffcd7a',
          general: '#a3e635',
        },
        // Per-module chrome accents — each app module owns one neon hue so the
        // chrome (buttons, focus, glows, nav) shifts color per section instead
        // of reusing the lime brand everywhere. Hexes mirror proven domain.*
        // values; kept as separate semantic tokens so they can be retuned
        // without touching the domain system. Source of truth for consumers:
        // src/lib/module-colors.ts.
        module: {
          dashboard: '#22d3ee',
          marketplace: '#ff5cc8',
          architect: '#9d4dff',
          agents: '#3b9dff',
          documents: '#ff7a45',
          // The three settings sub-sections each own a distinct hue so the
          // sidebar tabs and per-page chrome no longer share one color.
          'api-keys': '#2ee6a6',
          billing: '#ffb02e',
          profile: '#e879f9',
          settings: '#2ee6a6',
          // Moderation/admin chrome — a commanding red that reads as authority,
          // distinct from the marketplace pink and the danger semantic.
          admin: '#ff4d5e',
          // Observability/traces chrome — an indigo neon sitting in the gap
          // between the agents blue and the architect violet.
          traces: '#6d7cff',
          brand: '#d3cbc0',
        },
        // Chart-step hues — the domain hues stepped down into the dark chart
        // lightness band (OKLCH L 0.48–0.67) for data-viz marks on the surface.
        // The original eleven were validated as a mutually-distinct set (worst
        // adjacent CVD ΔE 16.4). That claim does NOT extend to the four
        // connected-API squads below: they are deliberate tonal variants of
        // their sibling domain, so social/marketing and community/marketing
        // read as related rather than distinct. Separation within a family is
        // lightness, not hue — do not treat these as CVD-separable pairs.
        chart: {
          software: '#2f86e6',
          finance: '#12a074',
          marketing: '#e23aa0',
          seo: '#c17d08',
          searching: '#1594ae',
          research: '#8b6bf0',
          data: '#e8641f',
          content: '#c026d3',
          legal: '#e0344e',
          education: '#bfa50f',
          social: '#e86bb4',
          community: '#b82d85',
          opensource: '#5ea8f0',
          local: '#d69a3a',
          general: '#749f10',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'glow-primary': '0 0 24px -6px rgba(211,203,192,0.45)',
        'glow-cyan': '0 0 24px -6px rgba(34,211,238,0.45)',
        'glow-danger': '0 0 24px -6px rgba(255,77,109,0.45)',
        'glow-warning': '0 0 24px -6px rgba(255,122,69,0.45)',
        'glow-sponsor': '0 0 24px -6px rgba(219,97,162,0.45)',
        // Per-domain neon glows (mirror the domain.* hues).
        'glow-software': '0 0 24px -6px rgba(59,157,255,0.45)',
        'glow-finance': '0 0 24px -6px rgba(46,230,166,0.45)',
        'glow-marketing': '0 0 24px -6px rgba(255,92,200,0.45)',
        'glow-seo': '0 0 24px -6px rgba(255,176,46,0.45)',
        'glow-searching': '0 0 24px -6px rgba(34,211,238,0.45)',
        'glow-research': '0 0 24px -6px rgba(167,139,250,0.45)',
        'glow-data': '0 0 24px -6px rgba(255,122,69,0.45)',
        'glow-content': '0 0 24px -6px rgba(232,121,249,0.45)',
        'glow-legal': '0 0 24px -6px rgba(255,77,94,0.45)',
        'glow-education': '0 0 24px -6px rgba(255,225,77,0.45)',
        'glow-social': '0 0 24px -6px rgba(255,138,216,0.45)',
        'glow-community': '0 0 24px -6px rgba(214,61,166,0.45)',
        'glow-opensource': '0 0 24px -6px rgba(126,196,255,0.45)',
        'glow-local': '0 0 24px -6px rgba(255,205,122,0.45)',
        'glow-general': '0 0 24px -6px rgba(163,230,53,0.45)',
        // Per-module neon glows (mirror the module.* hues).
        'glow-mod-dashboard': '0 0 24px -6px rgba(34,211,238,0.45)',
        'glow-mod-marketplace': '0 0 24px -6px rgba(255,92,200,0.45)',
        'glow-mod-architect': '0 0 24px -6px rgba(157,77,255,0.45)',
        'glow-mod-agents': '0 0 24px -6px rgba(59,157,255,0.45)',
        'glow-mod-documents': '0 0 24px -6px rgba(255,122,69,0.45)',
        'glow-mod-api-keys': '0 0 24px -6px rgba(46,230,166,0.45)',
        'glow-mod-billing': '0 0 24px -6px rgba(255,176,46,0.45)',
        'glow-mod-profile': '0 0 24px -6px rgba(232,121,249,0.45)',
        'glow-mod-settings': '0 0 24px -6px rgba(46,230,166,0.45)',
        'glow-mod-admin': '0 0 24px -6px rgba(255,77,94,0.45)',
        'glow-mod-traces': '0 0 24px -6px rgba(109,124,255,0.45)',
        'glow-mod-brand': '0 0 24px -6px rgba(211,203,192,0.45)',
      },
      letterSpacing: {
        micro: '0.18em',
      },
      keyframes: {
        blink: {
          '0%, 49%': { opacity: '1' },
          '50%, 100%': { opacity: '0' },
        },
        dash: {
          to: { strokeDashoffset: '-16' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        indeterminate: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(400%)' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          from: { transform: 'translateX(-150%) skewX(-12deg)' },
          to: { transform: 'translateX(250%) skewX(-12deg)' },
        },
        'border-pan': {
          from: { backgroundPosition: '0% 50%, 0 0' },
          to: { backgroundPosition: '200% 50%, 0 0' },
        },
        'flow-dash': {
          to: { strokeDashoffset: '-24' },
        },
        'pop-flash': {
          '0%': { filter: 'brightness(1)' },
          '35%': { filter: 'brightness(1.35)' },
          '100%': { filter: 'brightness(1)' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-6px)' },
          '40%': { transform: 'translateX(6px)' },
          '60%': { transform: 'translateX(-3px)' },
          '80%': { transform: 'translateX(3px)' },
        },
        'shine-sweep': {
          from: { backgroundPosition: '150% center' },
          to: { backgroundPosition: '-50% center' },
        },
        'gradient-pan': {
          from: { backgroundPosition: '0% 50%' },
          to: { backgroundPosition: '100% 50%' },
        },
        'word-in': {
          from: {
            opacity: '0',
            transform: 'translateY(6px)',
            filter: 'blur(4px)',
          },
          to: { opacity: '1', transform: 'translateY(0)', filter: 'blur(0px)' },
        },
        'node-ping': {
          '0%': { opacity: '0.7', transform: 'scale(1)' },
          '100%': { opacity: '0', transform: 'scale(1.05)' },
        },
      },
      animation: {
        blink: 'blink 1.1s step-end infinite',
        dash: 'dash 0.9s linear infinite',
        'pulse-glow': 'pulse-glow 1.6s ease-in-out infinite',
        indeterminate: 'indeterminate 1.4s ease-in-out infinite',
        'fade-in': 'fade-in 0.25s ease-out both',
        shimmer: 'shimmer 0.9s ease-out',
        'border-pan': 'border-pan 6s linear infinite',
        'flow-dash': 'flow-dash 1.2s linear infinite',
        'pop-flash': 'pop-flash 0.4s ease-out',
        shake: 'shake 0.4s ease-in-out',
        'shine-sweep': 'shine-sweep 3s linear infinite',
        'gradient-pan': 'gradient-pan 4s ease-in-out infinite alternate',
        'word-in': 'word-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
        'node-ping': 'node-ping 1.6s ease-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
