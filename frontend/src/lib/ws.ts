// WebSocket helper for live task streaming with auto-reconnect.

import {
  TERMINAL_EVENT_TYPES,
  TERMINAL_STATUSES,
  WS_BASE_URL,
} from '@/lib/constants';
import { ensureFreshAccessToken } from '@/lib/api';
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
  /** Send a human-in-the-loop answer back to a waiting agent. */
  answer: (text: string) => void;
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

  const done = (): boolean => closedByCaller || taskFinished;

  const scheduleReconnect = (delay: number): void => {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = window.setTimeout(() => void connect(), delay);
  };

  const connect = async (): Promise<void> => {
    if (done()) return;
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

    socket.onopen = () => {
      reconnectDelay = 1000;
    };

    socket.onmessage = (raw: MessageEvent<string>) => {
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
      // Best-effort reconnect (capped backoff) for transient drops.
      reconnectDelay = Math.min(reconnectDelay * 2, 8000);
      scheduleReconnect(reconnectDelay);
      handlers.onClose?.();
    };
  };

  // Hidden tabs throttle timers, so a pending backoff can sit for minutes.
  // Reconnect the moment the tab is visible again.
  const onVisibilityChange = (): void => {
    if (document.visibilityState !== 'visible' || done()) return;
    if (socket && socket.readyState !== WebSocket.CLOSED) return;
    scheduleReconnect(0);
  };
  document.addEventListener('visibilitychange', onVisibilityChange);

  void connect();

  return {
    close: () => {
      closedByCaller = true;
      window.clearTimeout(reconnectTimer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      socket?.close();
    },
    answer: (text: string) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'answer', answer: text }));
      }
    },
  };
}
