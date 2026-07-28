import { describe, it, expect, beforeEach } from 'vitest';
import {
  MOBILE_MAX_WIDTH,
  VIEW_PREF_KEY,
  readViewPreference,
  resolveAdminView,
  writeViewPreference,
} from './useMobileMapMode';

describe('resolveAdminView', () => {
  it('always gives a wide screen the full console, so a desk operator is never surprised', () => {
    expect(resolveAdminView(MOBILE_MAX_WIDTH, null)).toBe('full');
    expect(resolveAdminView(1920, 'map')).toBe('full');
  });

  it('defaults a narrow screen to the map', () => {
    expect(resolveAdminView(390, null)).toBe('map');
    expect(resolveAdminView(MOBILE_MAX_WIDTH - 1, null)).toBe('map');
  });

  it('lets a narrow screen opt into the full console for field calibration', () => {
    expect(resolveAdminView(390, 'full')).toBe('full');
  });

  it('treats an explicit map preference on a narrow screen as the map', () => {
    expect(resolveAdminView(390, 'map')).toBe('map');
  });

  it('ignores an unrecognised stored preference', () => {
    expect(resolveAdminView(390, 'nonsense')).toBe('map');
  });
});

describe('view preference storage', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips through localStorage under the agreed key', () => {
    writeViewPreference('full');
    expect(localStorage.getItem(VIEW_PREF_KEY)).toBe('full');
    expect(readViewPreference()).toBe('full');
  });

  it('reads null when nothing has been stored', () => {
    expect(readViewPreference()).toBe(null);
  });
});
