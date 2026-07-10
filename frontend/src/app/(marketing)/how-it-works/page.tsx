import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Reveal } from '@/components/effects/Reveal';
import { MarketingPage, PageHeader, SectionEyebrow } from '@/components/landing/MarketingSection';
import { buttonVariants } from '@/components/ui/Button';
import { FEATURES, PIPELINE } from '@/lib/marketing-content';
import { cn } from '@/lib/cn';
import { buildPageMetadata } from '@/lib/seo/metadata';

export const metadata = buildPageMetadata({
  title: 'How It Works',
  description:
    'One prompt, four layers: the orchestrator routes, a domain expert plans, subagents execute, the reviewer audits.',
  path: '/how-it-works',
});

export default function HowItWorksPage() {
  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ HOW IT WORKS ]"
        title="One prompt, four"
        titleAccent="layers"
        description="Tasks flow one way. The orchestrator routes, the main agent splits the work into subtasks, subagents execute them, and the reviewer optionally audits the result."
      />

      {/* Pipeline */}
      <section className="mt-16">
        <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-3 font-mono text-[11px]">
          {PIPELINE.map((stage, i) => (
            <div key={stage.label} className="flex items-center gap-2">
              <span
                className={cn(
                  'rounded border bg-surface/70 px-2.5 py-1 tracking-wide',
                  stage.optional
                    ? 'border-dashed border-border-bright text-muted'
                    : 'border-border text-slate-300',
                )}
              >
                {stage.label}
              </span>
              {i < PIPELINE.length - 1 && (
                <span className="text-primary/70" aria-hidden>
                  →
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-border bg-border">
          {PIPELINE.map((stage, i) => (
            <Reveal key={stage.label} delay={i * 0.05}>
              <div className="flex flex-col gap-1.5 bg-surface p-5 sm:flex-row sm:gap-6">
                <div className="flex shrink-0 items-baseline gap-3 sm:w-52">
                  <span className="font-mono text-xs text-primary/60">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h2 className="font-sans text-sm font-bold tracking-wide text-white">
                    {stage.label}
                  </h2>
                </div>
                <p className="font-mono text-xs leading-relaxed text-muted">
                  {stage.description}
                  {stage.optional && (
                    <span className="ml-1.5 text-primary/70">Optional — you toggle it.</span>
                  )}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="mt-20">
        <Reveal>
          <SectionEyebrow>[ FEATURES ]</SectionEyebrow>
          <h2 className="mt-3 font-sans text-2xl font-bold tracking-tight text-white">
            What you get
          </h2>
        </Reveal>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FEATURES.map((feature, i) => (
            <Reveal key={feature.title} delay={i * 0.05}>
              <div className="h-full rounded-lg border border-border bg-surface/50 p-5 transition-colors hover:border-border-bright">
                <feature.icon className="h-5 w-5 text-primary" aria-hidden />
                <h3 className="mt-3 font-sans text-base font-bold text-white">
                  {feature.title}
                </h3>
                <p className="mt-1.5 font-mono text-xs leading-relaxed text-muted">
                  {feature.description}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Guardrails */}
      <Reveal className="mt-20">
        <div className="rounded-lg border border-border bg-surface/50 p-6 text-center">
          <SectionEyebrow>[ GUARDRAILS ]</SectionEyebrow>
          <p className="mx-auto mt-3 max-w-2xl font-mono text-xs leading-relaxed text-muted">
            Every loop is bounded. Subagents stop at{' '}
            <code className="text-slate-300">max_iterations</code>, the review cycle at{' '}
            <code className="text-slate-300">max_review_iterations</code>, and the task
            as a whole at <code className="text-slate-300">task_timeout_seconds</code>. A
            task that hits a limit halts, tells you why, and still accounts for the
            tokens it spent.
          </p>
        </div>
      </Reveal>

      <div className="mt-14 flex justify-center">
        <Link
          href="/templates"
          className={cn(buttonVariants({ variant: 'lime' }), 'gap-1.5 px-6 py-2.5')}
        >
          Browse agent templates
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </MarketingPage>
  );
}
