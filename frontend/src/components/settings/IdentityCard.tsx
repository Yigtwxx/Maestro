'use client';

import { useEffect, useState } from 'react';
import { UserRound, X } from 'lucide-react';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import { AVATAR_COLOR_KEYS, AVATAR_PALETTE } from '@/lib/avatar';
import { BIO_MAX_LEN } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';

// Quick-pick monogram emojis; users can also type their own.
const EMOJI_PRESETS = ['🚀', '🤖', '🧠', '⚡', '🎯', '🔮', '🦾', '🛰️', '📊', '🌐'];

/**
 * Identity & personalization: monogram avatar (palette color + optional emoji),
 * display name, short bio and email. The avatar surfaces in the sidebar, so
 * these are real, app-wide personalization — not cosmetic-only fields.
 */
export function IdentityCard() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [bio, setBio] = useState('');
  const [avatarColor, setAvatarColor] = useState<string | null>(null);
  const [avatarEmoji, setAvatarEmoji] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [savedNonce, setSavedNonce] = useState(0);

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name ?? '');
      setEmail(user.email);
      setBio(user.bio ?? '');
      setAvatarColor(user.avatar_color ?? null);
      setAvatarEmoji(user.avatar_emoji ?? '');
    }
  }, [user]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      const updated = await api.updateProfile({
        display_name: displayName,
        email,
        bio: bio.trim() || null,
        avatar_color: avatarColor,
        avatar_emoji: avatarEmoji.trim() || null,
      });
      setUser(updated);
      setSavedNonce((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('This email is already in use.');
      } else {
        setError(err instanceof ApiError ? err.message : 'Profile could not be updated.');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <Card module="profile">
      <CardHeader icon={<UserRound className="h-5 w-5" />} module="profile">
        <CardTitle>Identity</CardTitle>
      </CardHeader>
      <form onSubmit={onSave} className="space-y-5">
        {/* Live avatar preview */}
        <div className="flex items-center gap-4">
          <Avatar
            displayName={displayName}
            email={email}
            color={avatarColor}
            emoji={avatarEmoji}
            size="xl"
          />
          <div className="space-y-2">
            <p className="text-micro text-muted">Accent color</p>
            <div className="flex flex-wrap gap-2">
              {AVATAR_COLOR_KEYS.map((key) => {
                const selected = (avatarColor ?? '') === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setAvatarColor(key)}
                    aria-label={`Accent color ${key}`}
                    aria-pressed={selected}
                    className={cn(
                      'h-6 w-6 rounded-full border-2 transition-transform',
                      'motion-safe:hover:scale-110',
                      selected ? 'border-white' : 'border-transparent',
                    )}
                    style={{ backgroundColor: AVATAR_PALETTE[key] }}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* Emoji monogram */}
        <div className="space-y-2">
          <p className="text-micro text-muted">Monogram emoji (optional)</p>
          <div className="flex flex-wrap items-center gap-2">
            {EMOJI_PRESETS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                onClick={() => setAvatarEmoji(emoji)}
                aria-label={`Use ${emoji}`}
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-md border text-lg transition-colors',
                  avatarEmoji === emoji
                    ? 'border-module-profile bg-module-profile/10'
                    : 'border-border hover:bg-surface-2',
                )}
              >
                {emoji}
              </button>
            ))}
            <Input
              aria-label="Custom emoji"
              value={avatarEmoji}
              onChange={(e) => setAvatarEmoji(e.target.value)}
              placeholder="Custom"
              maxLength={8}
              module="profile"
              className="w-24 text-center"
            />
            {avatarEmoji && (
              <button
                type="button"
                onClick={() => setAvatarEmoji('')}
                aria-label="Clear emoji"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted hover:bg-surface-2 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <p className="text-micro text-muted">
            When set, the emoji replaces your initials in the avatar.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Display Name"
            placeholder="Your name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={120}
            module="profile"
          />
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            module="profile"
          />
        </div>

        <Textarea
          label={`Bio (${bio.length}/${BIO_MAX_LEN})`}
          placeholder="A short line about you or your team."
          value={bio}
          onChange={(e) => setBio(e.target.value.slice(0, BIO_MAX_LEN))}
          rows={3}
          module="profile"
        />

        {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
        <Button
          key={savedNonce}
          type="submit"
          variant="solid"
          module="profile"
          loading={saving}
          className={cn(
            savedNonce > 0 &&
              'animate-pop-flash shadow-glow-mod-profile motion-reduce:animate-none',
          )}
        >
          Save
        </Button>
      </form>
    </Card>
  );
}
