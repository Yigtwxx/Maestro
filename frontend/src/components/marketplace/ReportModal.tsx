'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { ReportReason } from '@/types';

/** What is being flagged. `label` is a short human hint shown in the dialog. */
export interface ReportTarget {
  kind: 'item' | 'review';
  id: string;
  label: string;
}

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'spam', label: 'Spam' },
  { value: 'abuse', label: 'Abuse or harassment' },
  { value: 'malicious', label: 'Malicious / unsafe content' },
  { value: 'other', label: 'Other' },
];

/** Report an item or review for moderator review. Renders nothing when closed. */
export function ReportModal({
  target,
  onClose,
}: {
  target: ReportTarget | undefined;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<ReportReason>('spam');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  if (!target) return undefined;

  const submit = async () => {
    setSaving(true);
    try {
      const input = { reason, note: note.trim() || undefined };
      if (target.kind === 'item') {
        await api.reportItem(target.id, input);
      } else {
        await api.reportReview(target.id, input);
      }
      toast.success('Report submitted for review. Thank you.');
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Report failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} label={`Report ${target.kind}`}>
      <p className="text-micro text-module-admin">[ REPORT {target.kind.toUpperCase()} ]</p>
      <p className="mt-1 mb-4 truncate text-sm text-white">{target.label}</p>
      <Select
        label="Reason"
        value={reason}
        onChange={(e) => setReason(e.target.value as ReportReason)}
        options={REASONS}
        className="mb-4"
      />
      <Textarea
        label="Details (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        className="mb-4"
      />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="danger-outline" loading={saving} onClick={() => void submit()}>
          Submit report
        </Button>
      </div>
    </Modal>
  );
}
