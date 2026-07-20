'use client';

import { useCallback, useEffect, useState } from 'react';
import { Boxes } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Textarea';
import { Sparkline } from '@/components/ui/Sparkline';
import { StatBlock } from '@/components/ui/StatBlock';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { PageShell } from '@/components/layout/PageShell';
import { RatingStars } from '@/components/marketplace/RatingStars';
import { ReviewsDialog } from '@/components/marketplace/ReviewsDialog';
import { ReportModal, type ReportTarget } from '@/components/marketplace/ReportModal';
import { api, ApiError } from '@/lib/api';
import { AGENT_DOMAINS } from '@/lib/constants';
import { domainColor } from '@/lib/agent-colors';
import { toast } from '@/stores/toast';
import type { MarketplaceItem } from '@/types';

export default function MarketplacePage() {
  const [items, setItems] = useState<MarketplaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [message, setMessage] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [domain, setDomain] = useState('general');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [saving, setSaving] = useState(false);
  const [reviewItem, setReviewItem] = useState<MarketplaceItem | undefined>();
  const [reportTarget, setReportTarget] = useState<ReportTarget | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.listMarketplace());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Marketplace could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onPublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setMessage(undefined);
    setSaving(true);
    try {
      await api.publishMarketplace({
        name,
        description,
        domain,
        system_prompt: systemPrompt,
        tools: [],
      });
      setName('');
      setDescription('');
      setSystemPrompt('');
      setPublishing(false);
      setMessage('Agent team published (passed the security scan).');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Publish failed.');
    } finally {
      setSaving(false);
    }
  };

  // Aggregate refresh after a review: cosmetic, so a failure keeps the stale
  // numbers instead of surfacing an error inside the open dialog.
  const refresh = useCallback(async () => {
    try {
      setItems(await api.listMarketplace());
    } catch {
      /* keep the stale aggregates */
    }
  }, []);

  // The Deploy button sits at the bottom of a card, far from the page-top
  // banner, so a toast is the feedback the user will actually see.
  const onInstall = async (id: string) => {
    try {
      await api.installMarketplace(id);
      toast.success('Agent team installed as a custom agent.');
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Install failed.');
    }
  };

  return (
    <PageShell>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-micro text-module-marketplace">[ MARKETPLACE ]</p>
        <Button
          variant={publishing ? 'ghost' : 'solid'}
          module={publishing ? undefined : 'marketplace'}
          onClick={() => setPublishing((v) => !v)}
        >
          {publishing ? 'Close' : '+ Publish'}
        </Button>
      </div>

      {message && (
        <p className="mb-4 animate-word-in rounded-md border border-module-marketplace/30 bg-module-marketplace/10 px-4 py-2 text-sm text-module-marketplace motion-reduce:animate-none">
          &gt; {message}
        </p>
      )}
      {error && <p className="mb-4 text-sm text-danger">&gt; ERROR: {error}</p>}

      {publishing && (
        <Card module="marketplace" featured className="mb-8">
          <p className="text-micro mb-1 text-module-marketplace">[ PUBLISH NEW TEAM ]</p>
          <form onSubmit={onPublish} className="mt-3 grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Team Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                module="marketplace"
              />
              <Select
                label="Domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                options={AGENT_DOMAINS.map((d) => ({ value: d, label: d }))}
                module="marketplace"
              />
            </div>
            <Input
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              module="marketplace"
            />
            <div>
              <Textarea
                label="System Prompt"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={5}
                required
                module="marketplace"
              />
              <p className="mt-1.5 text-xs text-muted/70">
                Passes a mandatory security scan before publishing.
              </p>
            </div>
            <div>
              <Button type="submit" variant="solid" module="marketplace" loading={saving}>
                Publish
              </Button>
            </div>
          </form>
        </Card>
      )}

      {loading ? (
        <>
          <p className="font-mono text-sm text-module-marketplace">
            &gt; LOADING MARKETPLACE<span className="animate-blink">_</span>
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <SkeletonCard key={i} module="marketplace" />
            ))}
          </div>
        </>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">
          &gt; No agent teams published yet. Be the first to publish one.
        </p>
      ) : (
        <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => {
            const dc = domainColor(item.domain);
            return (
              <StaggerItem key={item.id} className="h-full">
              <Card glow domain={item.domain} className="flex h-full flex-col p-5">
                <CardHeader
                  icon={<Boxes className={`h-5 w-5 ${dc.text}`} />}
                  className="items-start justify-between"
                >
                  <CardTitle className="flex-1 text-base">{item.name}</CardTitle>
                  <Badge domain={item.domain} className="capitalize">
                    {item.domain}
                  </Badge>
                </CardHeader>
                {/* The clamp needs its own element: a flex item is blockified,
                    which turns `-webkit-box` into `flow-root` and kills it. */}
                <div className="mb-4 flex-1">
                  <p className="line-clamp-3 text-sm text-muted">{item.description}</p>
                </div>
                <div className="mb-4 rounded-md border border-border bg-surface-2 p-3">
                  <div className="grid grid-cols-2 gap-3">
                    <StatBlock size="sm" label="Installs" value={item.installs} />
                    <div className="flex items-end justify-end">
                      {item.install_history ? (
                        <Sparkline
                          values={item.install_history}
                          hex={dc.accentHex}
                          className="h-6 w-16 opacity-70"
                        />
                      ) : (
                        <span className="text-[10px] text-muted/60">no trend yet</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
                    {item.rating_count > 0 ? (
                      <span className="flex items-center gap-1.5">
                        <RatingStars value={item.rating_avg ?? 0} />
                        <span className="text-[10px] text-muted/60">
                          ({item.rating_count})
                        </span>
                      </span>
                    ) : (
                      <span className="text-[10px] text-muted/60">no ratings yet</span>
                    )}
                    <span className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() =>
                          setReportTarget({
                            kind: 'item',
                            id: item.id,
                            label: item.name,
                          })
                        }
                        className="text-[10px] text-muted hover:text-module-admin"
                      >
                        Report
                      </button>
                      <button
                        type="button"
                        onClick={() => setReviewItem(item)}
                        className="text-[10px] text-module-marketplace hover:underline"
                      >
                        Reviews
                      </button>
                    </span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <Badge tone="cyan" dot>
                    Ready
                  </Badge>
                  <Button variant="outline" module="marketplace" onClick={() => onInstall(item.id)}>
                    Deploy
                  </Button>
                </div>
              </Card>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}

      {reviewItem && (
        <ReviewsDialog
          item={reviewItem}
          onClose={() => setReviewItem(undefined)}
          onReviewed={() => void refresh()}
          onReport={setReportTarget}
        />
      )}

      <ReportModal target={reportTarget} onClose={() => setReportTarget(undefined)} />
    </PageShell>
  );
}
