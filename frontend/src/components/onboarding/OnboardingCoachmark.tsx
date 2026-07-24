'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { moduleColor } from '@/lib/module-colors';
import { useReducedMotion } from '@/lib/motion';
import {
  resolveSteps,
  type OnboardingContext,
  type OnboardingStep,
} from '@/lib/onboarding/steps';
import { useOnboardingStore } from '@/stores/onboarding';

/** A measured target box in viewport coordinates. */
interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

/** Absolute-positioned bubble corner in viewport coordinates. */
interface Pos {
  left: number;
  top: number;
}

const TARGET_POLL_MS = 150;
const BUBBLE_GAP = 14;
const VIEWPORT_MARGIN = 12;
/** Breathing room punched around the highlighted target. */
const SPOTLIGHT_PAD = 6;

function measureTarget(targetId: string): Rect | undefined {
  const el = document.querySelector(`[data-onboarding="${targetId}"]`);
  if (!el) return undefined;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return undefined;
  return { top: r.top, left: r.left, width: r.width, height: r.height, right: r.right, bottom: r.bottom };
}

function sameRect(a: Rect | undefined, b: Rect | undefined): boolean {
  if (a === undefined || b === undefined) return a === b;
  return (
    Math.abs(a.top - b.top) < 0.5 &&
    Math.abs(a.left - b.left) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5
  );
}

/**
 * First-run onboarding overlay. Mounted once in the authenticated shell. Reads
 * the onboarding store, anchors a coachmark to the active step's target element,
 * and advances when the user clicks that target or the "Got it" button.
 *
 * `hasApiKey` is frozen at mount so the resolved step list (and therefore the
 * stored step index) stays stable even if the user connects a key mid-tour.
 */
export function OnboardingCoachmark() {
  const pathname = usePathname();
  const reduced = useReducedMotion();

  const hydrated = useOnboardingStore((s) => s.hydrated);
  const status = useOnboardingStore((s) => s.status);
  const stepIndex = useOnboardingStore((s) => s.stepIndex);
  const hydrate = useOnboardingStore((s) => s.hydrate);
  const next = useOnboardingStore((s) => s.next);
  const complete = useOnboardingStore((s) => s.complete);
  const skip = useOnboardingStore((s) => s.skip);

  const [ctx, setCtx] = useState<OnboardingContext | undefined>(undefined);
  const [rect, setRect] = useState<Rect | undefined>(undefined);
  const [pos, setPos] = useState<Pos | undefined>(undefined);
  const bubbleRef = useRef<HTMLDivElement>(null);

  const active = hydrated && status === 'active';
  const steps = useMemo(() => (ctx ? resolveSteps(ctx) : []), [ctx]);
  const step: OnboardingStep | undefined =
    active && ctx && stepIndex < steps.length ? steps[stepIndex] : undefined;
  const onRoute = step !== undefined && step.route === pathname;

  // Read persisted state once localStorage is available.
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Freeze whether the user already has a key; drives which steps are skipped.
  useEffect(() => {
    if (!active || ctx !== undefined) return;
    let cancelled = false;
    void (async () => {
      try {
        const keys = await api.listApiKeys();
        if (!cancelled) setCtx({ hasApiKey: keys.some((k) => k.is_active) });
      } catch {
        // If we cannot tell, assume no key and show the full tour.
        if (!cancelled) setCtx({ hasApiKey: false });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, ctx]);

  // Walking past the last resolved step ends the tour.
  useEffect(() => {
    if (!active || ctx === undefined) return;
    if (steps.length > 0 && stepIndex >= steps.length) complete();
  }, [active, ctx, steps.length, stepIndex, complete]);

  // Track the target's box; polls so a target that mounts later (e.g. the
  // architect wizard advancing to its configure view) is picked up, and follows
  // scroll/resize. Capture-phase scroll catches the inner <main> scroll too.
  useEffect(() => {
    let last: Rect | undefined;
    const remeasure = () => {
      const found = step && onRoute ? measureTarget(step.targetId) : undefined;
      if (!sameRect(found, last)) {
        last = found;
        setRect(found);
      }
    };
    remeasure();
    // When there is no active target, clear any stale box and skip the listeners.
    if (!step || !onRoute) return;
    const id = window.setInterval(remeasure, TARGET_POLL_MS);
    window.addEventListener('scroll', remeasure, true);
    window.addEventListener('resize', remeasure);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('scroll', remeasure, true);
      window.removeEventListener('resize', remeasure);
    };
  }, [step, onRoute]);

  // Advance when the user clicks the highlighted target (the other exit besides
  // the "Got it" button). Capture phase so it fires before any navigation.
  useEffect(() => {
    if (!step || !onRoute) return;
    const targetId = step.targetId;
    const onClick = (e: MouseEvent) => {
      const el = e.target as Element | null;
      if (el?.closest(`[data-onboarding="${targetId}"]`)) next();
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [step, onRoute, next]);

  // Position the bubble next to the target, fully clamped inside the viewport.
  // Measured after render (bubble size is unknown until laid out).
  useEffect(() => {
    const el = bubbleRef.current;
    if (!el || !rect || !step) {
      setPos(undefined);
      return;
    }
    const bw = el.offsetWidth;
    const bh = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left: number;
    let top: number;
    switch (step.placement) {
      case 'right':
        left = rect.right + BUBBLE_GAP;
        top = rect.top + rect.height / 2 - bh / 2;
        break;
      case 'left':
        left = rect.left - BUBBLE_GAP - bw;
        top = rect.top + rect.height / 2 - bh / 2;
        break;
      case 'bottom':
        left = rect.left + rect.width / 2 - bw / 2;
        top = rect.bottom + BUBBLE_GAP;
        break;
      case 'top':
      default:
        left = rect.left + rect.width / 2 - bw / 2;
        top = rect.top - BUBBLE_GAP - bh;
        break;
    }
    left = Math.min(Math.max(left, VIEWPORT_MARGIN), vw - bw - VIEWPORT_MARGIN);
    top = Math.min(Math.max(top, VIEWPORT_MARGIN), vh - bh - VIEWPORT_MARGIN);
    setPos((prev) =>
      prev && Math.abs(prev.left - left) < 0.5 && Math.abs(prev.top - top) < 0.5
        ? prev
        : { left, top },
    );
  }, [rect, step]);

  if (!active || !step || !onRoute || !rect) return null;

  const mc = moduleColor(step.module);

  return (
    <div className="pointer-events-none fixed inset-0 z-[100]" aria-hidden={false}>
      {/* Spotlight — a padded hole in a dark scrim via a huge box-shadow. Does
          not block clicks, so the highlighted target stays interactive. */}
      <div
        className={reduced ? '' : 'transition-all duration-200'}
        style={{
          position: 'fixed',
          top: rect.top - SPOTLIGHT_PAD,
          left: rect.left - SPOTLIGHT_PAD,
          width: rect.width + SPOTLIGHT_PAD * 2,
          height: rect.height + SPOTLIGHT_PAD * 2,
          borderRadius: 10,
          boxShadow: `0 0 0 9999px rgba(3, 6, 12, 0.62), 0 0 22px 2px rgba(${mc.rgb} / 0.55)`,
          outline: `2px solid rgb(${mc.rgb})`,
          outlineOffset: 0,
          pointerEvents: 'none',
        }}
      />

      {/* Coaching bubble. */}
      <div
        ref={bubbleRef}
        role="dialog"
        aria-label="Onboarding"
        className="pointer-events-auto w-[300px] max-w-[calc(100vw-2rem)] rounded-lg border bg-surface/95 p-4 shadow-lg backdrop-blur"
        style={{
          position: 'fixed',
          left: pos?.left ?? -9999,
          top: pos?.top ?? -9999,
          visibility: pos ? 'visible' : 'hidden',
          borderColor: `rgb(${mc.rgb} / 0.5)`,
        }}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className={`text-micro ${mc.text}`}>
            {stepIndex + 1}/{steps.length}
          </span>
          <button
            type="button"
            onClick={skip}
            className="text-micro text-muted underline underline-offset-2 transition-colors hover:text-white"
          >
            Skip tour
          </button>
        </div>
        <p className="mb-1 font-sans text-sm font-bold text-white">{step.title}</p>
        <p className="font-mono text-xs leading-relaxed text-slate-200">{step.body}</p>
        <div className="mt-3 flex justify-end">
          <Button variant="solid" module={step.module} onClick={next}>
            {stepIndex + 1 === steps.length ? 'Finish' : 'Got it'}
          </Button>
        </div>
      </div>
    </div>
  );
}
