'use client';

import { useCallback, useEffect, useState } from 'react';
import { CreditCard, Receipt } from 'lucide-react';
import { CardForm } from '@/components/billing/CardForm';
import { CardBrandLogo } from '@/components/billing/CardBrandLogos';
import { PlanGrid } from '@/components/billing/PlanGrid';
import { QuotaMeter } from '@/components/billing/QuotaMeter';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { PageShell } from '@/components/layout/PageShell';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import { useAuthStore } from '@/stores/auth';
import type { CardInput, PlanPublic, SubscriptionPlan, SubscriptionPublic } from '@/types';

const mc = MODULE_COLOR.billing;

export default function BillingPage() {
  const refreshUser = useAuthStore((s) => s.refreshUser);

  const [subscription, setSubscription] = useState<SubscriptionPublic | undefined>();
  const [plans, setPlans] = useState<PlanPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionPlan | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    try {
      // A fresh account holds no subscription (there is no trial): the endpoint
      // 404s, which is a normal "not subscribed yet" state, not an error. The
      // plan grid below is exactly how the user subscribes.
      const [nextSubscription, nextPlans] = await Promise.all([
        api.getSubscription().catch((err) => {
          if (err instanceof ApiError && err.status === 404) return undefined;
          throw err;
        }),
        api.getPlans(),
      ]);
      setSubscription(nextSubscription);
      setPlans(nextPlans);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Billing could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSubscribe = async (card: CardInput) => {
    if (!selectedPlan) return;
    setError(undefined);
    setSubmitting(true);
    try {
      setSubscription(await api.subscribe(selectedPlan, card));
      setSelectedPlan(undefined);
      // The plan gates the UI elsewhere, so refresh the cached user tier too.
      await Promise.all([refreshUser(), load()]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The payment could not be processed.');
    } finally {
      setSubmitting(false);
    }
  };

  const onCancel = async () => {
    setError(undefined);
    setCancelling(true);
    try {
      setSubscription(await api.cancelSubscription());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The plan could not be cancelled.');
    } finally {
      setCancelling(false);
    }
  };

  if (loading) {
    return (
      <PageShell className="space-y-6">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageShell>
    );
  }

  const paymentMethod = subscription?.payment_method;
  const canCancel =
    subscription !== undefined &&
    subscription.status === 'active' &&
    !subscription.cancel_at_period_end;

  return (
    <PageShell>
      <div className="space-y-6">
        {subscription && <QuotaMeter subscription={subscription} />}

        <Card module="billing">
          <CardHeader icon={<Receipt className="h-5 w-5" />} module="billing">
            <CardTitle>Plans</CardTitle>
          </CardHeader>
          {!subscription && (
            <p className={`text-micro mb-4 ${mc.text}`}>
              [ SUBSCRIBE TO A PLAN TO START RUNNING TASKS ]
            </p>
          )}
          <PlanGrid
            plans={plans}
            currentPlan={subscription?.plan}
            selectedPlan={selectedPlan}
            onSelect={setSelectedPlan}
          />
        </Card>

        {selectedPlan && (
          <Card module="billing">
            <CardHeader icon={<CreditCard className="h-5 w-5" />} module="billing">
              <CardTitle>Payment details</CardTitle>
            </CardHeader>
            <CardForm
              submitLabel={`Subscribe to ${selectedPlan}`}
              submitting={submitting}
              onSubmit={(card) => void onSubscribe(card)}
            />
          </Card>
        )}

        {paymentMethod && !selectedPlan && (
          <Card module="billing">
            <CardHeader icon={<CreditCard className="h-5 w-5" />} module="billing">
              <CardTitle>Payment method</CardTitle>
            </CardHeader>
            <div className="flex items-center gap-3">
              <span className="text-white">
                <CardBrandLogo brand={paymentMethod.brand} />
              </span>
              <p className="font-mono text-sm text-muted">
                •••• {paymentMethod.last4} — expires{' '}
                {String(paymentMethod.exp_month).padStart(2, '0')}/{paymentMethod.exp_year}
              </p>
            </div>
            {canCancel && (
              <div className="mt-4 border-t border-border pt-4">
                <p className="mb-2 text-xs text-muted">
                  Cancelling stops renewal. Your plan stays usable until the period ends.
                </p>
                <Button
                  variant="danger-outline"
                  loading={cancelling}
                  onClick={() => void onCancel()}
                >
                  Cancel subscription
                </Button>
              </div>
            )}
          </Card>
        )}

        {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
      </div>
    </PageShell>
  );
}
