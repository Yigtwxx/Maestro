import { describe, expect, it } from 'vitest';
import { withRefreshLock } from '@/lib/refresh-lock';

/**
 * A minimal serializing LockManager, enough to observe the property that
 * matters: two holders of the same lock never overlap.
 */
function fakeLockManager(): LockManager {
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request: ((_name: string, fn: () => Promise<unknown>) => {
      const run = tail.then(() => fn());
      // Keep the chain alive even if a holder throws, mirroring the real API.
      tail = run.catch(() => undefined);
      return run;
    }) as LockManager['request'],
    query: () => Promise.resolve({}),
  } as LockManager;
}

describe('withRefreshLock', () => {
  it('does not let two holders overlap', async () => {
    const locks = fakeLockManager();
    const order: string[] = [];

    const hold = (id: string) =>
      withRefreshLock(async () => {
        order.push(`enter:${id}`);
        await new Promise((resolve) => setTimeout(resolve, 5));
        order.push(`exit:${id}`);
      }, locks);

    await Promise.all([hold('a'), hold('b')]);

    expect(order).toEqual(['enter:a', 'exit:a', 'enter:b', 'exit:b']);
  });

  it('returns the callback result through the lock', async () => {
    const result = await withRefreshLock(async () => 'rotated', fakeLockManager());
    expect(result).toBe('rotated');
  });

  it('still runs when the Web Locks API is unavailable', async () => {
    // Plain-HTTP deployments are not secure contexts, so `navigator.locks` is
    // undefined there. Refreshing must degrade, never stop.
    const result = await withRefreshLock(async () => 'rotated', undefined);
    expect(result).toBe('rotated');
  });

  it('propagates a rejection instead of swallowing it', async () => {
    await expect(
      withRefreshLock(() => Promise.reject(new Error('boom')), fakeLockManager()),
    ).rejects.toThrow('boom');
  });
});
