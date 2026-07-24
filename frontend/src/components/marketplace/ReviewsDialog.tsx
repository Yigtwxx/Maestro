'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Textarea } from '@/components/ui/Textarea';
import { RatingPicker, RatingStars } from '@/components/marketplace/RatingStars';
import type { ReportTarget } from '@/components/marketplace/ReportModal';
import { api, ApiError } from '@/lib/api';
import { REVIEWS_PAGE_SIZE } from '@/lib/constants';
import { formatDate, useTimeZone } from '@/lib/date';
import { toast } from '@/stores/toast';
import type { MarketplaceItem, MarketplaceReview } from '@/types';

interface ReviewsDialogProps {
  item: MarketplaceItem;
  onClose: () => void;
  /** Fired after a successful submit so the grid can refresh its aggregates. */
  onReviewed: () => void;
  /** Open the report dialog for a specific review. */
  onReport: (target: ReportTarget) => void;
}

/** Review list + "your review" form for one marketplace item. */
export function ReviewsDialog({ item, onClose, onReviewed, onReport }: ReviewsDialogProps) {
  const [reviews, setReviews] = useState<MarketplaceReview[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [saving, setSaving] = useState(false);
  const tz = useTimeZone();

  const load = useCallback(
    async (offset: number) => {
      try {
        const page = await api.listReviews(item.id, REVIEWS_PAGE_SIZE, offset);
        setTotal(page.total);
        setReviews((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
        if (offset === 0 && page.my_review) {
          setRating(page.my_review.rating);
          setComment(page.my_review.comment ?? '');
        }
      } catch (err) {
        toast.error(
          err instanceof ApiError ? err.message : 'Reviews could not be loaded.',
        );
      } finally {
        setLoading(false);
      }
    },
    [item.id],
  );

  useEffect(() => {
    void load(0);
  }, [load]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating === 0) {
      toast.error('Pick a star rating first.');
      return;
    }
    setSaving(true);
    try {
      await api.submitReview(item.id, {
        rating,
        comment: comment.trim() || undefined,
      });
      toast.success('Review saved.');
      onReviewed();
      await load(0);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Review could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} label={`Reviews for ${item.name}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-micro text-module-marketplace">[ REVIEWS ]</p>
          <h2 className="mt-1 text-lg font-bold text-white">{item.name}</h2>
        </div>
        {item.rating_count > 0 && (
          <span className="flex items-center gap-1.5 pt-1">
            <RatingStars value={item.rating_avg ?? 0} />
            <span className="text-xs text-muted">({item.rating_count})</span>
          </span>
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="mb-5 rounded-md border border-border bg-surface-2 p-4"
      >
        <p className="text-micro mb-2 text-module-marketplace">[ YOUR REVIEW ]</p>
        <RatingPicker value={rating} onChange={setRating} className="mb-3" />
        <Textarea
          label="Comment (optional)"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          module="marketplace"
        />
        <div className="mt-3">
          <Button type="submit" variant="solid" module="marketplace" loading={saving}>
            Save review
          </Button>
        </div>
      </form>

      {loading ? (
        <p className="font-mono text-sm text-module-marketplace">
          &gt; LOADING REVIEWS<span className="animate-blink">_</span>
        </p>
      ) : reviews.length === 0 ? (
        <p className="text-sm text-muted">&gt; No reviews yet. Be the first.</p>
      ) : (
        <ul className="grid gap-3">
          {reviews.map((review, index) => (
            <li
              key={review.id ?? `${review.updated_at}-${index}`}
              className="rounded-md border border-border p-3"
            >
              <div className="flex items-center justify-between">
                <RatingStars value={review.rating} />
                <span className="text-xs text-muted/70">
                  {review.is_own ? 'You' : 'Community member'} ·{' '}
                  {formatDate(review.updated_at, tz)}
                </span>
              </div>
              {review.comment && (
                <p className="mt-2 text-sm text-muted">{review.comment}</p>
              )}
              {!review.is_own && (
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() =>
                      onReport({
                        kind: 'review',
                        id: review.id,
                        label: review.comment ?? `${review.rating}-star review`,
                      })
                    }
                    className="text-[10px] text-muted hover:text-module-admin"
                  >
                    Report
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!loading && reviews.length < total && (
        <div className="mt-4 text-center">
          <Button variant="ghost" onClick={() => void load(reviews.length)}>
            Load more ({total - reviews.length} left)
          </Button>
        </div>
      )}
    </Modal>
  );
}
