// Task session store (Zustand). Survives page navigation, which App Router
// remounts (see app/(app)/template.tsx), so a task's events and answer no
// longer vanish when the user leaves the architect page.
//
// Only the active task id is persisted to localStorage; events are refetched
// from the server, which is their source of truth (task_sessions in MongoDB).

import { create, type StoreApi } from 'zustand';
import { api, ApiError } from '@/lib/api';
import {
  ACTIVE_TASK_KEY,
  TERMINAL_EVENT_TYPES,
  TERMINAL_STATUSES,
} from '@/lib/constants';
import { openTaskStream, type TaskStreamHandle } from '@/lib/ws';
import { toast } from '@/stores/toast';
import type { AgentEvent, TaskStatus, TaskSummary } from '@/types';

type StartTaskInput = Parameters<typeof api.startTask>[0];

const EXPIRED_TASK_MESSAGE =
  'This task passed its retention window and was deleted.';

/** A task still emits events until it reaches a terminal status. */
export function isTaskRunning(status: TaskStatus | undefined): boolean {
  return status !== undefined && !TERMINAL_STATUSES.has(status);
}

function readActiveTaskId(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  return window.localStorage.getItem(ACTIVE_TASK_KEY) ?? undefined;
}

function persistActiveTaskId(taskId: string | undefined): void {
  if (typeof window === 'undefined') return;
  if (taskId) window.localStorage.setItem(ACTIVE_TASK_KEY, taskId);
  else window.localStorage.removeItem(ACTIVE_TASK_KEY);
}

interface TaskStoreState {
  activeTaskId: string | undefined;
  events: AgentEvent[];
  status: TaskStatus | undefined;
  answer: string | undefined;
  error: string | undefined;
  question: string | undefined;
  /** Rows delivered in bulk (snapshot/replay); EventLog skips their animation. */
  staticEventCount: number;
  /** Restored per task so a reopened session redraws its reviewer node. */
  reviewerEnabled: boolean;
  history: TaskSummary[];
  historyLoading: boolean;

  /** Live socket for the active task, and the guard against stale writes. */
  _stream: TaskStreamHandle | undefined;
  _generation: number;

  setReviewerEnabled: (enabled: boolean) => void;
  applyEvent: (event: AgentEvent) => void;
  loadHistory: () => Promise<void>;
  startTask: (input: StartTaskInput) => Promise<void>;
  openTask: (taskId: string) => Promise<void>;
  restore: () => Promise<void>;
  cancelTask: () => Promise<void>;
  replyToQuestion: (text: string) => void;
  reset: () => void;
}

const initialTaskState = {
  activeTaskId: undefined,
  events: [],
  status: undefined,
  answer: undefined,
  error: undefined,
  question: undefined,
  staticEventCount: 0,
  reviewerEnabled: false,
} satisfies Partial<TaskStoreState>;

export const useTaskStore = create<TaskStoreState>((set, get) => ({
  ...initialTaskState,
  history: [],
  historyLoading: false,
  _stream: undefined,
  _generation: 0,

  setReviewerEnabled: (enabled) => set({ reviewerEnabled: enabled }),

  // Shared by live events and snapshot replay: a snapshot is the only delivery
  // path when the socket (re)connects after the task already finished, so the
  // terminal events inside it must update state the same way live ones do.
  applyEvent: (event) => {
    if (event.type === 'agent_question') {
      set({ question: String(event.question ?? '') });
    } else if (event.type === 'user_answer') {
      set({ question: undefined });
    } else if (event.type === 'task_completed') {
      set({
        answer: String(event.answer ?? ''),
        status: 'completed',
        question: undefined,
      });
    } else if (event.type === 'task_failed') {
      set({
        error: String(event.error ?? 'Task failed.'),
        status: 'failed',
        question: undefined,
      });
    }
  },

  loadHistory: async () => {
    set({ historyLoading: true });
    try {
      const page = await api.listTasks();
      set({ history: page.items });
    } catch {
      // Best-effort: the history sidebar is not worth failing the page over.
    } finally {
      set({ historyLoading: false });
    }
  },

  startTask: async (input) => {
    const generation = get()._generation + 1;
    get()._stream?.close();
    set({
      ...initialTaskState,
      _generation: generation,
      _stream: undefined,
      status: 'pending',
      reviewerEnabled: input.reviewer_enabled,
    });

    try {
      const created = await api.startTask(input);
      if (get()._generation !== generation) return;
      persistActiveTaskId(created.task_id);
      set({ activeTaskId: created.task_id, status: created.status });
      attachStream(set, get, created.task_id, generation);
      void get().loadHistory();
    } catch (err) {
      if (get()._generation !== generation) return;
      set({
        error: err instanceof ApiError ? err.message : 'Task could not be started.',
        status: 'failed',
      });
    }
  },

  openTask: async (taskId) => {
    const generation = get()._generation + 1;
    get()._stream?.close();
    set({
      ...initialTaskState,
      _generation: generation,
      _stream: undefined,
      activeTaskId: taskId,
    });
    persistActiveTaskId(taskId);

    let doc;
    try {
      doc = await api.getTask(taskId);
    } catch (err) {
      // A newer openTask/startTask already owns the view — drop this result.
      if (get()._generation !== generation) return;
      if (err instanceof ApiError && err.status === 404) {
        persistActiveTaskId(undefined);
        set((state) => ({
          activeTaskId: undefined,
          history: state.history.filter((task) => task.task_id !== taskId),
          error: EXPIRED_TASK_MESSAGE,
        }));
        return;
      }
      set({ error: 'Task could not be loaded.' });
      return;
    }
    if (get()._generation !== generation) return;

    set({
      events: doc.events,
      staticEventCount: doc.events.length,
      status: doc.status,
      reviewerEnabled: doc.reviewer_enabled,
    });
    for (const event of doc.events) get().applyEvent(event);

    // A finished task emits nothing further; opening a socket would only get
    // one snapshot and an immediate close.
    if (!TERMINAL_STATUSES.has(doc.status)) {
      attachStream(set, get, taskId, generation);
    }
  },

  restore: async () => {
    // The store is a module singleton, so it stays warm across navigation and
    // only a full reload needs the id read back from localStorage.
    if (get().activeTaskId !== undefined) return;
    const taskId = readActiveTaskId();
    if (taskId) await get().openTask(taskId);
  },

  cancelTask: async () => {
    const taskId = get().activeTaskId;
    if (!taskId) return;
    try {
      await api.cancelTask(taskId);
    } catch {
      /* task may have already finished; ignore */
    }
  },

  replyToQuestion: (text) => {
    get()._stream?.answer(text);
    set({ question: undefined });
  },

  reset: () => {
    get()._stream?.close();
    persistActiveTaskId(undefined);
    set((state) => ({
      ...initialTaskState,
      history: [],
      historyLoading: false,
      _stream: undefined,
      // Invalidate any in-flight request that would otherwise repopulate state.
      _generation: state._generation + 1,
    }));
  },
}));

type SetState = StoreApi<TaskStoreState>['setState'];
type GetState = StoreApi<TaskStoreState>['getState'];

/**
 * Subscribe to a task's live stream. Every handler re-checks `generation`:
 * `close()` stops reconnects but cannot cancel a message already in flight, so
 * without this a rapid A→B→A switch could paint task A's events over task B.
 */
function attachStream(
  set: SetState,
  get: GetState,
  taskId: string,
  generation: number,
): void {
  const stream = openTaskStream(taskId, {
    onSnapshot: (status, events) => {
      if (get()._generation !== generation) return;
      set({
        status: status as TaskStatus,
        events,
        staticEventCount: events.length,
      });
      for (const event of events) get().applyEvent(event);
    },
    onEvent: (event) => {
      if (get()._generation !== generation) return;
      set((state) => ({ events: [...state.events, event] }));
      get().applyEvent(event);
      // Live-only notice: a task can fail while the user is on another page.
      // Snapshot replay skips this path, so reopening a failed task won't re-toast.
      if (event.type === 'task_failed') {
        toast.error(String(event.error ?? 'Task failed.'), 'Task failed');
      }
      // Live finish: refresh the sidebar so this row leaves the running state.
      // Snapshot replay deliberately skips this — reopening a task is not news.
      if (TERMINAL_EVENT_TYPES.has(event.type)) void get().loadHistory();
    },
  });
  if (get()._generation !== generation) {
    // Superseded while the socket was being created.
    stream.close();
    return;
  }
  set({ _stream: stream });
}
