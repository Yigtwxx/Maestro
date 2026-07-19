'use client';

import dynamic from 'next/dynamic';
import DecryptedText from '@/components/DecryptedText';
import { ShinyText } from '@/components/effects/ShinyText';

// WebGL aurora curtain is decorative and client-only — keep it out of the
// initial bundle so the form paints immediately.
const Aurora = dynamic(() => import('@/components/Aurora'), { ssr: false });

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div className="absolute inset-0 opacity-60" aria-hidden>
        {/* Brand ramp: navy -> blue -> white -> champagne -> yellow. */}
        <Aurora
          colorStops={['#1a2b6d', '#3b9dff', '#ffffff', '#d3cbc0', '#ffd54a']}
          amplitude={1.0}
          blend={0.6}
          speed={0.6}
        />
      </div>
      {/* Terminal power-on: corner labels flicker in after the wordmark starts. */}
      <p
        className="text-micro absolute left-6 top-5 text-muted animate-word-in motion-reduce:animate-none"
        style={{ animationDelay: '0.25s' }}
      >
        MAESTRO <span className="text-border-bright">/</span> TERMINAL_V1
      </p>
      <p
        className="text-micro absolute right-6 top-5 animate-word-in motion-reduce:animate-none"
        style={{ animationDelay: '0.3s' }}
      >
        <ShinyText color="#d3cbc0" speed={4}>
          [ STATUS: ONLINE ]
        </ShinyText>
      </p>
      <div className="relative w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <span
            className="flex h-12 w-12 items-center justify-center rounded bg-primary font-sans text-2xl font-bold text-black animate-word-in motion-reduce:animate-none"
            aria-hidden
          >
            M
          </span>
          <div>
            <h1 className="font-sans text-2xl font-bold tracking-wide text-white">
              <DecryptedText
                text="MAESTRO"
                animateOn="view"
                sequential
                speed={80}
                encryptedClassName="text-primary/60"
              />
            </h1>
            <p
              className="text-micro mt-1 text-primary animate-word-in motion-reduce:animate-none"
              style={{ animationDelay: '0.2s' }}
            >
              AI OS v0.2 — ORCHESTRATION LAYER
            </p>
          </div>
        </div>
        <div
          className="animate-word-in motion-reduce:animate-none"
          style={{ animationDelay: '0.35s' }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
