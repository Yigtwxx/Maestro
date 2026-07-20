import { ConsentManager } from '@/components/legal/ConsentManager';
import { LegalDocument } from '@/components/legal/LegalDocument';
import { umamiWebsiteId } from '@/lib/analytics/config';
import { legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('cookies');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function CookiesPage() {
  // Request-time read (the root layout's connection() makes every page
  // dynamic); tells the consent manager whether there is anything to manage.
  const analyticsAvailable = umamiWebsiteId() !== undefined;

  return (
    <LegalDocument doc={doc} title="Cookie" titleAccent="Policy">
      <ConsentManager analyticsAvailable={analyticsAvailable} />
    </LegalDocument>
  );
}
