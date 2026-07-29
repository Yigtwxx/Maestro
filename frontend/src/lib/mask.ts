/**
 * Partial redaction for addresses shown back to a signed-in user.
 *
 * The point is recognition, not secrecy: enough for someone to confirm which
 * inbox to open, without printing a full address onto a screen that may be
 * shared or shoulder-surfed.
 */

/** Bullet used for each hidden character. */
const DOT = '•';

/** How many leading local-part characters stay visible. */
const VISIBLE_HEAD = 1;

/** Cap on bullets, so a long local part does not render as a wall of dots. */
const MAX_DOTS = 3;

/**
 * `yigit@gmail.com` -> `y•••@gmail.com`.
 *
 * Anything without a single `@` is returned untouched rather than guessed at —
 * this is display sugar, not validation, and mangling an unexpected string
 * would be worse than showing it.
 */
export function maskEmail(email: string): string {
  const at = email.indexOf('@');
  if (at < 0 || at !== email.lastIndexOf('@')) return email;

  const local = email.slice(0, at);
  const domain = email.slice(at);
  if (local.length <= VISIBLE_HEAD) return `${local}${DOT.repeat(MAX_DOTS)}${domain}`;

  const hidden = Math.min(local.length - VISIBLE_HEAD, MAX_DOTS);
  return `${local.slice(0, VISIBLE_HEAD)}${DOT.repeat(hidden)}${domain}`;
}

/** `93` -> `1:33`, for the resend cooldown and the code countdown. */
export function formatCountdown(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}
