import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/lib/api';

const jsonResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const bodyOf = (mock: ReturnType<typeof vi.fn>, call = 0): Record<string, unknown> =>
  JSON.parse((mock.mock.calls[call][1] as RequestInit).body as string);

describe('public forms carry their anti-automation fields', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ detail: 'ok' })));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('forwards the honeypot and nonce on register', () => {
    // The backend answers a tripped submission with its normal success body,
    // so nothing downstream can tell these were dropped — which is exactly why
    // the client has to be checked here rather than through the response.
    api.register('a@b.com', 'supersecret', undefined, {
      challenge: 'nonce-value',
      website_url: '',
    });

    const body = bodyOf(fetchMock);
    expect(body.challenge).toBe('nonce-value');
    expect(body.website_url).toBe('');
  });

  it('forwards the honeypot and nonce on forgot-password', () => {
    api.forgotPassword('a@b.com', { challenge: 'nonce-value', website_url: '' });

    const body = bodyOf(fetchMock);
    expect(body.challenge).toBe('nonce-value');
    expect(body.website_url).toBe('');
  });

  it('sends no credentials with the challenge request', async () => {
    // Public and unauthenticated: it is fetched before anyone has signed in,
    // and attaching a token would make it look like a session-bound call.
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ provider: 'none', site_key: '', nonce: 'n' }),
    );

    const challenge = await api.challenge();

    expect(challenge.provider).toBe('none');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('GET');
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});
