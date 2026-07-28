import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AdminPanel from './AdminPanel';
import useStore from '../store';
import { VIEW_PREF_KEY } from '../hooks/useMobileMapMode';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  localStorage.clear();
  useStore.setState({
    workers: { WK_101: { worker_id: 'WK_101', alert: 'NORMAL', x: 50, y: 50 } },
    anchors: [],
    personnel: [],
    hiddenNodes: {},
    mapTheme: 'SITE',
  });
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  );
});

const renderAdmin = () => render(<MemoryRouter><AdminPanel /></MemoryRouter>);

describe('AdminPanel view selection', () => {
  it('shows the map-only view on a phone-width viewport', async () => {
    window.innerWidth = 390;
    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
    expect(screen.queryByText('Manual Node Override')).toBe(null);
  });

  it('shows the unchanged full console on a desktop-width viewport', async () => {
    window.innerWidth = 1440;
    renderAdmin();
    await waitFor(() => expect(screen.getByText('Manual Node Override')).toBeTruthy());
    expect(screen.queryByTestId('flat-map-surface')).toBe(null);
  });

  it('honours an explicit full-console preference on a phone', async () => {
    window.innerWidth = 390;
    localStorage.setItem(VIEW_PREF_KEY, 'full');
    renderAdmin();
    await waitFor(() => expect(screen.getByText('Manual Node Override')).toBeTruthy());
  });

  it('ignores a map preference on a desktop, so a desk operator keeps the console', async () => {
    window.innerWidth = 1440;
    localStorage.setItem(VIEW_PREF_KEY, 'map');
    renderAdmin();
    await waitFor(() => expect(screen.getByText('Manual Node Override')).toBeTruthy());
  });

  it('shows nothing but the map and its controls on the phone view', async () => {
    window.innerWidth = 390;
    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
    // No sidebar sections, and the joystick stays hidden until a selection.
    expect(screen.queryByText('Fall Diagnostics')).toBe(null);
    expect(screen.queryByText('UWB Range Calibration')).toBe(null);
    expect(screen.queryByTestId('joystick')).toBe(null);
  });

  it('reveals the joystick once a worker is selected', async () => {
    window.innerWidth = 390;
    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());

    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));

    await waitFor(() => expect(screen.getByTestId('joystick')).toBeTruthy());
  });

  it('offers a way back to the full console for field calibration', async () => {
    window.innerWidth = 390;
    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('open-full-console')).toBeTruthy());
    fireEvent.click(screen.getByTestId('open-full-console'));
    await waitFor(() => expect(screen.getByText('Manual Node Override')).toBeTruthy());
  });
});
