// WebSocket helper for live task streaming with auto-reconnect.

import {
  TASK_POLL_INTERVAL_MS,
  TERMINAL_EVENT_TYPES,
  TERMINAL_STATUSES,
  WS_BASE_URL,
  WS_FALLBACK_AFTER_FAILURES,
} from '@/lib/constants';
import { api, ApiError, ensureFreshAccessToken } from '@/lib/api';
import type { AgentEvent, TaskStatus } from '@/types';

export interface TaskSocketHandlers {
  onSnapshot?: (status: string, events: AgentEvent[]) => void;
  onEvent?: (event: AgentEvent) => void;
  onClose?: () => void;
}

interface SnapshotMessage {
  type: 'snapshot';
  status: string;
  events: AgentEvent[];
}

export interface TaskStreamHandle {
  /** Close the socket and stop reconnection. */
  close: () => void;
  /**
   * Send a human-in-the-loop answer back to a waiting agent. Rejects when the
   * HTTP fallback delivery fails so the caller can surface the error and let
   * the user retry, rather than dropping the answer silently.
   */
  answer: (text: string) => Promise<void>;
}

/**
 * Origin to open the socket against. Without an explicit override the socket is
 * same-origin, matching the reverse proxy that fronts both app and API — so the
 * image carries no domain and `wss:` is picked up from a TLS page automatically.
 * Only ever called from the browser, where `window` is always defined.
 */
function wsBase(): string {
  if (WS_BASE_URL) return WS_BASE_URL;
  const { protocol, host } = window.location;
  return `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}`;
}

/**
 * Open a live task stream. Returns a handle to close the socket or send an
 * answer. Reconnects with backoff until the task reaches a terminal state.
 *
 * Resilient to backgrounded tabs: the access token is refreshed before every
 * (re)connect (a stale token makes the server reject the handshake forever),
 * and returning to the foreground reconnects immediately instead of waiting
 * out a browser-throttled backoff timer. Every successful (re)connect replays
 * a full snapshot, so missed events — including the final answer — are
 * recovered.
 *
 * If the socket cannot be established at all (proxy strips the upgrade,
 * firewall, broken WS route), the stream degrades to HTTP polling of
 * GET /tasks/{id} — same snapshot shape, delivered through `onSnapshot` — and
 * stays on polling until the task is terminal.
 */
export function openTaskStream(
  taskId: string,
  handlers: TaskSocketHandlers,
): TaskStreamHandle {
  let socket: WebSocket | undefined;
  let closedByCaller = false;
  // Once the task is terminal the server closes after every (re)connect;
  // reconnecting again would loop forever.
  let taskFinished = false;
  let reconnectDelay = 1000;
  let reconnectTimer: number | undefined;
  // A connection that dies before delivering a single message counts as a
  // failure; enough of those in a row and WS is treated as unreachable.
  let consecutiveFailures = 0;
  let polling = false;
  let pollTimer: number | undefined;
  let lastPolledStatus: string | undefined;
  let lastPolledEventCount = -1;

  const done = (): boolean => closedByCaller || taskFinished;

  const scheduleReconnect = (delay: number): void => {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = window.setTimeout(() => void connect(), delay);
  };

  const schedulePoll = (): void => {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(() => void poll(), TASK_POLL_INTERVAL_MS);
  };

  const poll = async (): Promise<void> => {
    if (done()) return;
    try {
      const task = await api.getTask(taskId);
      if (done()) return;
      // Only re-deliver when something changed; the snapshot path replaces
      // events wholesale, so redundant deliveries would just churn renders.
      if (
        task.status !== lastPolledStatus ||
        task.events.length !== lastPolledEventCount
      ) {
        lastPolledStatus = task.status;
        lastPolledEventCount = task.events.length;
        handlers.onSnapshot?.(task.status, task.events);
      }
      if (TERMINAL_STATUSES.has(task.status)) {
        taskFinished = true;
        handlers.onClose?.();
        return;
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        // Task deleted elsewhere — nothing left to stream.
        taskFinished = true;
        handlers.onClose?.();
        return;
      }
      // Transient failure (network, 5xx) — keep polling.
    }
    schedulePoll();
  };

  const startPolling = (): void => {
    if (polling || done()) return;
    polling = true;
    window.clearTimeout(reconnectTimer);
    void poll();
  };

  const connect = async (): Promise<void> => {
    if (done() || polling) return;
    // The token may have expired while the tab was hidden or the network was
    // down; connecting with a stale one gets rejected on every retry.
    const token = await ensureFreshAccessToken();
    if (done()) return;
    if (!token) {
      // No valid session left — stop instead of hammering the server.
      handlers.onClose?.();
      return;
    }
    const url = `${wsBase()}/api/v1/tasks/${taskId}/stream?token=${encodeURIComponent(token)}`;
    socket = new WebSocket(url);
    let gotMessage = false;

    socket.onopen = () => {
      reconnectDelay = 1000;
    };

    socket.onmessage = (raw: MessageEvent<string>) => {
      gotMessage = true;
      consecutiveFailures = 0;
      const data = JSON.parse(raw.data) as SnapshotMessage | AgentEvent;
      if ((data as SnapshotMessage).type === 'snapshot') {
        const snap = data as SnapshotMessage;
        if (TERMINAL_STATUSES.has(snap.status as TaskStatus)) {
          taskFinished = true;
        }
        handlers.onSnapshot?.(snap.status, snap.events);
      } else {
        const event = data as AgentEvent;
        if (TERMINAL_EVENT_TYPES.has(event.type)) taskFinished = true;
        handlers.onEvent?.(event);
      }
    };

    socket.onclose = () => {
      if (done()) return;
      if (!gotMessage) {
        consecutiveFailures += 1;
        if (consecutiveFailures >= WS_FALLBACK_AFTER_FAILURES) {
          startPolling();
          return;
        }
      }
      // Best-effort reconnect (capped backoff) for transient drops.
      reconnectDelay = Math.min(reconnectDelay * 2, 8000);
      scheduleReconnect(reconnectDelay);
      handlers.onClose?.();
    };
  };

  // Hidden tabs throttle timers, so a pending backoff can sit for minutes.
  // Reconnect the moment the tab is visible again.
  const onVisibilityChange = (): void => {
    if (document.visibilityState !== 'visible' || done() || polling) return;
    if (socket && socket.readyState !== WebSocket.CLOSED) return;
    scheduleReconnect(0);
  };
  document.addEventListener('visibilitychange', onVisibilityChange);

  void connect();

  return {
    close: () => {
      closedByCaller = true;
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(pollTimer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      socket?.close();
    },
    answer: async (text: string): Promise<void> => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'answer', answer: text }));
        return;
      }
      // Socket down or in polling mode — deliver over HTTP. Let a rejection
      // propagate so the caller can tell the user it did not go through.
      await api.answerTask(taskId, text);
    },
  };
}
