'use client';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { formatDateTime, relativeTime, useTimeZone } from '@/lib/date';
import type { TaskSummary } from '@/types';

interface TaskDetailModalProps {
  /** The rail dot that was clicked; undefined renders nothing. */
  task: TaskSummary | undefined;
  onClose: () => void;
  onOpenInCanvas: (taskId: string) => void;
  onDelete: (taskId: string) => void;
}

/**
 * Detail for one task history dot. Reads only the summary the rail already
 * holds — no extra fetch — so the dialog opens instantly.
 */
export function TaskDetailModal({
  task,
  onClose,
  onOpenInCanvas,
  onDelete,
}: TaskDetailModalProps) {
  const timeZone = useTimeZone();
  if (!task) return null;

  return (
    <Modal open onClose={onClose} label="Task detail">
      <div className="flex flex-wrap items-center gap-3">
        <Badge status={task.status} />
        {task.domain && <Badge domain={task.domain} />}
        <span className="text-micro ml-auto text-muted">
          {relativeTime(task.created_at)}
        </span>
      </div>

      <p className="mt-1 text-sm text-muted">
        {formatDateTime(task.created_at, timeZone)}
      </p>

      {/* Server-side preview: task_service truncates the prompt at 140 chars. */}
      <p className="mt-4 whitespace-pre-wrap rounded border border-border bg-surface-2 p-3 font-mono text-sm text-slate-200">
        {task.prompt}
      </p>

      {task.error && (
        <p className="mt-3 rounded border border-danger/40 bg-danger-dim p-3 text-sm text-danger">
          {task.error}
        </p>
      )}

      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <Button
          variant="danger-outline"
          onClick={() => {
            onDelete(task.task_id);
            onClose();
          }}
        >
          Delete
        </Button>
        <Button
          variant="solid"
          module="architect"
          onClick={() => {
            onOpenInCanvas(task.task_id);
            onClose();
          }}
        >
          Open in canvas
        </Button>
      </div>
    </Modal>
  );
}
