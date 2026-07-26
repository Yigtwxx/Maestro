'use client';

import { useEffect } from 'react';
import {
  BRAND,
  MONOGRAM_GRADIENT,
  MONOGRAM_PATH,
  MONOGRAM_STROKE_WIDTH,
} from '@/lib/seo/config';
import { isTaskRunning, useTaskStore } from '@/stores/tasks';

// Chrome and Edge never animate SVG or GIF favicons; the only cross-browser
// technique is swapping the <link rel="icon"> href with canvas frames. Safari
// ignores dynamic favicon swaps entirely and simply keeps the static icon.
//
// The frames redraw app/icon.svg (champagne square, navy-gloss signature "M")
// from the same constants in lib/seo/config.ts, animating the stroke with a
// dash offset: the signature draws itself, holds, erases, then loops.
//
// The loop is a fixed set of frames, each drawn and PNG-encoded the first time
// it comes up and replayed from cache afterwards, so past the first cycle a
// tick is one string assignment. Encoding on every tick instead made the
// animation stutter on a busy main thread — exactly when a task is running.

/**
 * Drawn at 2x the 32px icon box: the browser downsamples this to the 16px
 * tab icon, and the extra resolution is what keeps the thin stroke from
 * looking ragged after that scale-down. Each doubling quadruples the encode
 * cost of a frame, and 64px is already twice the retina tab slot.
 */
const CANVAS_SIZE = 64;
const ICON_BOX = 32;
const ICON_RADIUS = 7;
/** Same offset icon.svg applies to center the 24-box monogram in the 32 box. */
const MONOGRAM_OFFSET = 4;
/** Vertical extent of the drawn stroke, mirroring the SVG gradient's span. */
const GRADIENT_TOP = 9;
const GRADIENT_BOTTOM = 23;

const CYCLE_MS = 2400;
/**
 * The cycle is quantised into this many cached frames. 20 fps reads as smooth
 * in a 16px tab and is about as fast as the tab strip repaints a swapped icon
 * anyway; a higher rate only spends encode time on frames the browser drops.
 */
const FRAME_COUNT = 48;
const FRAME_MS = CYCLE_MS / FRAME_COUNT;
/**
 * Ticks arrive twice per frame, so timer jitter — or a main thread busy with
 * the architect event stream — delays a frame instead of skipping it. A tick
 * landing on the frame already shown costs a single comparison.
 */
const TICK_MS = FRAME_MS / 2;

/** Measured ~57.8 in Chrome; used only if getTotalLength is unavailable. */
const FALLBACK_PATH_LENGTH = 58;

// Cycle phases, as fractions of CYCLE_MS. Erase runs to the cycle's end:
// its final frame and the next draw's first frame are both empty, so the
// loop closes seamlessly with no blank beat.
const DRAW_END = 0.42;
const HOLD_END = 0.58;

/** Pen-like pacing: the stroke starts gently, speeds up, then settles. */
function easeInOutCubic(p: number): number {
  return p < 0.5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2;
}

/**
 * Dash offset for the signature stroke at cycle position `t` in [0, 1).
 * With a dash pattern of [length, length], offset length→0 draws the stroke
 * from its start, and 0→-length erases it from the start while the tip stays.
 */
export function dashOffsetAt(t: number, pathLength: number): number {
  if (t < DRAW_END) return pathLength * (1 - easeInOutCubic(t / DRAW_END));
  if (t < HOLD_END) return 0;
  return -pathLength * easeInOutCubic((t - HOLD_END) / (1 - HOLD_END));
}

function measurePathLength(d: string): number {
  try {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    const length = path.getTotalLength();
    return Number.isFinite(length) && length > 0 ? length : FALLBACK_PATH_LENGTH;
  } catch {
    return FALLBACK_PATH_LENGTH;
  }
}

/**
 * Ticks `onTick` every `intervalMs`, returning a stop function. Main-thread
 * timers are clamped to >=1s in background tabs — which froze the animation
 * exactly where it matters most, the tab strip while the user is elsewhere.
 * Worker timers are exempt from that clamp, so the ticks come from an inline
 * worker; the main-thread interval is only a fallback (e.g. a CSP that blocks
 * blob workers), where the animation degrades to one frame per second.
 */
function startTicker(onTick: () => void, intervalMs: number): () => void {
  try {
    const source = `setInterval(() => postMessage(0), ${intervalMs});`;
    const url = URL.createObjectURL(
      new Blob([source], { type: 'text/javascript' }),
    );
    const worker = new Worker(url);
    URL.revokeObjectURL(url);
    worker.onmessage = onTick;
    return () => worker.terminate();
  } catch {
    const intervalId = window.setInterval(onTick, intervalMs);
    return () => window.clearInterval(intervalId);
  }
}

function ensureIconLink(): HTMLLinkElement {
  const existing = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
  if (existing) return existing;
  const link = document.createElement('link');
  link.rel = 'icon';
  link.href = '/icon.svg';
  document.head.appendChild(link);
  return link;
}

/**
 * Animates the favicon while a task is running — the signature monogram
 * draws and erases in a loop — and restores the static icon on any terminal
 * status. Renders nothing; mounted once in the (app) layout so marketing
 * pages keep the static favicon. Honors prefers-reduced-motion.
 */
export function TaskFavicon() {
  const running = useTaskStore((s) => isTaskRunning(s.status));

  useEffect(() => {
    if (!running) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const link = ensureIconLink();
    const originalHref = link.href;
    const originalType = link.getAttribute('type');

    const canvas = document.createElement('canvas');
    canvas.width = CANVAS_SIZE;
    canvas.height = CANVAS_SIZE;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const pathLength = measurePathLength(MONOGRAM_PATH);
    const monogram = new Path2D(MONOGRAM_PATH);
    // Gradient coordinates are read at stroke time, under the 2x transform.
    const gradient = ctx.createLinearGradient(0, GRADIENT_TOP, 0, GRADIENT_BOTTOM);
    gradient.addColorStop(0, MONOGRAM_GRADIENT[0]);
    gradient.addColorStop(0.5, MONOGRAM_GRADIENT[1]);
    gradient.addColorStop(1, MONOGRAM_GRADIENT[2]);
    const started = performance.now();

    /** Draws frame `index` of the cycle and returns it as a PNG data URL. */
    const renderFrame = (index: number): string => {
      const t = index / FRAME_COUNT;
      ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
      ctx.save();
      ctx.scale(CANVAS_SIZE / ICON_BOX, CANVAS_SIZE / ICON_BOX);
      ctx.beginPath();
      ctx.roundRect(0, 0, ICON_BOX, ICON_BOX, ICON_RADIUS);
      ctx.fillStyle = BRAND.primary;
      ctx.fill();
      ctx.translate(MONOGRAM_OFFSET, MONOGRAM_OFFSET);
      ctx.lineWidth = MONOGRAM_STROKE_WIDTH;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = gradient;
      ctx.setLineDash([pathLength, pathLength]);
      ctx.lineDashOffset = dashOffsetAt(t, pathLength);
      ctx.stroke(monogram);
      ctx.restore();
      return canvas.toDataURL('image/png');
    };

    const frames = new Array<string | undefined>(FRAME_COUNT);
    const frameAt = (index: number): string => {
      const cached = frames[index];
      if (cached !== undefined) return cached;
      const rendered = renderFrame(index);
      frames[index] = rendered;
      return rendered;
    };

    // The frame is derived from elapsed time rather than a tick count, so a
    // late tick resumes at the right point in the cycle instead of drifting.
    let shownIndex = -1;
    const showFrame = () => {
      const elapsed = (performance.now() - started) % CYCLE_MS;
      const index = Math.min(Math.floor(elapsed / FRAME_MS), FRAME_COUNT - 1);
      if (index === shownIndex) return;
      shownIndex = index;
      link.href = frameAt(index);
    };

    link.setAttribute('type', 'image/png');
    showFrame();
    const stopTicker = startTicker(showFrame, TICK_MS);
    return () => {
      stopTicker();
      if (originalType === null) link.removeAttribute('type');
      else link.setAttribute('type', originalType);
      link.href = originalHref;
    };
  }, [running]);

  return null;
}
