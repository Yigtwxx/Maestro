import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { GradientText } from '@/components/effects/GradientText';
import { Reveal } from '@/components/effects/Reveal';

/** Uppercase, bracketed section label. Lime by default; pass a module hue class. */
export function SectionEyebrow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn('text-micro text-primary', className)}>{children}</span>;
}

interface PageHeaderProps {
  eyebrow: string;
  /** Plain leading words of the title. */
  title: string;
  /** Trailing words carrying the brand gradient sweep. */
  titleAccent?: string;
  description: string;
  /** Tints the eyebrow (e.g. `text-module-marketplace`). Defaults to lime. */
  eyebrowClassName?: string;
  children?: ReactNode;
}

/** The hero block every marketing tab opens with. */
export function PageHeader({
  eyebrow,
  title,
  titleAccent,
  description,
  eyebrowClassName,
  children,
}: PageHeaderProps) {
  return (
    <Reveal onMount className="mx-auto max-w-3xl text-center">
      <SectionEyebrow className={eyebrowClassName}>{eyebrow}</SectionEyebrow>
      <h1 className="mt-3 font-sans text-3xl font-bold tracking-tight text-white sm:text-4xl">
        {title}
        {titleAccent && (
          <>
            {' '}
            <GradientText>{titleAccent}</GradientText>
          </>
        )}
      </h1>
      <p className="mx-auto mt-4 max-w-xl font-mono text-sm leading-relaxed text-muted">
        {description}
      </p>
      {children && <div className="mt-8 flex justify-center">{children}</div>}
    </Reveal>
  );
}

/** Standard vertical rhythm + max width for a marketing tab's content. */
export function MarketingPage({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mx-auto max-w-5xl px-5 py-16 sm:px-8 sm:py-20', className)}>
      {children}
    </div>
  );
}
