import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';

export function StubPage({
  title,
  description,
  roadmap,
  module,
}: {
  title: string;
  description: string;
  roadmap: string[];
  /** Neon hue of the owning module (brand lime fallback). */
  module?: ModuleKey;
}) {
  const mc = moduleColor(module);
  return (
    <div className="mx-auto max-w-4xl px-6 pt-5 pb-8">
      <Card module={module ?? 'brand'}>
        <p className={`text-micro mb-2 ${mc.text}`}>[ MODULE: PLANNED ]</p>
        <h1 className="text-sm font-bold text-white">{title}</h1>
        <p className="mt-1 mb-4 text-sm text-muted">{description}</p>
        <div className="mb-4 flex items-center gap-3">
          <Badge tone="gray">PENDING</Badge>
          <p className="text-sm text-muted">
            This module will be enabled in upcoming development rounds.
          </p>
        </div>
        <ul className="space-y-2 font-mono text-sm">
          {roadmap.map((item) => (
            <li key={item} className="flex items-start gap-2 text-slate-300">
              <span className={`shrink-0 ${mc.text}`}>&gt;</span>
              {item}
            </li>
          ))}
        </ul>
        <p className={`mt-4 font-mono text-sm ${mc.text}`}>
          &gt;<span className="animate-blink">_</span>
        </p>
      </Card>
    </div>
  );
}
