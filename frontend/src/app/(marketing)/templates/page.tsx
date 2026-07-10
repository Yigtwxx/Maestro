import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import { api } from '@/lib/api';
import { buildPageMetadata } from '@/lib/seo/metadata';
import type { MarketplaceItemPreview } from '@/types';
import { ShowcaseGrid } from './ShowcaseGrid';

export const metadata = buildPageMetadata({
  title: 'Agent Templates',
  description:
    'Ready-made agent teams from Maestro and the community. Install one in a click, or publish your own.',
  path: '/templates',
});

// The showcase reflects what the community has just published, so it is read on
// every request rather than baked into the build — which also keeps `next build`
// working when the API is not running.
export const dynamic = 'force-dynamic';

export default async function TemplatesPage() {
  let items: MarketplaceItemPreview[] = [];
  let unreachable = false;

  try {
    items = await api.listShowcase();
  } catch {
    // The rest of the page is static copy; render it rather than erroring out.
    unreachable = true;
  }

  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ AGENT TEMPLATES ]"
        title="Agent teams, ready to"
        titleAccent="deploy"
        description="Every team below is a main agent and its specialist subagents, already briefed. Install one in a click, then edit its system prompt to taste."
        eyebrowClassName="text-module-marketplace"
      />

      {unreachable ? (
        <p className="mt-16 text-center font-mono text-sm text-muted">
          &gt; The template catalog is unreachable right now. Please try again shortly.
        </p>
      ) : (
        <ShowcaseGrid items={items} />
      )}
    </MarketingPage>
  );
}
