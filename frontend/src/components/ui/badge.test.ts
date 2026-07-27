import { describe, it, expect } from 'vitest';
import {
  isLiveStatus,
  STATUS_DOT,
  STATUS_RGB,
  statusDotClass,
  statusRgb,
} from '@/components/ui/Badge';
import type { TaskStatus } from '@/types';

const ALL_STATUSES: TaskStatus[] = [
  'pending',
  'running',
  'needs_review',
  'awaiting_answer',
  'completed',
  'completed_with_warnings',
  'failed',
  'cancelled',
  'timeout',
];

const LIVE_STATUSES: TaskStatus[] = ['running', 'awaiting_answer'];

describe('status color maps', () => {
  it('define a dot class and an rgb triplet for every status', () => {
    for (const status of ALL_STATUSES) {
      expect(STATUS_DOT[status], `dot for ${status}`).toBeTruthy();
      expect(STATUS_RGB[status], `rgb for ${status}`).toMatch(/^\d+ \d+ \d+$/);
    }
  });
});

describe('statusDotClass', () => {
  it('pulses live statuses only', () => {
    for (const status of ALL_STATUSES) {
      const cls = statusDotClass(status);
      expect(cls).toContain(STATUS_DOT[status]);
      expect(cls.includes('animate-pulse-glow')).toBe(LIVE_STATUSES.includes(status));
    }
  });

  it('falls back to the neutral hue for an unknown status', () => {
    expect(statusDotClass('bogus')).toBe('bg-muted');
  });
});

describe('statusRgb', () => {
  it('falls back to the pending hue for an unknown status', () => {
    expect(statusRgb('bogus')).toBe(STATUS_RGB.pending);
  });
});

describe('isLiveStatus', () => {
  it('is true only while the task is still moving', () => {
    for (const status of ALL_STATUSES) {
      expect(isLiveStatus(status)).toBe(LIVE_STATUSES.includes(status));
    }
  });
});
