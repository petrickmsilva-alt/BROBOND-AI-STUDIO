// @vitest-environment jsdom
//
// PR009.6 — remembered-login seam ("Lembrar de mim", 30 days): behavioral
// tests for the cookie that greets a returning creator and scopes the
// session restore. It stores email + display name — never a credential.

import { afterEach, describe, expect, it } from 'vitest';
import {
  REMEMBERED_LOGIN_DAYS,
  clearRememberedLogin,
  getRememberedLogin,
  setRememberedLogin,
} from './remembered_login';

afterEach(() => clearRememberedLogin());

describe('PR009.6 remembered login (cookie seam)', () => {
  it('round-trips email and name', () => {
    setRememberedLogin('petrick@brobond.ai', 'Petrick');
    expect(getRememberedLogin()).toMatchObject({ email: 'petrick@brobond.ai', name: 'Petrick' });
  });

  it('falls back to the email when no name is given', () => {
    setRememberedLogin('petrick@brobond.ai', '');
    expect(getRememberedLogin()).toMatchObject({ email: 'petrick@brobond.ai', name: 'petrick@brobond.ai' });
  });

  it('keeps free text (accents, pipes, em dashes) intact', () => {
    setRememberedLogin('petrick@brobond.ai', 'Petrick | Brobond — São Paulo');
    expect(getRememberedLogin()?.name).toBe('Petrick | Brobond — São Paulo');
  });

  it('ignores an empty email', () => {
    setRememberedLogin('', 'Ghost');
    expect(document.cookie).toBe('');
    expect(getRememberedLogin()).toBeNull();
  });

  it('reads a lapsed record as absent (defensive clock guard)', () => {
    // A hand-edited / clock-skewed cookie past its expiry reads as absent.
    document.cookie = `brobond_remembered_login=${encodeURIComponent('x@brobond.ai')}|${encodeURIComponent('X')}|1; Path=/`;
    expect(getRememberedLogin()).toBeNull();
  });

  it('survives a corrupt record', () => {
    // Undecodable escape and a truncated payload both read as absent.
    document.cookie = 'brobond_remembered_login=%; Path=/';
    expect(getRememberedLogin()).toBeNull();
    document.cookie = 'brobond_remembered_login=a|b; Path=/';
    expect(getRememberedLogin()).toBeNull();
  });

  it('clears on demand', () => {
    setRememberedLogin('petrick@brobond.ai', 'Petrick');
    clearRememberedLogin();
    expect(getRememberedLogin()).toBeNull();
  });

  it('defaults the window to 30 days', () => {
    expect(REMEMBERED_LOGIN_DAYS).toBe(30);
    const before = Date.now();
    setRememberedLogin('petrick@brobond.ai', 'Petrick');
    const record = getRememberedLogin();
    expect(record).not.toBeNull();
    // 30 days, give or take the milliseconds the test itself takes.
    expect(record!.expiresAt).toBeGreaterThanOrEqual(before + 30 * 24 * 60 * 60 * 1000);
  });
});
