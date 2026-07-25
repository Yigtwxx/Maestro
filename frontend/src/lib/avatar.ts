// Monogram-avatar helpers. The avatar is rendered client-side from a palette
// key + optional emoji — no image is ever uploaded or stored. AVATAR_PALETTE
// mirrors the backend AVATAR_COLORS allow-list (core/constants.py): the server
// validates the key, the client maps it to a neon hex here.

export type AvatarColorKey =
  | 'brand'
  | 'lime'
  | 'cyan'
  | 'violet'
  | 'fuchsia'
  | 'pink'
  | 'amber'
  | 'orange'
  | 'red'
  | 'yellow'
  | 'blue'
  | 'green';

/** Palette key -> bright neon hex. Keys must stay in sync with the backend. */
export const AVATAR_PALETTE: Record<AvatarColorKey, string> = {
  brand: '#d3cbc0',
  lime: '#a3e635',
  cyan: '#22d3ee',
  violet: '#a78bfa',
  fuchsia: '#e879f9',
  pink: '#ff5cc8',
  amber: '#ffb02e',
  orange: '#ff7a45',
  red: '#ff4d5e',
  yellow: '#ffe14d',
  blue: '#3b9dff',
  green: '#2ee6a6',
};

/** Ordered keys, for rendering a picker. */
export const AVATAR_COLOR_KEYS = Object.keys(AVATAR_PALETTE) as AvatarColorKey[];

/**
 * Deterministically pick a palette color from a seed (id/email) so a user with
 * no chosen color still gets a stable, non-grey hue instead of the brand grey.
 */
export function fallbackAvatarColor(seed: string): AvatarColorKey {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  // Skip 'brand' (index 0) so the fallback is always a saturated hue.
  const hues = AVATAR_COLOR_KEYS.slice(1);
  return hues[Math.abs(hash) % hues.length];
}

/** Resolve the hex for a stored key, falling back to a seeded hue. */
export function resolveAvatarHex(
  color: string | null | undefined,
  seed: string,
): string {
  if (color && color in AVATAR_PALETTE) {
    return AVATAR_PALETTE[color as AvatarColorKey];
  }
  return AVATAR_PALETTE[fallbackAvatarColor(seed)];
}

/**
 * Initials for the monogram: up to two letters from the display name, else the
 * first character of the email local-part.
 */
export function avatarInitials(
  displayName: string | null | undefined,
  email: string,
): string {
  const name = displayName?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }
  return (email.trim()[0] ?? '?').toUpperCase();
}
