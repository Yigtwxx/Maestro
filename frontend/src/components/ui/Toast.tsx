import { AlertTriangle, CheckCircle2, Info, X, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { Toast as ToastData, ToastVariant } from '@/stores/toast';

// Per-variant neon treatment: brand lime for success, danger red for errors,
// cyan accent for info. The left border carries the hue; the icon matches.
// Errors announce assertively; the rest wait their turn in the live region.
const VARIANT: Record<
  ToastVariant,
  { border: string; icon: string; Icon: LucideIcon; live: 'polite' | 'assertive' }
> = {
  success: { border: 'border-l-primary', icon: 'text-primary', Icon: CheckCircle2, live: 'polite' },
  error: { border: 'border-l-danger', icon: 'text-danger', Icon: AlertTriangle, live: 'assertive' },
  info: { border: 'border-l-accent', icon: 'text-accent', Icon: Info, live: 'polite' },
};

export function Toast({
  toast,
  onDismiss,
}: {
  toast: ToastData;
  onDismiss: (id: string) => void;
}) {
  const { border, icon, Icon, live } = VARIANT[toast.variant];

  return (
    <div
      role="status"
      aria-live={live}
      className={cn(
        'toast-in flex gap-3 rounded-lg border border-l-2 border-border-bright bg-surface/95 p-3 shadow-lg backdrop-blur',
        border,
      )}
    >
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', icon)} aria-hidden />
      <div className="min-w-0 flex-1">
        {toast.title !== undefined && (
          <p className="font-mono text-xs font-bold uppercase tracking-wide text-white">
            {toast.title}
          </p>
        )}
        <p className="break-words font-mono text-xs leading-relaxed text-slate-200">
          {toast.message}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss"
        className="mt-0.5 shrink-0 text-muted transition-colors hover:text-white"
      >
        <X className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
