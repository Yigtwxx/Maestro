import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeSlug from 'rehype-slug';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/cn';
import { normalizeMarkdownTables } from '@/lib/markdown-tables';
import { remarkUncertainty } from '@/lib/uncertainty';

/** Same-origin links (`/privacy`, `#section`) must not open a new tab. */
function isInternalHref(href: string | undefined): boolean {
  return href !== undefined && (href.startsWith('/') || href.startsWith('#'));
}

const markdownComponents: Components = {
  h1: ({ className, ...props }) => (
    <h1 className={cn('mb-2 mt-4 text-lg font-semibold text-slate-100 first:mt-0', className)} {...props} />
  ),
  h2: ({ className, ...props }) => (
    <h2 className={cn('mb-2 mt-4 text-base font-semibold text-slate-100 first:mt-0', className)} {...props} />
  ),
  h3: ({ className, ...props }) => (
    <h3 className={cn('mb-1.5 mt-3 text-sm font-semibold text-slate-100 first:mt-0', className)} {...props} />
  ),
  h4: ({ className, ...props }) => (
    <h4 className={cn('mb-1 mt-3 text-sm font-medium text-slate-100 first:mt-0', className)} {...props} />
  ),
  p: ({ className, ...props }) => (
    <p className={cn('text-sm leading-relaxed text-slate-200 [&:not(:first-child)]:mt-2', className)} {...props} />
  ),
  ul: ({ className, ...props }) => (
    <ul className={cn('mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200', className)} {...props} />
  ),
  ol: ({ className, ...props }) => (
    <ol className={cn('mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-200', className)} {...props} />
  ),
  li: ({ className, ...props }) => <li className={cn('leading-relaxed', className)} {...props} />,
  strong: ({ className, ...props }) => (
    <strong className={cn('font-semibold text-white', className)} {...props} />
  ),
  em: ({ className, ...props }) => <em className={cn('italic', className)} {...props} />,
  a: ({ className, href, ...props }) => {
    const internal = isInternalHref(href);
    return (
      <a
        className={cn('text-accent underline underline-offset-2 hover:text-accent/80', className)}
        href={href}
        target={internal ? undefined : '_blank'}
        rel={internal ? undefined : 'noopener noreferrer'}
        {...props}
      />
    );
  },
  code: ({ className, ...props }) => (
    <code
      className={cn(
        'rounded border border-border bg-surface-2 px-1 py-0.5 font-mono text-xs text-primary',
        className,
      )}
      {...props}
    />
  ),
  // The `code` renderer above styles inline spans. Inside a `pre` it would draw
  // a bordered box around every wrapped line, so strip its chrome back off.
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        'mt-2 overflow-x-auto rounded-md border border-border bg-surface-2 p-3 font-mono text-xs text-slate-200',
        '[&>code]:border-0 [&>code]:bg-transparent [&>code]:p-0',
        className,
      )}
      {...props}
    />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn('mt-2 border-l-2 border-border-bright pl-3 italic text-muted', className)}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => <hr className={cn('my-3 border-border', className)} {...props} />,
  // Wrapped so a wide table scrolls itself instead of the page body.
  table: ({ className, ...props }) => (
    <div className="mt-2 overflow-x-auto">
      <table className={cn('w-full border-collapse text-sm text-slate-200', className)} {...props} />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th className={cn('border border-border bg-surface-2 px-2 py-1 text-left font-semibold', className)} {...props} />
  ),
  td: ({ className, ...props }) => (
    <td className={cn('border border-border px-2 py-1', className)} {...props} />
  ),
  // Only `remarkUncertainty` produces <mark>: an agent's own markdown reaches
  // this renderer as text, and raw HTML is disabled. Amber-300 is already the
  // "not yet verified" colour in Badge's `needs_review`, and the trailing "(?)"
  // carries the same meaning without relying on colour alone. Full literal
  // classes — Tailwind cannot see a class name built at runtime.
  mark: ({ className, children, ...props }) => (
    <mark
      className={cn(
        'rounded bg-amber-400/10 px-1 text-amber-300 [box-decoration-break:clone]',
        className,
      )}
      title="The agent flagged this as inferred, not sourced"
      {...props}
    >
      {children}
      <span className="ml-0.5 font-semibold">(?)</span>
    </mark>
  ),
};

interface MarkdownProps {
  content: string;
  className?: string;
  /**
   * Highlight the agent's `[? ... ?]` grounding markers. Off by default so the
   * docs and legal pages, which share this renderer, are untouched.
   */
  markUncertainty?: boolean;
  /**
   * Also highlight a marker whose closing `?]` has not arrived yet. Only for
   * the streaming preview, where the text is still being written.
   */
  streaming?: boolean;
}

export function Markdown({ content, className, markUncertainty, streaming }: MarkdownProps) {
  // Built inline rather than memoized: this component is also rendered from
  // server components (docs, legal), so it must stay hook-free.
  const remarkPlugins = markUncertainty
    ? [remarkGfm, remarkUncertainty({ tolerateOpen: streaming })]
    : [remarkGfm];

  return (
    <div className={cn('break-words', className)}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={[rehypeSlug]}
        components={markdownComponents}
      >
        {normalizeMarkdownTables(content)}
      </ReactMarkdown>
    </div>
  );
}
