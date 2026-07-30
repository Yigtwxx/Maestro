import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  api: {
    logout: vi.fn(() => Promise.resolve()),
    getCurrentUser: vi.fn(() => Promise.reject(new Error('not signed in'))),
  },
  accessTokenStore: { get: vi.fn(), set: vi.fn(), clear: vi.fn() },
  ensureFreshAccessToken: vi.fn(() => Promise.resolve(undefined)),
}));

const { accessTokenStore, api, ensureFreshAccessToken } = await import('@/lib/api');
const { useAuthStore } = await import('@/stores/auth');

const signedIn = () => ({
  isAuthenticated: true,
  hydrated: true,
  email: 'u@example.com',
  user: { id: '1' } as never,
});

describe('useAuthStore.logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState(signedIn());
  });

  it('revokes the session server-side', async () => {
    // The bug this guards: sign-out used to be purely local, leaving the
    // refresh-token family valid for a further seven days.
    await useAuthStore.getState().logout();

    expect(api.logout).toHaveBeenCalledTimes(1);
  });

  it('clears local session state', async () => {
    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.email).toBeUndefined();
    expect(state.user).toBeUndefined();
    expect(accessTokenStore.clear).toHaveBeenCalled();
  });

  it('still signs out locally when the revocation call fails', async () => {
    // A user who is offline, or whose session is already gone, must not be
    // stuck looking at a signed-in shell.
    vi.mocked(api.logout).mockRejectedValueOnce(new Error('offline'));

    await expect(useAuthStore.getState().logout()).resolves.toBeUndefined();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});

describe('useAuthStore.hydrate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: false,
      hydrated: false,
      email: undefined,
      user: undefined,
    });
  });

  it('signs in when the refresh cookie yields an access token', async () => {
    vi.mocked(ensureFreshAccessToken).mockResolvedValueOnce('jwt');

    await useAuthStore.getState().hydrate();

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().hydrated).toBe(true);
  });

  it('marks itself hydrated when no session survived', async () => {
    // `hydrated` must flip either way — the app layout holds its loading
    // screen until it does, so failing to set it hangs the app forever.
    await useAuthStore.getState().hydrate();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().hydrated).toBe(true);
  });

  it('does not spend a second rotation once hydrated', async () => {
    // StrictMode invokes the effect twice; a second rotation would replay a
    // token the first one already spent.
    vi.mocked(ensureFreshAccessToken).mockResolvedValue('jwt');

    await useAuthStore.getState().hydrate();
    await useAuthStore.getState().hydrate();

    expect(ensureFreshAccessToken).toHaveBeenCalledTimes(1);
  });
});
