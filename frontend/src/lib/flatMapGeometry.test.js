import { describe, it, expect } from 'vitest';
import {
  MAX_ZOOM_MULTIPLE,
  SCENE_W_PX,
  SCENE_H_PX,
  clampLogical,
  clampPan,
  clampZoomMultiple,
  fitScale,
  screenDeltaToLogical,
} from './flatMapGeometry';

describe('fitScale', () => {
  it('fits the limiting axis so the whole scene is visible', () => {
    // 390x844 portrait phone: width is limiting (0.39 < 1.055)
    expect(fitScale(390, 844)).toBeCloseTo(0.39, 5);
    // 844x390 landscape: height is limiting (0.4875 < 0.844)
    expect(fitScale(844, 390)).toBeCloseTo(0.4875, 5);
  });

  it('returns 1 for a degenerate viewport rather than 0 or NaN', () => {
    expect(fitScale(0, 0)).toBe(1);
    expect(fitScale(390, 0)).toBe(1);
  });
});

describe('clampZoomMultiple', () => {
  it('never drops below 1, so the scene is always fully reachable', () => {
    expect(clampZoomMultiple(0.2)).toBe(1);
    expect(clampZoomMultiple(-4)).toBe(1);
  });

  it('caps at the maximum multiple', () => {
    expect(clampZoomMultiple(99)).toBe(MAX_ZOOM_MULTIPLE);
  });

  it('passes through a value already in range', () => {
    expect(clampZoomMultiple(1.8)).toBeCloseTo(1.8, 5);
  });

  it('falls back to 1 rather than propagating NaN into a transform', () => {
    expect(clampZoomMultiple(NaN)).toBe(1);
    expect(clampZoomMultiple(Infinity)).toBe(1);
  });
});

describe('screenDeltaToLogical', () => {
  it('converts pixel drag to logical units using the 10px/8px scene mapping', () => {
    expect(screenDeltaToLogical(10, 8, 1)).toEqual({ dlx: 1, dly: 1 });
  });

  it('scales the delta by zoom, so a zoomed-in drag moves fewer units', () => {
    expect(screenDeltaToLogical(20, 16, 2)).toEqual({ dlx: 1, dly: 1 });
  });

  it('preserves direction for negative deltas', () => {
    expect(screenDeltaToLogical(-10, -8, 1)).toEqual({ dlx: -1, dly: -1 });
  });
});

describe('clampLogical', () => {
  it('holds each of the four boundaries', () => {
    expect(clampLogical(-5, 50)).toEqual({ x: 0, y: 50 });
    expect(clampLogical(105, 50)).toEqual({ x: 100, y: 50 });
    expect(clampLogical(50, -5)).toEqual({ x: 50, y: 0 });
    expect(clampLogical(50, 105)).toEqual({ x: 50, y: 100 });
  });

  it('leaves an in-range coordinate alone', () => {
    expect(clampLogical(42.5, 17.25)).toEqual({ x: 42.5, y: 17.25 });
  });
});

describe('clampPan', () => {
  it('collapses pan to zero at fit scale, where the scene already fits', () => {
    const fit = fitScale(390, 844);
    expect(clampPan(200, 200, fit, 390, 844)).toEqual({ x: 0, y: 0 });
  });

  it('allows pan up to half the overflow once zoomed past fit', () => {
    // zoom 1 on a 390-wide viewport: scene is 1000px, overflow 610, half = 305
    expect(clampPan(9999, 0, 1, 390, 844).x).toBeCloseTo(305, 5);
    expect(clampPan(-9999, 0, 1, 390, 844).x).toBeCloseTo(-305, 5);
  });

  it('clamps the vertical axis independently of the horizontal one', () => {
    // zoom 1 on an 844-tall viewport: scene is 800px, so no vertical overflow
    expect(clampPan(0, 500, 1, 390, 844).y).toBe(0);
  });
});

describe('scene constants', () => {
  it('matches the coordinate frame the backend addresses', () => {
    expect(SCENE_W_PX).toBe(1000);
    expect(SCENE_H_PX).toBe(800);
  });
});
