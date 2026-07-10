'use client';

import { useEffect } from 'react';
import { Toast } from '@/components/ui/Toast';
import { useToastStore, type Toast as ToastData } from '@/stores/toast';

/**
 * Owns one toast's auto-dismiss timer. Keyed by id in the list, so it mounts
 * once per toast and its timer never restarts when a sibling toast is added --
 * a single shared effect over the array would reset every countdown on each push.
 */
function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastData;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), toast.duration);
    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, onDismiss]);

  return <Toast toast={toast} onDismiss={onDismiss} />;
}

/**
 * Global toast viewport, mounted once in the root layout beside CookieNotice.
 * Top-right so it never overlaps the bottom-right cookie notice. Timers live in
 * the client component, so a server render never schedules one.
 */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Notifications"
      className="fixed right-3 top-3 z-50 flex w-[calc(100%-1.5rem)] max-w-sm flex-col gap-2 sm:w-96"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
      ))}
    </div>
  );
}
