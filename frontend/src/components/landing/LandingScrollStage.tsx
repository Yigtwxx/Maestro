'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { EASE, useReducedMotion } from '@/lib/motion';

interface LandingScrollStageProps {
  hero: ReactNode;
  below: ReactNode;
}

type Panel = 0 | 1;

const TRANSITION_MS = 700;
// Trackpads emit a stream of tiny wheel deltas; ignore sub-pixel jitter so a
// resting finger never triggers a panel change.
const WHEEL_MIN_DELTA = 6;
// Minimum vertical swipe (px) before a touch gesture flips the panel.
const TOUCH_THRESHOLD = 36;
const EASE_CSS = `cubic-bezier(${EASE.inOut.join(',')})`;

const DOWN_KEYS = new Set(['ArrowDown', 'PageDown', ' ', 'Spacebar']);
const UP_KEYS = new Set(['ArrowUp', 'PageUp']);

/**
 * Two-panel scroll stage for the landing page. The hero owns the first
 * viewport; a single wheel / touch / key gesture slide-and-fades down to the
 * second panel (features + metrics + footer), which then scrolls on its own.
 * Scrolling back to the top of the second panel and pushing up returns to the
 * hero.
 *
 * The native document never scrolls -- the outer box is clipped and the two
 * stacked panels ride a transformed track -- so every transition is fully
 * controlled. Because the slide is a CSS transition, the browser re-runs its
 * intersection observations each frame, so the `whileInView` reveals inside the
 * second panel still fire as it arrives. Under reduced motion the same snap
 * happens instantly, with no travel and no fade.
 */
export function LandingScrollStage({ hero, below }: LandingScrollStageProps) {
  const [panel, setPanel] = useState<Panel>(0);
  const panelRef = useRef<Panel>(0);
  const lockRef = useRef(false);
  const belowRef = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  const go = useCallback(
    (next: Panel) => {
      if (lockRef.current || panelRef.current === next) return;
      lockRef.current = true;
      panelRef.current = next;
      setPanel(next);
      window.setTimeout(
        () => {
          lockRef.current = false;
        },
        reduced ? 0 : TRANSITION_MS,
      );
    },
    [reduced],
  );

  useEffect(() => {
    const atBelowTop = () => (belowRef.current?.scrollTop ?? 0) <= 0;

    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) < WHEEL_MIN_DELTA) return;
      if (panelRef.current === 0) {
        if (e.deltaY > 0) {
          e.preventDefault();
          go(1);
        }
      } else if (e.deltaY < 0 && atBelowTop()) {
        e.preventDefault();
        go(0);
      }
    };

    let touchStartY = 0;
    const onTouchStart = (e: TouchEvent) => {
      touchStartY = e.touches[0]?.clientY ?? 0;
    };
    const onTouchMove = (e: TouchEvent) => {
      // Positive delta = finger travelling up = intent to move down a panel.
      const delta = touchStartY - (e.touches[0]?.clientY ?? 0);
      if (panelRef.current === 0) {
        e.preventDefault(); // the hero has nothing to scroll natively
        if (delta > TOUCH_THRESHOLD) go(1);
      } else if (delta < -TOUCH_THRESHOLD && atBelowTop()) {
        e.preventDefault();
        go(0);
      }
    };

    const keyChunk = (key: string) =>
      key === 'ArrowUp' || key === 'ArrowDown' ? 80 : window.innerHeight * 0.9;
    const onKeyDown = (e: KeyboardEvent) => {
      if (panelRef.current === 0) {
        if (DOWN_KEYS.has(e.key)) {
          e.preventDefault();
          go(1);
        }
        return;
      }
      const el = belowRef.current;
      if (!el) return;
      if (UP_KEYS.has(e.key)) {
        e.preventDefault();
        if (el.scrollTop <= 0) go(0);
        else el.scrollBy({ top: -keyChunk(e.key), behavior: 'smooth' });
      } else if (DOWN_KEYS.has(e.key)) {
        e.preventDefault();
        el.scrollBy({ top: keyChunk(e.key), behavior: 'smooth' });
      }
    };

    window.addEventListener('wheel', onWheel, { passive: false });
    window.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: false });
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('wheel', onWheel);
      window.removeEventListener('touchstart', onTouchStart);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [go]);

  const duration = reduced ? 0 : TRANSITION_MS;
  const panelOpacity = (own: Panel) => (reduced ? 1 : panel === own ? 1 : 0);

  return (
    <div className="relative z-10 h-[100svh] overflow-hidden">
      <div
        className="h-[200svh] will-change-transform"
        style={{
          transform: `translate3d(0, ${panel === 0 ? '0' : '-50%'}, 0)`,
          transition: `transform ${duration}ms ${EASE_CSS}`,
        }}
      >
        {/* Panel 0 -- hero. */}
        <section
          inert={panel !== 0}
          className="flex h-[100svh] flex-col items-center justify-center px-5 text-center"
          style={{
            opacity: panelOpacity(0),
            transition: `opacity ${duration}ms ${EASE_CSS}`,
          }}
        >
          {hero}
        </section>

        {/* Panel 1 -- features + metrics + footer, self-scrolling. */}
        <div
          ref={belowRef}
          inert={panel !== 1}
          className="h-[100svh] overflow-y-auto overflow-x-hidden overscroll-contain"
          style={{
            opacity: panelOpacity(1),
            transition: `opacity ${duration}ms ${EASE_CSS}`,
          }}
        >
          {below}
        </div>
      </div>
    </div>
  );
}
