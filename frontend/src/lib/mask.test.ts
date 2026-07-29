import { describe, expect, it } from 'vitest';
import { formatCountdown, maskEmail } from './mask';

describe('maskEmail', () => {
  it('keeps the first character and the whole domain', () => {
    expect(maskEmail('yigit@gmail.com')).toBe('y•••@gmail.com');
  });

  it('caps the bullets so a long local part is not a wall of dots', () => {
    expect(maskEmail('averylonglocalpart@example.com')).toBe('a•••@example.com');
  });

  it('still pads a single-character local part', () => {
    // Nothing left to hide, but the shape must stay consistent with the rest
    // so the address does not visibly reveal how short its local part is.
    expect(maskEmail('a@example.com')).toBe('a•••@example.com');
  });

  it('shortens the bullets for a two-character local part', () => {
    expect(maskEmail('ab@example.com')).toBe('a•@example.com');
  });

  it('returns anything that is not a single-@ address untouched', () => {
    expect(maskEmail('not-an-email')).toBe('not-an-email');
    expect(maskEmail('two@at@signs.com')).toBe('two@at@signs.com');
    expect(maskEmail('')).toBe('');
  });
});

describe('formatCountdown', () => {
  it('zero-pads the seconds', () => {
    expect(formatCountdown(93)).toBe('1:33');
    expect(formatCountdown(65)).toBe('1:05');
  });

  it('renders a sub-minute value with a zero minute', () => {
    expect(formatCountdown(9)).toBe('0:09');
  });

  it('floors to zero rather than rendering a negative clock', () => {
    expect(formatCountdown(0)).toBe('0:00');
    expect(formatCountdown(-5)).toBe('0:00');
  });

  it('truncates fractional seconds', () => {
    expect(formatCountdown(59.9)).toBe('0:59');
  });
});
