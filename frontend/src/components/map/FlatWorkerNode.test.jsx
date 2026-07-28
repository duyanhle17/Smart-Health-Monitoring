import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import FlatWorkerNode from './FlatWorkerNode';
import { toneFor } from '../../lib/flatNodeTone';
import { DOT_PX, HIT_MIN_PX } from '../../lib/flatNodeMetrics';

afterEach(cleanup);

const worker = (over = {}) => ({
  worker_id: 'WK_101',
  alert: 'NORMAL',
  x: 50,
  y: 50,
  ...over,
});

const renderNode = (over = {}, props = {}) =>
  render(
    <FlatWorkerNode
      worker={worker(over)}
      displayName="Nguyen Van A"
      left="500px"
      top="400px"
      selected={false}
      uncommitted={false}
      onPointerDown={props.onPointerDown || (() => {})}
      {...props}
    />
  );

describe('toneFor', () => {
  it('mirrors the isometric map precedence: health alert outranks position state', () => {
    expect(toneFor(worker({ alert: 'WARNING', location_stale: true }))).toBe('WARNING');
    expect(toneFor(worker({ alert: 'DANGER' }))).toBe('DANGER');
    expect(toneFor(worker({ alert: 'OFFLINE', location_last_known: true }))).toBe('OFFLINE');
  });

  it('separates last-known from degraded, as the isometric map does', () => {
    expect(toneFor(worker({ location_last_known: true }))).toBe('LAST_KNOWN');
    expect(toneFor(worker({ location_stale: true }))).toBe('DEGRADED');
    expect(toneFor(worker({ location_degraded: true }))).toBe('DEGRADED');
    expect(toneFor(worker({ uwb: { geometry_mode: 'line' } }))).toBe('DEGRADED');
    expect(toneFor(worker({ uwb: { low_geometry: true } }))).toBe('DEGRADED');
    expect(toneFor(worker({ uwb: { branch_ambiguous: true } }))).toBe('DEGRADED');
  });

  it('falls back to normal for a plain healthy worker', () => {
    expect(toneFor(worker())).toBe('NORMAL');
  });
});

describe('FlatWorkerNode', () => {
  it('shows the name label without needing hover, because touch has none', () => {
    renderNode();
    expect(screen.getByTestId('label-WK_101').textContent).toBe('Nguyen Van A');
  });

  it('picks up the worker when the label is touched', () => {
    const onPointerDown = vi.fn();
    renderNode({}, { onPointerDown });
    fireEvent.pointerDown(screen.getByTestId('label-WK_101'));
    expect(onPointerDown).toHaveBeenCalledTimes(1);
  });

  it('picks up the same worker when the dot is touched', () => {
    const onPointerDown = vi.fn();
    renderNode({}, { onPointerDown });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'));
    expect(onPointerDown).toHaveBeenCalledTimes(1);
  });

  it('sizes the dot at 28px and the hit box at or above the touch minimum', () => {
    renderNode();
    expect(screen.getByTestId('dot-WK_101').style.width).toBe(`${DOT_PX}px`);
    const hit = screen.getByTestId('hit-WK_101');
    expect(parseFloat(hit.style.minWidth)).toBeGreaterThanOrEqual(HIT_MIN_PX);
    expect(parseFloat(hit.style.height)).toBeGreaterThanOrEqual(HIT_MIN_PX);
  });

  it('marks a selected node so the operator knows what the joystick drives', () => {
    renderNode({}, { selected: true });
    expect(screen.getByTestId('ring-WK_101')).toBeTruthy();
  });

  it('has no ring when nothing is selected', () => {
    renderNode();
    expect(screen.queryByTestId('ring-WK_101')).toBe(null);
  });

  it('flags a position that failed to reach the server instead of hiding it', () => {
    renderNode({}, { uncommitted: true });
    expect(screen.getByTestId('uncommitted-WK_101')).toBeTruthy();
  });

  it('sits exactly on its coordinate when no jitter is supplied', () => {
    renderNode();
    expect(screen.getByTestId('node-WK_101').style.transform).toBe('');
  });

  it('applies jitter as a pixel offset, leaving the coordinate untouched', () => {
    renderNode({}, { jitter: { x: 3, y: -4 } });
    const node = screen.getByTestId('node-WK_101');
    expect(node.style.transform).toBe('translate(3px, -4px)');
    expect(node.style.left).toBe('500px');
    expect(node.style.top).toBe('400px');
  });
});
