import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('privacy');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function PrivacyPage() {
  return <LegalDocument doc={doc} title="Privacy" titleAccent="Policy" />;
}
