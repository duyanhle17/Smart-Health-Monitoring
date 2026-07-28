import { describe, it, expect } from 'vitest';
import {
  DOT_PX,
  HIT_MIN_PX,
  HIT_PAD_PX,
  LABEL_GAP_PX,
  LABEL_H_PX,
  dotCenterOffsetY,
  hitBoxHeight,
} from './flatNodeMetrics';

describe('flat node metrics', () => {
  it('makes the dot bigger than the 20px isometric one', () => {
    expect(DOT_PX).toBe(28);
    expect(DOT_PX).toBeGreaterThan(20);
  });

  it('gives a hit box comfortably above the 44px touch minimum', () => {
    expect(hitBoxHeight()).toBeGreaterThanOrEqual(HIT_MIN_PX);
    expect(hitBoxHeight()).toBe(HIT_PAD_PX * 2 + LABEL_H_PX + LABEL_GAP_PX + DOT_PX);
  });

  it('places the dot centre so the node anchors exactly on its coordinate', () => {
    // Column runs pad, label, gap, dot, pad from the top of the hit box.
    expect(dotCenterOffsetY()).toBe(HIT_PAD_PX + LABEL_H_PX + LABEL_GAP_PX + DOT_PX / 2);
  });

  it('keeps the dot centre inside the hit box', () => {
    expect(dotCenterOffsetY()).toBeLessThan(hitBoxHeight());
    expect(dotCenterOffsetY()).toBeGreaterThan(0);
  });
});
