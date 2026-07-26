import type { CSSProperties } from 'react';
import { cn } from '@/lib/cn';
import { avatarInitials, resolveAvatarHex } from '@/lib/avatar';

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';

const sizeStyles: Record<AvatarSize, string> = {
  sm: 'h-7 w-7 text-[0.65rem]',
  md: 'h-9 w-9 text-xs',
  lg: 'h-12 w-12 text-base',
  xl: 'h-20 w-20 text-2xl',
};

interface AvatarProps {
  /** Seeds initials + the fallback hue; falls back to email when absent. */
  displayName?: string | null;
  email: string;
  /** Palette key (lib/avatar.ts). Undefined => seeded fallback hue. */
  color?: string | null;
  /** Optional emoji rendered instead of initials. */
  emoji?: string | null;
  size?: AvatarSize;
  className?: string;
}

/**
 * A client-rendered monogram avatar: a neon ring around the user's initials or
 * a chosen emoji, tinted by their palette color. No image is loaded — the
 * "avatar" is purely a color key + optional emoji stored on the profile.
 */
export function Avatar({
  displayName,
  email,
  color,
  emoji,
  size = 'md',
  className,
}: AvatarProps) {
  const hex = resolveAvatarHex(color, email);
  const label = emoji?.trim() || avatarInitials(displayName, email);
  return (
    <span
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full',
        'border font-sans font-bold',
        sizeStyles[size],
        className,
      )}
      style={
        {
          color: hex,
          borderColor: `${hex}66`,
          backgroundColor: `${hex}1a`,
          boxShadow: `0 0 12px ${hex}33`,
        } as CSSProperties
      }
      aria-hidden
    >
      {label}
    </span>
  );
}
