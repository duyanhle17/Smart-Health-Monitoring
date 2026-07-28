import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import Joystick from './Joystick';
import { STICK_RADIUS_PX } from '../../lib/joystickMotion';

afterEach(cleanup);

// jsdom does no layout, so getBoundingClientRect returns zeroes. Pin it to a
// known box centred on (100, 100) so pointer offsets are predictable.
const pinBase = (element) => {
  element.getBoundingClientRect = () => ({
    left: 100 - STICK_RADIUS_PX,
    top: 100 - STICK_RADIUS_PX,
    width: STICK_RADIUS_PX * 2,
    height: STICK_RADIUS_PX * 2,
    right: 100 + STICK_RADIUS_PX,
    bottom: 100 + STICK_RADIUS_PX,
    x: 100 - STICK_RADIUS_PX,
    y: 100 - STICK_RADIUS_PX,
  });
};

describe('Joystick', () => {
  it('reports a rightward vector when pushed right', () => {
    const onVector = vi.fn();
    render(<Joystick onVector={onVector} onRelease={() => {}} label="WK_101" />);
    const base = screen.getByTestId('joystick');
    pinBase(base);

    fireEvent.pointerDown(base, { clientX: 100 + STICK_RADIUS_PX, clientY: 100 });

    const last = onVector.mock.calls.at(-1)[0];
    expect(last.x).toBeCloseTo(1, 5);
    expect(last.y).toBeCloseTo(0, 5);
  });

  it('reports a negative y when pushed up', () => {
    const onVector = vi.fn();
    render(<Joystick onVector={onVector} onRelease={() => {}} label="WK_101" />);
    const base = screen.getByTestId('joystick');
    pinBase(base);

    fireEvent.pointerDown(base, { clientX: 100, clientY: 100 - STICK_RADIUS_PX });

    expect(onVector.mock.calls.at(-1)[0].y).toBeCloseTo(-1, 5);
  });

  it('recentres and fires onRelease exactly once when the thumb lifts', () => {
    const onVector = vi.fn();
    const onRelease = vi.fn();
    render(<Joystick onVector={onVector} onRelease={onRelease} label="WK_101" />);
    const base = screen.getByTestId('joystick');
    pinBase(base);

    fireEvent.pointerDown(base, { clientX: 100 + STICK_RADIUS_PX, clientY: 100 });
    fireEvent.pointerUp(window);

    expect(onRelease).toHaveBeenCalledTimes(1);
    expect(onVector.mock.calls.at(-1)[0]).toEqual({ x: 0, y: 0 });
  });

  it('does not fire onRelease when the thumb was never down', () => {
    const onRelease = vi.fn();
    render(<Joystick onVector={() => {}} onRelease={onRelease} label="WK_101" />);
    fireEvent.pointerUp(window);
    expect(onRelease).not.toHaveBeenCalled();
  });

  it('shows the label of the worker it is driving', () => {
    render(<Joystick onVector={() => {}} onRelease={() => {}} label="WK_101" />);
    expect(screen.getByText('WK_101')).toBeTruthy();
  });
});
