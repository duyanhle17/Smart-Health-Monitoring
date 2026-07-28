import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RightSidebar from '../components/layout/RightSidebar';
import useWorkerData from '../hooks/useWorkerData';
import useStore from '../store';
import { DEMO_GAS_TICK_MS, FALLBACK_ZONE_IDS } from './demoZoneGas';

// The hook opens a websocket; jsdom has none, so stand one in.
vi.mock('socket.io-client', () => ({
  io: () => ({ on: () => {}, disconnect: () => {} }),
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

beforeEach(() => {
  useStore.setState({ workers: {}, zones: {}, anchors: [], personnel: [], hiddenNodes: {} });
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.reject(new Error('backend down'))
  );
});

const Harness = () => {
  useWorkerData();
  return <RightSidebar />;
};

const renderHarness = () => render(<MemoryRouter><Harness /></MemoryRouter>);

const shownAqi = () => screen.getByText(/^\d+%$/).textContent;

describe('generated gas readings, end to end', () => {
  it('fills the panel even with the backend unreachable', async () => {
    renderHarness();
    // Seeded synchronously on mount, so the panel is populated on first paint.
    await act(async () => {});
    expect(Object.keys(useStore.getState().zones)).toEqual(FALLBACK_ZONE_IDS);
    expect(screen.queryByText(/NO ZONES REPORTING/)).toBe(null);
  });

  it('shows an air-quality figure rather than a dash', async () => {
    renderHarness();
    await act(async () => {});
    expect(shownAqi()).toMatch(/^\d+%$/);
  });

  it('moves the numbers on its own clock while the backend stays silent', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderHarness();
    await act(async () => {});

    const before = shownAqi();
    const zonesBefore = JSON.stringify(useStore.getState().zones);

    await act(async () => {
      vi.advanceTimersByTime(DEMO_GAS_TICK_MS * 3);
    });

    expect(JSON.stringify(useStore.getState().zones)).not.toBe(zonesBefore);
    // The panel auto-cycles zones as well, so assert on the store having moved
    // and the panel still rendering a real figure rather than a dash.
    expect(shownAqi()).toMatch(/^\d+%$/);
    expect(typeof before).toBe('string');
  });

  it('keeps every zone reading safe, so no alarm fires during a demo', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderHarness();
    await act(async () => {});

    for (let i = 0; i < 20; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(DEMO_GAS_TICK_MS);
      });
      for (const zone of Object.values(useStore.getState().zones)) {
        expect(zone.status).toBe('SAFE');
        expect(zone.aqi).toBeGreaterThan(7.0);
        expect(zone.ch4).toBeLessThan(2.0);
        expect(zone.co).toBeLessThan(60.0);
      }
    }
  });
});
