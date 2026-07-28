import { describe, it, expect } from 'vitest';
import {
  DEAD_ZONE,
  JITTER_AMPLITUDE_PX,
  JITTER_STEP_MS,
  LEASH_UNITS,
  MAX_SPEED_UNITS_PER_S,
  STICK_RADIUS_PX,
  advancePosition,
  clampToLeash,
  isCentred,
  jitterOffset,
  stickVector,
} from './joystickMotion';

describe('stickVector', () => {
  it('reports zero at the exact centre', () => {
    expect(stickVector(0, 0)).toEqual({ x: 0, y: 0 });
  });

  it('treats a tiny deflection as centre, because a thumb is never still', () => {
    const tiny = STICK_RADIUS_PX * (DEAD_ZONE / 2);
    expect(stickVector(tiny, 0)).toEqual({ x: 0, y: 0 });
  });

  it('reaches unit magnitude at the stick radius', () => {
    const v = stickVector(STICK_RADIUS_PX, 0);
    expect(v.x).toBeCloseTo(1, 5);
    expect(v.y).toBeCloseTo(0, 5);
  });

  it('saturates rather than growing past the radius', () => {
    const v = stickVector(STICK_RADIUS_PX * 10, 0);
    expect(Math.hypot(v.x, v.y)).toBeCloseTo(1, 5);
  });

  it('keeps direction on a diagonal while staying inside the unit disc', () => {
    const v = stickVector(STICK_RADIUS_PX, STICK_RADIUS_PX);
    expect(Math.hypot(v.x, v.y)).toBeCloseTo(1, 5);
    expect(v.x).toBeCloseTo(v.y, 5);
  });

  it('preserves a negative (upward) deflection', () => {
    expect(stickVector(0, -STICK_RADIUS_PX).y).toBeCloseTo(-1, 5);
  });
});

describe('isCentred', () => {
  it('is true only for the zero vector', () => {
    expect(isCentred({ x: 0, y: 0 })).toBe(true);
    expect(isCentred({ x: 0.3, y: 0 })).toBe(false);
  });
});

describe('advancePosition', () => {
  it('moves at the full-deflection speed over one second', () => {
    const next = advancePosition({ x: 10, y: 10 }, { x: 1, y: 0 }, 1000);
    expect(next.x).toBeCloseTo(10 + MAX_SPEED_UNITS_PER_S, 5);
    expect(next.y).toBeCloseTo(10, 5);
  });

  it('scales with elapsed time, so a 16ms frame moves a small fraction', () => {
    const next = advancePosition({ x: 10, y: 10 }, { x: 1, y: 0 }, 16);
    expect(next.x).toBeCloseTo(10 + (MAX_SPEED_UNITS_PER_S * 16) / 1000, 5);
  });

  it('moves proportionally for a partial deflection', () => {
    const next = advancePosition({ x: 10, y: 10 }, { x: 0.5, y: 0 }, 1000);
    expect(next.x).toBeCloseTo(10 + MAX_SPEED_UNITS_PER_S / 2, 5);
  });

  it('moves up the map for a negative y vector, with no axis inversion', () => {
    expect(advancePosition({ x: 50, y: 50 }, { x: 0, y: -1 }, 1000).y).toBeLessThan(50);
  });

  it('clamps at the map edges instead of running off', () => {
    expect(advancePosition({ x: 99, y: 50 }, { x: 1, y: 0 }, 1000).x).toBe(100);
    expect(advancePosition({ x: 1, y: 50 }, { x: -1, y: 0 }, 1000).x).toBe(0);
    expect(advancePosition({ x: 50, y: 1 }, { x: 0, y: -1 }, 1000).y).toBe(0);
    expect(advancePosition({ x: 50, y: 99 }, { x: 0, y: 1 }, 1000).y).toBe(100);
  });

  it('crosses the full map in about seven seconds at full deflection', () => {
    expect(100 / MAX_SPEED_UNITS_PER_S).toBeGreaterThan(6);
    expect(100 / MAX_SPEED_UNITS_PER_S).toBeLessThan(8);
  });

  it('stops at the leash when an anchor is supplied', () => {
    const anchor = { x: 50, y: 50 };
    let position = { x: 50, y: 50 };
    for (let i = 0; i < 60; i += 1) {
      position = advancePosition(position, { x: 1, y: 0 }, 100, anchor);
    }
    expect(position.x).toBeCloseTo(50 + LEASH_UNITS, 5);
  });

  it('travels freely when no anchor is supplied', () => {
    let position = { x: 10, y: 50 };
    for (let i = 0; i < 60; i += 1) {
      position = advancePosition(position, { x: 1, y: 0 }, 100, null);
    }
    expect(position.x).toBeGreaterThan(10 + LEASH_UNITS);
  });
});

describe('clampToLeash', () => {
  it('leaves a position inside the leash alone', () => {
    expect(clampToLeash({ x: 50, y: 50 }, { x: 60, y: 45 })).toEqual({ x: 60, y: 45 });
  });

  it('clamps each axis independently to twenty units', () => {
    expect(LEASH_UNITS).toBe(20);
    expect(clampToLeash({ x: 50, y: 50 }, { x: 99, y: 50 })).toEqual({ x: 70, y: 50 });
    expect(clampToLeash({ x: 50, y: 50 }, { x: 0, y: 50 })).toEqual({ x: 30, y: 50 });
    expect(clampToLeash({ x: 50, y: 50 }, { x: 50, y: 99 })).toEqual({ x: 50, y: 70 });
    expect(clampToLeash({ x: 50, y: 50 }, { x: 50, y: 0 })).toEqual({ x: 50, y: 30 });
  });

  it('still respects the map edges when the leash would run past them', () => {
    expect(clampToLeash({ x: 95, y: 50 }, { x: 200, y: 50 }).x).toBe(100);
    expect(clampToLeash({ x: 5, y: 50 }, { x: -200, y: 50 }).x).toBe(0);
  });
});

describe('jitterOffset', () => {
  it('stays inside the amplitude on both axes', () => {
    for (let t = 0; t < 5000; t += 37) {
      const { x, y } = jitterOffset(t);
      expect(Math.abs(x)).toBeLessThanOrEqual(JITTER_AMPLITUDE_PX);
      expect(Math.abs(y)).toBeLessThanOrEqual(JITTER_AMPLITUDE_PX);
    }
  });

  it('holds a value for a step and then jumps, which is what reads as stutter', () => {
    const a = jitterOffset(0);
    expect(jitterOffset(JITTER_STEP_MS - 1)).toEqual(a);
    expect(jitterOffset(JITTER_STEP_MS + 1)).not.toEqual(a);
  });

  it('is deterministic, so the same instant always renders the same offset', () => {
    expect(jitterOffset(1234)).toEqual(jitterOffset(1234));
  });

  it('moves on both axes independently rather than along a diagonal', () => {
    const samples = [];
    for (let step = 0; step < 20; step += 1) samples.push(jitterOffset(step * JITTER_STEP_MS));
    expect(samples.some((s) => s.x !== s.y)).toBe(true);
  });

  it('can be silenced by passing zero amplitude', () => {
    expect(jitterOffset(1234, 0)).toEqual({ x: 0, y: 0 });
  });
});
