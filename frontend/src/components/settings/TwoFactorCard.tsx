'use client';

import { useState } from 'react';
import { KeyRound, ShieldCheck, ShieldOff, Download, Copy } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import type { TwoFactorSetup } from '@/types';

type Stage = 'idle' | 'enrolling' | 'codes';

/** Enroll, confirm and disable TOTP two-factor auth, with recovery codes. */
export function TwoFactorCard() {
  const user = useAuthStore((s) => s.user);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [stage, setStage] = useState<Stage>('idle');
  const [setup, setSetup] = useState<TwoFactorSetup | undefined>();
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [confirmingDisable, setConfirmingDisable] = useState(false);

  if (!user) return null;
  const enabled = user.two_factor_enabled ?? false;

  const reset = () => {
    setStage('idle');
    setSetup(undefined);
    setPassword('');
    setCode('');
    setError(undefined);
    setConfirmingDisable(false);
  };

  const onBeginSetup = async () => {
    setError(undefined);
    setBusy(true);
    try {
      setSetup(await api.setup2fa());
      setStage('enrolling');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start setup.');
    } finally {
      setBusy(false);
    }
  };

  const onEnable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setBusy(true);
    try {
      const { recovery_codes } = await api.enable2fa(password, code.trim());
      setRecoveryCodes(recovery_codes);
      setStage('codes');
      setPassword('');
      setCode('');
      await refreshUser();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not enable 2FA.');
    } finally {
      setBusy(false);
    }
  };

  const onDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setBusy(true);
    try {
      await api.disable2fa(password, code.trim() || undefined);
      await refreshUser();
      toast.success('Two-factor authentication disabled.');
      reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not disable 2FA.');
    } finally {
      setBusy(false);
    }
  };

  const copyCodes = async () => {
    try {
      await navigator.clipboard.writeText(recoveryCodes.join('\n'));
      toast.success('Recovery codes copied.');
    } catch {
      toast.error('Clipboard unavailable.');
    }
  };

  const downloadCodes = () => {
    const blob = new Blob([recoveryCodes.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement('a');
      link.href = url;
      link.download = 'maestro-recovery-codes.txt';
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  return (
    <Card module="profile">
      <CardHeader icon={<KeyRound className="h-5 w-5" />} module="profile">
        <CardTitle>Two-Factor Authentication</CardTitle>
      </CardHeader>

      {/* One-time recovery codes, shown right after enabling. */}
      {stage === 'codes' ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-module-profile">
            <ShieldCheck className="h-5 w-5" aria-hidden />
            <p className="text-sm font-semibold">Two-factor authentication is on.</p>
          </div>
          <p className="text-sm text-muted">
            Save these recovery codes somewhere safe. Each works once if you lose
            your authenticator. They will not be shown again.
          </p>
          <ul className="grid grid-cols-2 gap-2 rounded-md border border-border bg-surface-2 p-3 font-mono text-sm text-white">
            {recoveryCodes.map((rc) => (
              <li key={rc}>{rc}</li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" module="profile" className="gap-1.5" onClick={copyCodes}>
              <Copy className="h-4 w-4" aria-hidden />
              Copy
            </Button>
            <Button variant="cyan-outline" className="gap-1.5" onClick={downloadCodes}>
              <Download className="h-4 w-4" aria-hidden />
              Download
            </Button>
            <Button variant="solid" module="profile" onClick={reset}>
              Done
            </Button>
          </div>
        </div>
      ) : enabled ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge tone="cyan" dot>
              Enabled
            </Badge>
            <p className="text-sm text-muted">
              A code from your authenticator is required at every sign-in.
            </p>
          </div>
          {!confirmingDisable ? (
            <Button
              variant="danger-outline"
              className="gap-1.5"
              onClick={() => setConfirmingDisable(true)}
            >
              <ShieldOff className="h-4 w-4" aria-hidden />
              Disable 2FA
            </Button>
          ) : (
            <form onSubmit={onDisable} className="grid gap-3 sm:grid-cols-2">
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                module="profile"
              />
              <Input
                label="Code (optional)"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                module="profile"
              />
              {error && <p className="text-sm text-danger sm:col-span-2">&gt; ERROR: {error}</p>}
              <div className="flex gap-2 sm:col-span-2">
                <Button variant="danger-outline" type="submit" loading={busy}>
                  Confirm disable
                </Button>
                <Button variant="ghost" type="button" onClick={reset}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </div>
      ) : stage === 'enrolling' && setup ? (
        <form onSubmit={onEnable} className="space-y-4">
          <p className="text-sm text-muted">
            Scan this QR code with an authenticator app (Google Authenticator,
            Authy, 1Password), then enter the 6-digit code it shows.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <div
              className="h-40 w-40 shrink-0 rounded-md bg-white p-2 [&_svg]:h-full [&_svg]:w-full"
              // Backend-generated SVG QR (our own origin, no external asset).
              dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
            />
            <div className="min-w-0 space-y-1">
              <p className="text-micro text-muted">Or enter this key manually</p>
              <code className="block break-all font-mono text-sm text-white">
                {setup.secret}
              </code>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Authentication code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              placeholder="123456"
              module="profile"
            />
            <Input
              label="Confirm password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              module="profile"
            />
          </div>
          {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
          <div className="flex gap-2">
            <Button variant="solid" module="profile" type="submit" loading={busy}>
              Enable 2FA
            </Button>
            <Button variant="ghost" type="button" onClick={reset}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            Add a second step to your sign-in with a time-based one-time code.
            Protects your account even if your password is leaked.
          </p>
          {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
          <Button
            variant="solid"
            module="profile"
            className="gap-1.5"
            loading={busy}
            onClick={onBeginSetup}
          >
            <ShieldCheck className="h-4 w-4" aria-hidden />
            Enable 2FA
          </Button>
        </div>
      )}
    </Card>
  );
}
