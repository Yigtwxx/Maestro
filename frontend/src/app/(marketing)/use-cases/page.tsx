import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Reveal } from '@/components/effects/Reveal';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { buttonVariants } from '@/components/ui/Button';
import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import { domainColor } from '@/lib/agent-colors';
import { AGENT_LOCALE_TR } from '@/lib/agent-locale';
import { USE_CASES } from '@/lib/marketing-content';
import { cn } from '@/lib/cn';
import { buildPageMetadata } from '@/lib/seo/metadata';

export const metadata = buildPageMetadata({
  title: 'Use Cases',
  description:
    'Ten expert domains, each with its own fixed team of specialist subagents. See what they are for.',
  path: '/use-cases',
});

export default function UseCasesPage() {
  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ USE CASES ]"
        title="Ten domains, one"
        titleAccent="orchestrator"
        description="Each domain is a main agent with a fixed team of specialist subagents. The orchestrator picks the right one from your prompt — you never have to."
      />

      <div className="mt-16 grid gap-4 sm:grid-cols-2">
        {USE_CASES.map((useCase, i) => {
          const dc = domainColor(useCase.domain);
          const expert = AGENT_LOCALE_TR[useCase.domain];
          return (
            <Reveal key={useCase.domain} delay={(i % 2) * 0.05}>
              <Card domain={useCase.domain} className="flex h-full flex-col p-5">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <h2 className="font-sans text-base font-bold text-white">
                    {useCase.title}
                  </h2>
                  <Badge domain={useCase.domain} className="shrink-0 capitalize">
                    {useCase.domain}
                  </Badge>
                </div>

                <p className="font-mono text-xs leading-relaxed text-muted">
                  {useCase.description}
                </p>

                <ul className="mt-4 flex-1 space-y-2">
                  {useCase.examples.map((example) => (
                    <li
                      key={example}
                      className="flex gap-2 font-mono text-xs leading-relaxed text-slate-400"
                    >
                      <span className={cn('select-none', dc.text)} aria-hidden>
                        &gt;
                      </span>
                      <span>{example}</span>
                    </li>
                  ))}
                </ul>

                {expert && (
                  <p className="mt-4 border-t border-border pt-3 font-mono text-[11px] text-muted/70">
                    Run by the {expert.name}, with{' '}
                    {Object.keys(expert.team).length} specialist subagents.
                  </p>
                )}
              </Card>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-14 flex justify-center">
        <Link
          href="/register"
          className={cn(buttonVariants({ variant: 'lime' }), 'gap-1.5 px-6 py-2.5')}
        >
          Start for free
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </MarketingPage>
  );
}
