import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, fireEvent, act } from '@testing-library/react';
import FlatMap from './FlatMap';
import useStore from '../../store';

afterEach(cleanup);

beforeEach(() => {
  useStore.setState({
    workers: {
      WK_101: { worker_id: 'WK_101', alert: 'NORMAL', x: 50, y: 50, location_valid: true },
      WK_102: { worker_id: 'WK_102', alert: 'NORMAL', x: 20, y: 20, location_valid: true },
    },
    anchors: [{ id: 'ANC_LEFT', x: 10, y: 10 }, { id: 'ANC_RIGHT', x: 90, y: 10 }],
    personnel: [{ id: 'WK_101', name: 'Nguyen Van A' }],
    hiddenNodes: {},
    uwbConfig: null,
    mapTheme: 'SITE',
  });
  window.innerWidth = 390;
  window.innerHeight = 844;
});

const renderMap = (props = {}) =>
  render(
    <FlatMap
      selectedId={null}
      onSelect={() => {}}
      overrides={{}}
      uncommittedIds={new Set()}
      jitterFor={() => null}
      onDragMove={() => {}}
      onDragEnd={() => {}}
      {...props}
    />
  );

describe('FlatMap', () => {
  it('renders every worker, including ones without a fix, because placing them is the point', () => {
    act(() => {
      useStore.setState({
        workers: {
          WK_101: { worker_id: 'WK_101', alert: 'NORMAL', x: 50, y: 50, location_valid: true },
          WK_103: { worker_id: 'WK_103', alert: 'NORMAL', x: 0, y: 0, location_valid: false },
        },
      });
    });
    renderMap();
    expect(screen.getByTestId('node-WK_101')).toBeTruthy();
    expect(screen.getByTestId('node-WK_103')).toBeTruthy();
  });

  it('resolves the registered name, falling back to the raw tag id', () => {
    renderMap();
    expect(screen.getByTestId('label-WK_101').textContent).toBe('Nguyen Van A');
    expect(screen.getByTestId('label-WK_102').textContent).toBe('WK_102');
  });

  it('hides nodes the admin has toggled off', () => {
    act(() => useStore.setState({ hiddenNodes: { WK_102: true } }));
    renderMap();
    expect(screen.queryByTestId('node-WK_102')).toBe(null);
  });

  it('lays the scene flat, with no rotation in the transform', () => {
    renderMap();
    const scene = screen.getByTestId('flat-map-scene');
    expect(scene.style.transform).not.toMatch(/rotate/);
    expect(scene.style.transform).toMatch(/scale\(/);
  });

  it('selects a worker on pointer down, not on release', () => {
    const onSelect = vi.fn();
    renderMap({ onSelect });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 0, clientY: 0 });
    expect(onSelect).toHaveBeenCalledWith('WK_101');
  });

  it('reports drag movement in logical coordinates', () => {
    const onDragMove = vi.fn();
    renderMap({ onDragMove });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(screen.getByTestId('flat-map-surface'), { clientX: 110, clientY: 100 });

    expect(onDragMove).toHaveBeenCalled();
    const [id, pos] = onDragMove.mock.calls.at(-1);
    expect(id).toBe('WK_101');
    expect(pos.x).toBeGreaterThan(50);
  });

  it('commits once when the drag ends, handing over the final coordinate', () => {
    const onDragEnd = vi.fn();
    renderMap({ onDragEnd });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(screen.getByTestId('flat-map-surface'), { clientX: 140, clientY: 100 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));

    expect(onDragEnd).toHaveBeenCalledTimes(1);
    // The position travels with the event rather than being looked up by the
    // parent, so a release cannot race a render that has not landed yet.
    const [id, position] = onDragEnd.mock.calls[0];
    expect(id).toBe('WK_101');
    expect(position.x).toBeGreaterThan(50);
    expect(position.y).toBeCloseTo(50, 5);
  });

  it('hands over a null position when the pointer never moved', () => {
    const onDragEnd = vi.fn();
    renderMap({ onDragEnd });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 100, clientY: 100 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));
    expect(onDragEnd).toHaveBeenCalledWith('WK_101', null);
  });

  it('deselects on a tap of the empty map', () => {
    const onSelect = vi.fn();
    renderMap({ selectedId: 'WK_101', onSelect });
    const surface = screen.getByTestId('flat-map-surface');
    fireEvent.pointerDown(surface, { clientX: 10, clientY: 10 });
    fireEvent.pointerUp(surface, { clientX: 12, clientY: 11 });
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('keeps the selection when the empty-map gesture was a pan, not a tap', () => {
    const onSelect = vi.fn();
    renderMap({ selectedId: 'WK_101', onSelect });
    const surface = screen.getByTestId('flat-map-surface');
    fireEvent.pointerDown(surface, { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(surface, { clientX: 90, clientY: 10 });
    fireEvent.pointerUp(surface, { clientX: 90, clientY: 10 });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('renders a worker at its override coordinate rather than the store one', () => {
    renderMap({ overrides: { WK_101: { x: 90, y: 90 } } });
    expect(screen.getByTestId('node-WK_101').style.left).toBe('900px');
    expect(screen.getByTestId('node-WK_101').style.top).toBe('720px');
  });

  it('marks an uncommitted worker so a failed save is visible', () => {
    renderMap({ uncommittedIds: new Set(['WK_101']) });
    expect(screen.getByTestId('uncommitted-WK_101')).toBeTruthy();
  });

  it('explains an empty scene instead of showing a blank screen', () => {
    act(() => useStore.setState({ workers: {} }));
    renderMap();
    expect(screen.getByTestId('flat-map-empty')).toBeTruthy();
  });

  it('wobbles only the worker the caller nominates', () => {
    renderMap({ jitterFor: (id) => (id === 'WK_101' ? { x: 4, y: -3 } : null) });
    expect(screen.getByTestId('node-WK_101').style.transform).toBe('translate(4px, -3px)');
    expect(screen.getByTestId('node-WK_102').style.transform).toBe('');
  });
});
