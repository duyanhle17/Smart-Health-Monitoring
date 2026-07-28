# Mobile Admin Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `/admin` a phone-only presentation — a flat top-down map with nothing around it, 28 px worker dots whose name label shares the touch target, and a joystick for precise placement.

**Architecture:** All camera rotation is removed on this path, which is what makes the rest simple: at `rotateX(0)` nothing is foreshortened, so no billboarding is needed, and with no rotate gesture a touch on empty map is free to mean pan. Every piece of maths lives in a pure module under `src/lib/` so it can be tested without a layout engine; the React components stay thin. The desktop `IsometricMap.jsx` is not touched.

**Tech Stack:** React 19, Vite 7, Tailwind v4, zustand, Vitest + jsdom + @testing-library/react (added by Task 1).

## Global Constraints

- **Desktop behaviour must not change.** `frontend/src/components/map/IsometricMap.jsx` is never edited. `CommandLayout.jsx` and `AdminPanel.jsx` receive only guarded branches that a viewport ≥ 1024 px never enters.
- **Breakpoint:** mobile map mode applies below **1024 px** viewport width.
- **Preference key:** `localStorage` key `safework_admin_view`, values `'map'` or `'full'`.
- **Scene dimensions:** 1000 × 800 px for logical coordinates 0–100 on both axes (10 px per unit X, 8 px per unit Y).
- **Dot size:** 28 px. **Minimum touch target:** 44 px.
- **Joystick full-deflection speed:** 15 logical units per second.
- **Joystick leash:** a worker can be pushed at most **±20 logical units** on each axis from where it sat when the placement session began.
- **Jitter:** visual only, **5 px** amplitude, resampled every **120 ms**, applied **only to the worker currently being pushed**. It never reaches the committed coordinate, and no other worker jitters.
- **Joystick commit debounce:** 500 ms after the stick returns to centre.
- **Tap vs drag threshold on empty map:** 8 px.
- **Zoom range:** fit scale to 3× fit scale.
- Test files are colocated as `<name>.test.js` / `<name>.test.jsx` and import `describe`/`it`/`expect` explicitly from `vitest` (the config does not enable globals).
- Existing lint must keep passing for files this plan creates: `npm run lint` introduces no new errors. (The repo already has 6 pre-existing errors in files this plan does not touch; do not fix them here.)

---

### Task 1: Test harness and flat-map geometry

**Files:**
- Create: `frontend/vitest.config.js`
- Create: `frontend/src/lib/flatMapGeometry.js`
- Create: `frontend/src/lib/flatMapGeometry.test.js`
- Modify: `frontend/package.json` (devDependencies + `test` script)

**Interfaces:**
- Consumes: nothing.
- Produces: `SCENE_W_PX: number`, `SCENE_H_PX: number`, `PX_PER_UNIT_X: number`, `PX_PER_UNIT_Y: number`, `MAX_ZOOM_MULTIPLE: number`, `fitScale(viewportW: number, viewportH: number) => number`, `clampZoom(zoom: number, fit: number) => number`, `screenDeltaToLogical(dxPx: number, dyPx: number, zoom: number) => {dlx: number, dly: number}`, `clampLogical(x: number, y: number) => {x: number, y: number}`, `clampPan(panX: number, panY: number, zoom: number, viewportW: number, viewportH: number) => {x: number, y: number}`.

- [ ] **Step 1: Install the test dependencies**

```bash
cd frontend
npm install --save-dev vitest@^3 jsdom@^25 @testing-library/react@^16
```

- [ ] **Step 2: Add the test script to `frontend/package.json`**

In the `"scripts"` block, add these two entries after `"lint"`:

```json
    "test": "vitest run",
    "test:watch": "vitest",
```

- [ ] **Step 3: Create `frontend/vitest.config.js`**

A separate config so `vite.config.js` — which drives the production build — is left alone.

```js
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Kept separate from vite.config.js so the production build config is never
// touched by test setup. Globals stay off; test files import from 'vitest'
// explicitly, which keeps the existing eslint config working unchanged.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
  },
})
```

- [ ] **Step 4: Write the failing test at `frontend/src/lib/flatMapGeometry.test.js`**

```js
import { describe, it, expect } from 'vitest';
import {
  SCENE_W_PX,
  SCENE_H_PX,
  clampLogical,
  clampPan,
  clampZoom,
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

describe('clampZoom', () => {
  it('never goes below fit, so the scene is always fully reachable', () => {
    expect(clampZoom(0.1, 0.39)).toBeCloseTo(0.39, 5);
  });

  it('caps at three times fit', () => {
    expect(clampZoom(99, 0.39)).toBeCloseTo(1.17, 5);
  });

  it('passes through a value already in range', () => {
    expect(clampZoom(0.8, 0.39)).toBeCloseTo(0.8, 5);
  });
});

describe('screenDeltaToLogical', () => {
  it('converts pixel drag to logical units using the 10px/8px scene mapping', () => {
    // At zoom 1, 10 screen px across is one logical unit; 8 px down is one unit.
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
    const panned = clampPan(9999, 0, 1, 390, 844);
    expect(panned.x).toBeCloseTo(305, 5);
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
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/lib/flatMapGeometry.test.js`
Expected: FAIL — `Failed to resolve import "./flatMapGeometry"`.

- [ ] **Step 6: Write `frontend/src/lib/flatMapGeometry.js`**

```js
// Pure geometry for the flat (top-down) mobile map. No React and no DOM here,
// so the camera and touch behaviour can be tested without a layout engine.

// The backend addresses a 0-100 logical space on both axes. It renders at a
// fixed 1000x800 px, giving 10 px per unit across and 8 px down — the same
// mapping the isometric map uses, so a coordinate means the same thing in both.
export const SCENE_W_PX = 1000;
export const SCENE_H_PX = 800;
export const PX_PER_UNIT_X = SCENE_W_PX / 100;
export const PX_PER_UNIT_Y = SCENE_H_PX / 100;

export const MAX_ZOOM_MULTIPLE = 3;

/** Scale at which the whole scene is visible in the given viewport. */
export function fitScale(viewportW, viewportH) {
  if (!(viewportW > 0) || !(viewportH > 0)) return 1;
  return Math.min(viewportW / SCENE_W_PX, viewportH / SCENE_H_PX);
}

/** Zoom never drops below fit (the scene stays wholly visible) or above 3x fit. */
export function clampZoom(zoom, fit) {
  return Math.min(Math.max(zoom, fit), fit * MAX_ZOOM_MULTIPLE);
}

/**
 * Screen-pixel drag delta to logical-coordinate delta. Without camera rotation
 * this is two divisions; the isometric map needs six trigonometric steps to
 * undo its rotateX/rotateZ before it can do the same thing.
 */
export function screenDeltaToLogical(dxPx, dyPx, zoom) {
  return {
    dlx: dxPx / zoom / PX_PER_UNIT_X,
    dly: dyPx / zoom / PX_PER_UNIT_Y,
  };
}

/** Worker coordinates are 0-100 on both axes. */
export function clampLogical(x, y) {
  return {
    x: Math.min(100, Math.max(0, x)),
    y: Math.min(100, Math.max(0, y)),
  };
}

/**
 * Pan is clamped so a scene edge can never travel inside a viewport edge. The
 * scene is centred at rest, so the reachable range is half the overflow in each
 * direction; at fit scale there is no overflow and pan collapses to zero.
 */
export function clampPan(panX, panY, zoom, viewportW, viewportH) {
  const maxX = Math.max(0, (SCENE_W_PX * zoom - viewportW) / 2);
  const maxY = Math.max(0, (SCENE_H_PX * zoom - viewportH) / 2);
  return {
    x: Math.min(maxX, Math.max(-maxX, panX)),
    y: Math.min(maxY, Math.max(-maxY, panY)),
  };
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/lib/flatMapGeometry.test.js`
Expected: PASS — 13 tests.

- [ ] **Step 8: Verify the production build and lint still work**

Run: `cd frontend && npm run build && npm run lint 2>&1 | tail -3`
Expected: build succeeds; lint reports the same 6 pre-existing errors and no new ones.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.js frontend/src/lib/flatMapGeometry.js frontend/src/lib/flatMapGeometry.test.js
git commit -m "test: add vitest harness and flat-map geometry"
```

---

### Task 2: Joystick motion maths

**Files:**
- Create: `frontend/src/lib/joystickMotion.js`
- Create: `frontend/src/lib/joystickMotion.test.js`

**Interfaces:**
- Consumes: `clampLogical` from `src/lib/flatMapGeometry.js`.
- Produces: `STICK_RADIUS_PX: number`, `MAX_SPEED_UNITS_PER_S: number`, `DEAD_ZONE: number`, `LEASH_UNITS: number`, `JITTER_AMPLITUDE_PX: number`, `JITTER_STEP_MS: number`, `stickVector(dxPx: number, dyPx: number, radiusPx?: number) => {x: number, y: number}`, `isCentred(vector: {x: number, y: number}) => boolean`, `clampToLeash(anchor: {x: number, y: number}, position: {x: number, y: number}, leash?: number) => {x: number, y: number}`, `advancePosition(position: {x: number, y: number}, vector: {x: number, y: number}, dtMs: number, anchor?: {x: number, y: number} | null) => {x: number, y: number}`, `jitterOffset(tMs: number, amplitudePx?: number) => {x: number, y: number}`.

- [ ] **Step 1: Write the failing test at `frontend/src/lib/joystickMotion.test.js`**

```js
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
    const v = stickVector(0, -STICK_RADIUS_PX);
    expect(v.y).toBeCloseTo(-1, 5);
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
    const next = advancePosition({ x: 50, y: 50 }, { x: 0, y: -1 }, 1000);
    expect(next.y).toBeLessThan(50);
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
    const b = jitterOffset(JITTER_STEP_MS - 1);
    const c = jitterOffset(JITTER_STEP_MS + 1);
    expect(b).toEqual(a);
    expect(c).not.toEqual(a);
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/lib/joystickMotion.test.js`
Expected: FAIL — `Failed to resolve import "./joystickMotion"`.

- [ ] **Step 3: Write `frontend/src/lib/joystickMotion.js`**

```js
import { clampLogical } from './flatMapGeometry';

// Analog-stick maths for nudging the selected worker. Pure: the component only
// supplies pointer offsets and elapsed frame time.

/** Travel radius of the stick, in CSS pixels. */
export const STICK_RADIUS_PX = 48;

/** Speed at full deflection. 100 units / 15 is a ~6.7 s traverse of the map. */
export const MAX_SPEED_UNITS_PER_S = 15;

/** Deflections this small read as centre — a resting thumb still wobbles. */
export const DEAD_ZONE = 0.12;

/**
 * How far the joystick may push a worker from where it sat when the placement
 * session began, on each axis. Placement is a correction, not free teleporting.
 */
export const LEASH_UNITS = 20;

/**
 * Cosmetic wobble applied to the worker currently being pushed, so a
 * hand-placed dot reads like a live UWB fix rather than a frozen marker.
 *
 * This is presentation only. It is applied at render as a pixel offset and
 * never enters the coordinate sent to the backend, so a placement stays exactly
 * where the operator put it. Only the worker under the joystick wobbles; every
 * other dot keeps showing what the server reported.
 */
export const JITTER_AMPLITUDE_PX = 5;

/** Resample interval. Sample-and-hold is what makes it read as stutter. */
export const JITTER_STEP_MS = 120;

/** Deterministic 0-1 hash, so a given instant always renders the same offset. */
const hash01 = (n) => {
  const s = Math.sin(n * 12.9898) * 43758.5453;
  return s - Math.floor(s);
};

/**
 * Pointer offset from the stick centre to a direction vector inside the unit
 * disc. Past the stick radius the vector saturates instead of growing, so
 * dragging far away does not accelerate the worker without limit.
 */
export function stickVector(dxPx, dyPx, radiusPx = STICK_RADIUS_PX) {
  const distance = Math.hypot(dxPx, dyPx);
  if (distance === 0) return { x: 0, y: 0 };
  const magnitude = Math.min(1, distance / radiusPx);
  if (magnitude < DEAD_ZONE) return { x: 0, y: 0 };
  return { x: (dxPx / distance) * magnitude, y: (dyPx / distance) * magnitude };
}

/** True when the stick is centred, or inside the dead zone. */
export function isCentred(vector) {
  return vector.x === 0 && vector.y === 0;
}

/** Hold a position within the leash of its anchor, and within the map. */
export function clampToLeash(anchor, position, leash = LEASH_UNITS) {
  const bounded = clampLogical(position.x, position.y);
  return {
    x: Math.min(anchor.x + leash, Math.max(anchor.x - leash, bounded.x)),
    y: Math.min(anchor.y + leash, Math.max(anchor.y - leash, bounded.y)),
  };
}

/**
 * Advance a logical position by one animation frame. Pointer "up" is a negative
 * dy and logical y also grows downward, so the axes already agree — no
 * inversion is needed anywhere in this path.
 *
 * Passing an anchor keeps the worker on its leash; passing null lets it travel
 * the whole map, which is what direct dragging does.
 */
export function advancePosition(position, vector, dtMs, anchor = null) {
  const distance = (MAX_SPEED_UNITS_PER_S * dtMs) / 1000;
  const next = clampLogical(
    position.x + vector.x * distance,
    position.y + vector.y * distance
  );
  return anchor ? clampToLeash(anchor, next) : next;
}

/**
 * Cosmetic pixel offset for the worker under the joystick. Sample-and-hold:
 * one value is held for a step and then jumps, which is how a glitching UWB fix
 * actually behaves — smooth interpolation would read as animation, not noise.
 */
export function jitterOffset(tMs, amplitudePx = JITTER_AMPLITUDE_PX) {
  if (!amplitudePx) return { x: 0, y: 0 };
  const step = Math.floor(tMs / JITTER_STEP_MS);
  return {
    x: (hash01(step) * 2 - 1) * amplitudePx,
    y: (hash01(step + 1000) * 2 - 1) * amplitudePx,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/lib/joystickMotion.test.js`
Expected: PASS — 23 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/joystickMotion.js frontend/src/lib/joystickMotion.test.js
git commit -m "feat: joystick motion maths with leash and cosmetic jitter"
```

---

### Task 3: View-mode hook

**Files:**
- Create: `frontend/src/hooks/useMobileMapMode.js`
- Create: `frontend/src/hooks/useMobileMapMode.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `MOBILE_MAX_WIDTH: number`, `VIEW_PREF_KEY: string`, `resolveAdminView(width: number, preference: string | null) => 'map' | 'full'`, `readViewPreference() => string | null`, `writeViewPreference(value: string) => void`, and default export `useMobileMapMode() => {view: 'map' | 'full', setView: (v: 'map' | 'full') => void, width: number}`.

- [ ] **Step 1: Write the failing test at `frontend/src/hooks/useMobileMapMode.test.js`**

```js
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/hooks/useMobileMapMode.test.js`
Expected: FAIL — `Failed to resolve import "./useMobileMapMode"`.

- [ ] **Step 3: Write `frontend/src/hooks/useMobileMapMode.js`**

```js
import { useCallback, useEffect, useState } from 'react';

/** Below this viewport width the admin console shows the map-only view. */
export const MOBILE_MAX_WIDTH = 1024;

export const VIEW_PREF_KEY = 'safework_admin_view';

/**
 * A wide screen always gets the full console — an operator at a desk should
 * never be handed the stripped-down view. A narrow screen gets the map unless
 * the operator explicitly asked for the console, which they need on site for
 * UWB calibration.
 */
export function resolveAdminView(width, preference) {
  if (width >= MOBILE_MAX_WIDTH) return 'full';
  return preference === 'full' ? 'full' : 'map';
}

export const readViewPreference = () => {
  try {
    return localStorage.getItem(VIEW_PREF_KEY);
  } catch {
    return null; // private mode
  }
};

export const writeViewPreference = (value) => {
  try {
    localStorage.setItem(VIEW_PREF_KEY, value);
  } catch {
    /* private mode: the choice simply does not persist */
  }
};

export default function useMobileMapMode() {
  const [width, setWidth] = useState(() =>
    typeof window === 'undefined' ? MOBILE_MAX_WIDTH : window.innerWidth
  );
  const [preference, setPreference] = useState(readViewPreference);

  // The isometric map sizes itself once at mount and registers no resize
  // listener, so rotating a phone leaves its view wrong. Track width properly.
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('orientationchange', onResize);
    };
  }, []);

  const setView = useCallback((value) => {
    writeViewPreference(value);
    setPreference(value);
  }, []);

  return { view: resolveAdminView(width, preference), setView, width };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/hooks/useMobileMapMode.test.js`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useMobileMapMode.js frontend/src/hooks/useMobileMapMode.test.js
git commit -m "feat: admin view-mode hook with persisted preference"
```

---

### Task 4: Joystick component

**Files:**
- Create: `frontend/src/components/map/Joystick.jsx`
- Create: `frontend/src/components/map/Joystick.test.jsx`

**Interfaces:**
- Consumes: `STICK_RADIUS_PX`, `stickVector` from `src/lib/joystickMotion.js`.
- Produces: default export `Joystick({ onVector, onRelease, label })`. `onVector` is called with `{x, y}` on every pointer move while held and once with `{x: 0, y: 0}` on release. `onRelease` is called once per gesture, after the final `onVector`. Renders `data-testid="joystick"` on the base and `data-testid="joystick-knob"` on the knob.

- [ ] **Step 1: Write the failing test at `frontend/src/components/map/Joystick.test.jsx`**

```jsx
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/map/Joystick.test.jsx`
Expected: FAIL — `Failed to resolve import "./Joystick"`.

- [ ] **Step 3: Write `frontend/src/components/map/Joystick.jsx`**

```jsx
import { useCallback, useEffect, useRef, useState } from 'react';
import { STICK_RADIUS_PX, stickVector } from '../../lib/joystickMotion';

const BASE_PX = STICK_RADIUS_PX * 2 + 24;
const KNOB_PX = 56;

/**
 * Analog stick for nudging the selected worker. It reports a direction vector
 * and leaves the animation loop to the caller: a thumb held still fires no
 * further pointer events, so the caller must keep applying the last vector.
 *
 * `onRelease` fires once per gesture and is where the caller commits.
 */
export default function Joystick({ onVector, onRelease, label }) {
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const activeRef = useRef(false);
  const baseRef = useRef(null);

  const updateFrom = useCallback((clientX, clientY) => {
    const base = baseRef.current;
    if (!base) return;
    const rect = base.getBoundingClientRect();
    const vector = stickVector(
      clientX - (rect.left + rect.width / 2),
      clientY - (rect.top + rect.height / 2)
    );
    setKnob({ x: vector.x * STICK_RADIUS_PX, y: vector.y * STICK_RADIUS_PX });
    onVector(vector);
  }, [onVector]);

  const end = useCallback(() => {
    if (!activeRef.current) return;
    activeRef.current = false;
    setKnob({ x: 0, y: 0 });
    onVector({ x: 0, y: 0 });
    onRelease();
  }, [onVector, onRelease]);

  // A thumb routinely leaves the stick's own bounds mid-gesture, so movement
  // and release are tracked on the window rather than on the element.
  useEffect(() => {
    const move = (e) => {
      if (activeRef.current) updateFrom(e.clientX, e.clientY);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
  }, [updateFrom, end]);

  return (
    <div
      ref={baseRef}
      data-testid="joystick"
      onPointerDown={(e) => {
        e.stopPropagation();
        activeRef.current = true;
        updateFrom(e.clientX, e.clientY);
      }}
      className="relative rounded-full border-4 border-black bg-white/70 flex items-center justify-center"
      style={{ width: BASE_PX, height: BASE_PX, touchAction: 'none' }}
    >
      <span className="absolute -top-7 font-heavy uppercase text-[11px] whitespace-nowrap bg-black text-white px-2 py-0.5">
        {label}
      </span>
      <div
        data-testid="joystick-knob"
        className="rounded-full bg-black border-4 border-white pointer-events-none"
        style={{
          width: KNOB_PX,
          height: KNOB_PX,
          transform: `translate(${knob.x}px, ${knob.y}px)`,
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/components/map/Joystick.test.jsx`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/map/Joystick.jsx frontend/src/components/map/Joystick.test.jsx
git commit -m "feat: analog joystick component"
```

---

### Task 5: Flat worker node

**Files:**
- Create: `frontend/src/lib/flatNodeMetrics.js`
- Create: `frontend/src/lib/flatNodeMetrics.test.js`
- Create: `frontend/src/components/map/FlatWorkerNode.jsx`
- Create: `frontend/src/components/map/FlatWorkerNode.test.jsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: from `flatNodeMetrics.js` — `DOT_PX: number`, `LABEL_H_PX: number`, `LABEL_GAP_PX: number`, `HIT_PAD_PX: number`, `HIT_MIN_PX: number`, `hitBoxHeight() => number`, `dotCenterOffsetY() => number`. From `FlatWorkerNode.jsx` — named export `toneFor(worker: object) => string` and default export `FlatWorkerNode({ worker, displayName, left, top, selected, uncommitted, jitter, onPointerDown })` where `jitter` is `{x: number, y: number}` in pixels and defaults to no offset. The root carries `data-testid={'node-' + worker.worker_id}`, the dot carries `data-testid={'dot-' + worker.worker_id}`, the label carries `data-testid={'label-' + worker.worker_id}`.

- [ ] **Step 1: Write the failing metrics test at `frontend/src/lib/flatNodeMetrics.test.js`**

```js
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm test -- src/lib/flatNodeMetrics.test.js`
Expected: FAIL — `Failed to resolve import "./flatNodeMetrics"`.

- [ ] **Step 3: Write `frontend/src/lib/flatNodeMetrics.js`**

```js
// Fixed pixel geometry for a flat map node. Kept out of the component so the
// touch target can be asserted in a test — jsdom does no layout, so nothing
// can be measured from the rendered DOM.

/** Dot diameter. Up from the isometric map's 20 px. */
export const DOT_PX = 28;

/** Reserved height for the one-line name label above the dot. */
export const LABEL_H_PX = 20;

/** Gap between label and dot. */
export const LABEL_GAP_PX = 4;

/** Padding around the whole control, which is what buys the touch slack. */
export const HIT_PAD_PX = 8;

/** iOS and Android both put the minimum comfortable touch target here. */
export const HIT_MIN_PX = 44;

/**
 * The control is one column: pad, label, gap, dot, pad. Label and dot share a
 * single hit box, so touching either one picks up the worker.
 */
export const hitBoxHeight = () =>
  HIT_PAD_PX * 2 + LABEL_H_PX + LABEL_GAP_PX + DOT_PX;

/**
 * Distance from the top of the hit box down to the dot's centre. The box is
 * offset upward by this much so the dot — not the box — sits on the worker's
 * coordinate.
 */
export const dotCenterOffsetY = () =>
  HIT_PAD_PX + LABEL_H_PX + LABEL_GAP_PX + DOT_PX / 2;
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npm test -- src/lib/flatNodeMetrics.test.js`
Expected: PASS — 4 tests.

- [ ] **Step 5: Write the failing component test at `frontend/src/components/map/FlatWorkerNode.test.jsx`**

```jsx
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import FlatWorkerNode, { toneFor } from './FlatWorkerNode';
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
    const dot = screen.getByTestId('dot-WK_101');
    expect(dot.style.width).toBe(`${DOT_PX}px`);
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
    // The anchor itself must not move: only the rendering is offset.
    expect(node.style.left).toBe('500px');
    expect(node.style.top).toBe('400px');
  });
});
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd frontend && npm test -- src/components/map/FlatWorkerNode.test.jsx`
Expected: FAIL — `Failed to resolve import "./FlatWorkerNode"`.

- [ ] **Step 7: Write `frontend/src/components/map/FlatWorkerNode.jsx`**

```jsx
import {
  DOT_PX,
  HIT_MIN_PX,
  HIT_PAD_PX,
  LABEL_GAP_PX,
  LABEL_H_PX,
  dotCenterOffsetY,
  hitBoxHeight,
} from '../../lib/flatNodeMetrics';

const TONE = {
  NORMAL: { dot: 'bg-green-500 border-green-900', label: 'bg-green-900 border-green-400 text-white' },
  WARNING: { dot: 'bg-orange-500 border-orange-900', label: 'bg-orange-700 border-orange-200 text-white' },
  DANGER: { dot: 'bg-red-600 border-red-950', label: 'bg-red-700 border-red-300 text-white' },
  OFFLINE: { dot: 'bg-gray-700 border-gray-900', label: 'bg-gray-800 border-gray-600 text-gray-400' },
  LAST_KNOWN: { dot: 'bg-gray-500 border-gray-800', label: 'bg-gray-800 border-gray-300 text-white' },
  DEGRADED: { dot: 'bg-amber-500 border-amber-900', label: 'bg-amber-700 border-amber-100 text-white' },
};

/**
 * Mirrors the isometric map's precedence at IsometricMap.jsx:37-86 exactly, so
 * the two views can never disagree about how confident a position is. A health
 * alert outranks any position state; last-known is distinguished from the
 * degraded family.
 */
export function toneFor(worker) {
  if (worker.alert === 'WARNING') return 'WARNING';
  if (worker.alert === 'DANGER') return 'DANGER';
  if (worker.alert === 'OFFLINE') return 'OFFLINE';
  if (worker.location_last_known === true) return 'LAST_KNOWN';
  if (worker.location_stale === true) return 'DEGRADED';
  if (worker.location_degraded || worker.uwb?.degraded || worker.uwb?.geometry_mode === 'line') {
    return 'DEGRADED';
  }
  if (worker.uwb?.low_geometry || worker.uwb?.branch_ambiguous) return 'DEGRADED';
  return 'NORMAL';
}

/**
 * Dot plus name label as a single touch control. The whole column is one hit
 * box — touching the label picks up the worker exactly as touching the dot
 * does, which is the point: a 28 px dot alone is still a small target on a
 * phone, and on the isometric map everything around the dot is inert.
 */
export default function FlatWorkerNode({
  worker,
  displayName,
  left,
  top,
  selected,
  uncommitted,
  jitter,
  onPointerDown,
}) {
  const tone = TONE[toneFor(worker)];

  // Jitter is a render-time pixel offset, never part of `left`/`top`. The
  // coordinate the operator placed is what gets committed, wobble or not.
  const wobble = jitter && (jitter.x || jitter.y)
    ? `translate(${jitter.x}px, ${jitter.y}px)`
    : undefined;

  return (
    <div
      data-testid={`node-${worker.worker_id}`}
      className="absolute"
      style={{ left, top, transform: wobble, zIndex: selected ? 200 : 100 }}
    >
      <div
        data-testid={`hit-${worker.worker_id}`}
        onPointerDown={onPointerDown}
        className="flex flex-col items-center justify-start"
        style={{
          transform: `translate(-50%, -${dotCenterOffsetY()}px)`,
          minWidth: HIT_MIN_PX,
          height: hitBoxHeight(),
          paddingTop: HIT_PAD_PX,
          paddingLeft: HIT_PAD_PX,
          paddingRight: HIT_PAD_PX,
          touchAction: 'none',
          cursor: 'grab',
        }}
      >
        <span
          data-testid={`label-${worker.worker_id}`}
          className={`whitespace-nowrap border-2 px-2 font-heavy uppercase text-[11px] leading-none flex items-center ${tone.label}`}
          style={{ height: LABEL_H_PX, marginBottom: LABEL_GAP_PX }}
        >
          {displayName}
        </span>

        <span className="relative flex items-center justify-center">
          {selected && (
            <span
              data-testid={`ring-${worker.worker_id}`}
              className="absolute rounded-full border-4 border-black"
              style={{ width: DOT_PX + 16, height: DOT_PX + 16 }}
            />
          )}
          {uncommitted && (
            <span
              data-testid={`uncommitted-${worker.worker_id}`}
              className="absolute rounded-full border-2 border-dashed border-brand-red"
              style={{ width: DOT_PX + 28, height: DOT_PX + 28 }}
            />
          )}
          <span
            data-testid={`dot-${worker.worker_id}`}
            className={`rounded-full border-4 ${tone.dot}`}
            style={{ width: DOT_PX, height: DOT_PX }}
          />
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run it to verify it passes**

Run: `cd frontend && npm test -- src/components/map/FlatWorkerNode.test.jsx src/lib/flatNodeMetrics.test.js`
Expected: PASS — 16 tests.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/flatNodeMetrics.js frontend/src/lib/flatNodeMetrics.test.js frontend/src/components/map/FlatWorkerNode.jsx frontend/src/components/map/FlatWorkerNode.test.jsx
git commit -m "feat: flat worker node with label inside the touch target"
```

---

### Task 6: Flat map

**Files:**
- Create: `frontend/src/components/map/FlatMap.jsx`
- Create: `frontend/src/components/map/FlatMap.test.jsx`

**Interfaces:**
- Consumes: `fitScale`, `clampZoom`, `clampPan`, `clampLogical`, `screenDeltaToLogical`, `SCENE_W_PX`, `SCENE_H_PX`, `PX_PER_UNIT_X`, `PX_PER_UNIT_Y` from `src/lib/flatMapGeometry.js`; `FlatWorkerNode` from `./FlatWorkerNode`; `useStore`, `workerName` from `src/store.js`.
- Produces: default export `FlatMap({ selectedId, onSelect, overrides, uncommittedIds, jitterFor, onDragMove, onDragEnd })`. `overrides` is `{[workerId]: {x, y}}`; `uncommittedIds` is a `Set` of worker ids; `jitterFor` is `(workerId: string) => {x: number, y: number} | null`, called once per worker per render. `onDragMove(workerId, {x, y})` fires on every drag frame; `onDragEnd(workerId)` fires once on release. Renders `data-testid="flat-map-surface"` on the pannable surface and `data-testid="flat-map-scene"` on the transformed scene.

- [ ] **Step 1: Write the failing test at `frontend/src/components/map/FlatMap.test.jsx`**

```jsx
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
    expect(pos.x).toBeGreaterThan(50); // moved right
  });

  it('commits once when the drag ends', () => {
    const onDragEnd = vi.fn();
    renderMap({ onDragEnd });
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(screen.getByTestId('flat-map-surface'), { clientX: 140, clientY: 100 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));
    expect(onDragEnd).toHaveBeenCalledTimes(1);
    expect(onDragEnd).toHaveBeenCalledWith('WK_101');
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm test -- src/components/map/FlatMap.test.jsx`
Expected: FAIL — `Failed to resolve import "./FlatMap"`.

- [ ] **Step 3: Write `frontend/src/components/map/FlatMap.jsx`**

```jsx
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import useStore, { workerName } from '../../store';
import FlatWorkerNode from './FlatWorkerNode';
import {
  PX_PER_UNIT_X,
  PX_PER_UNIT_Y,
  SCENE_H_PX,
  SCENE_W_PX,
  clampLogical,
  clampPan,
  clampZoom,
  fitScale,
  screenDeltaToLogical,
} from '../../lib/flatMapGeometry';

/** Below this movement a gesture on empty map is a tap, above it a pan. */
const TAP_THRESHOLD_PX = 8;

const LIVE_UWB_ANCHOR_IDS = ['ANC_LEFT', 'ANC_RIGHT'];

/**
 * Top-down map for the phone. No camera rotation at all: at rotateX(0) nothing
 * is foreshortened, so dots are true circles at a constant screen size, and
 * with no rotate gesture a drag on empty map is free to mean pan.
 */
export default function FlatMap({
  selectedId,
  onSelect,
  overrides,
  uncommittedIds,
  jitterFor,
  onDragMove,
  onDragEnd,
}) {
  const workers = useStore((s) => s.workers);
  const anchors = useStore((s) => s.anchors);
  const personnel = useStore((s) => s.personnel);
  const hiddenNodes = useStore((s) => s.hiddenNodes);
  const mapTheme = useStore((s) => s.mapTheme);

  const surfaceRef = useRef(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const dragRef = useRef(null);
  const panRef = useRef(null);
  const pinchRef = useRef(null);
  const pointersRef = useRef(new Map());

  const fit = fitScale(viewport.w, viewport.h);

  // Measure on mount and on every resize or orientation change. The isometric
  // map computes its zoom once from window.innerWidth and never listens, which
  // is why rotating a phone leaves it wrong.
  useLayoutEffect(() => {
    const measure = () => {
      const el = surfaceRef.current;
      const w = el?.clientWidth || window.innerWidth;
      const h = el?.clientHeight || window.innerHeight;
      setViewport({ w, h });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('orientationchange', measure);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('orientationchange', measure);
    };
  }, []);

  // Snap to fit whenever the viewport changes shape, and re-clamp pan so a
  // rotation cannot leave the scene dragged off screen.
  useEffect(() => {
    if (!(viewport.w > 0)) return;
    const nextFit = fitScale(viewport.w, viewport.h);
    setZoom((z) => clampZoom(z < nextFit ? nextFit : z, nextFit));
    setPan((p) => clampPan(p.x, p.y, Math.max(nextFit, zoom), viewport.w, viewport.h));
    // zoom is deliberately excluded: this effect reacts to viewport shape only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewport.w, viewport.h]);

  const applyZoom = useCallback((next) => {
    setZoom(() => {
      const clamped = clampZoom(next, fit);
      setPan((p) => clampPan(p.x, p.y, clamped, viewport.w, viewport.h));
      return clamped;
    });
  }, [fit, viewport.w, viewport.h]);

  const zoomIn = () => applyZoom(zoom * 1.4);
  const zoomOut = () => applyZoom(zoom / 1.4);
  const resetView = () => {
    applyZoom(fit);
    setPan({ x: 0, y: 0 });
  };

  const startWorkerDrag = useCallback((e, worker) => {
    e.stopPropagation();
    onSelect(worker.worker_id);
    const base = overrides[worker.worker_id] || { x: worker.x, y: worker.y };
    dragRef.current = {
      id: worker.worker_id,
      startX: e.clientX,
      startY: e.clientY,
      origX: Number(base.x) || 0,
      origY: Number(base.y) || 0,
    };
  }, [onSelect, overrides]);

  const handlePointerDown = (e) => {
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (dragRef.current) return;

    if (pointersRef.current.size === 2) {
      const [a, b] = [...pointersRef.current.values()];
      pinchRef.current = { distance: Math.hypot(a.x - b.x, a.y - b.y), zoom };
      panRef.current = null;
      return;
    }
    panRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: pan.x,
      origY: pan.y,
      moved: 0,
    };
  };

  const handlePointerMove = (e) => {
    if (pointersRef.current.has(e.pointerId)) {
      pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    const drag = dragRef.current;
    if (drag) {
      const { dlx, dly } = screenDeltaToLogical(
        e.clientX - drag.startX,
        e.clientY - drag.startY,
        zoom
      );
      onDragMove(drag.id, clampLogical(drag.origX + dlx, drag.origY + dly));
      return;
    }

    if (pinchRef.current && pointersRef.current.size === 2) {
      const [a, b] = [...pointersRef.current.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchRef.current.distance > 0) {
        applyZoom((pinchRef.current.zoom * distance) / pinchRef.current.distance);
      }
      return;
    }

    const panning = panRef.current;
    if (panning) {
      const dx = e.clientX - panning.startX;
      const dy = e.clientY - panning.startY;
      panning.moved = Math.max(panning.moved, Math.hypot(dx, dy));
      setPan(clampPan(panning.origX + dx, panning.origY + dy, zoom, viewport.w, viewport.h));
    }
  };

  const handlePointerUp = () => {
    if (dragRef.current) {
      const { id } = dragRef.current;
      dragRef.current = null;
      pointersRef.current.clear();
      panRef.current = null;
      pinchRef.current = null;
      onDragEnd(id);
      return;
    }

    // A short gesture on empty map is a tap and clears the selection; a longer
    // one was a pan and must leave the selection — and therefore the joystick —
    // exactly where it was.
    if (panRef.current && panRef.current.moved < TAP_THRESHOLD_PX && selectedId) {
      onSelect(null);
    }
    pointersRef.current.clear();
    panRef.current = null;
    pinchRef.current = null;
  };

  const displayAnchors = LIVE_UWB_ANCHOR_IDS
    .map((id) => anchors.find((a) => a.id === id))
    .filter(Boolean)
    .filter((a) => !hiddenNodes[a.id]);

  const displayWorkers = Object.values(workers).filter((w) => !hiddenNodes[w.worker_id]);

  return (
    <div
      ref={surfaceRef}
      data-testid="flat-map-surface"
      className="relative w-full h-full overflow-hidden bg-gray-200 flex items-center justify-center"
      style={{ touchAction: 'none' }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div
        data-testid="flat-map-scene"
        className="relative"
        style={{
          width: SCENE_W_PX,
          height: SCENE_H_PX,
          flex: '0 0 auto',
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: 'center center',
        }}
      >
        <div className={mapTheme === 'MINE' ? 'mine-ground' : 'site-ground'} />

        {displayAnchors.map((a) => (
          <div
            key={a.id}
            data-testid={`anchor-${a.id}`}
            className="absolute flex flex-col items-center"
            style={{
              left: `${a.x * PX_PER_UNIT_X}px`,
              top: `${a.y * PX_PER_UNIT_Y}px`,
              transform: 'translate(-50%, -50%)',
              zIndex: 90,
            }}
          >
            <span className="bg-brand-yellow text-black border-2 border-black px-2 font-heavy uppercase text-[11px] leading-none mb-1">
              {a.id}
            </span>
            <span className="bg-brand-yellow border-4 border-black" style={{ width: 24, height: 24 }} />
          </div>
        ))}

        {displayWorkers.map((w) => {
          const pos = overrides[w.worker_id] || { x: w.x, y: w.y };
          return (
            <FlatWorkerNode
              key={w.worker_id}
              worker={w}
              displayName={workerName(personnel, w.worker_id)}
              left={`${(Number(pos.x) || 0) * PX_PER_UNIT_X}px`}
              top={`${(Number(pos.y) || 0) * PX_PER_UNIT_Y}px`}
              selected={selectedId === w.worker_id}
              uncommitted={uncommittedIds.has(w.worker_id)}
              jitter={jitterFor(w.worker_id)}
              onPointerDown={(e) => startWorkerDrag(e, w)}
            />
          );
        })}
      </div>

      {displayWorkers.length === 0 && (
        <div
          data-testid="flat-map-empty"
          className="absolute inset-x-0 top-1/2 -translate-y-1/2 text-center font-heavy uppercase text-xs text-gray-600 pointer-events-none"
        >
          Waiting for telemetry
        </div>
      )}

      <div className="absolute top-4 right-4 z-30 flex flex-col">
        <button
          onClick={zoomIn}
          aria-label="Zoom in"
          className="w-12 h-12 bg-white border-4 border-black font-heavy text-lg"
        >
          +
        </button>
        <button
          onClick={zoomOut}
          aria-label="Zoom out"
          className="w-12 h-12 bg-white border-4 border-t-0 border-black font-heavy text-lg"
        >
          −
        </button>
        <button
          onClick={resetView}
          aria-label="Reset view"
          className="w-12 h-12 mt-3 bg-white border-4 border-black font-heavy text-[10px] uppercase"
        >
          Fit
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npm test -- src/components/map/FlatMap.test.jsx`
Expected: PASS — 13 tests.

- [ ] **Step 5: Run the whole suite and lint**

Run: `cd frontend && npm test && npm run lint 2>&1 | tail -3`
Expected: all tests pass; lint shows the same 6 pre-existing errors and no new ones.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/map/FlatMap.jsx frontend/src/components/map/FlatMap.test.jsx
git commit -m "feat: flat top-down map with pan, pinch and direct drag"
```

---

### Task 7: Mobile admin map page

**Files:**
- Create: `frontend/src/pages/MobileAdminMap.jsx`
- Create: `frontend/src/pages/MobileAdminMap.test.jsx`
- Modify: `frontend/src/pages/AdminPanel.jsx` (export `PinGate` — add the `export` keyword only)

**Interfaces:**
- Consumes: `FlatMap` from `src/components/map/FlatMap.jsx`; `Joystick` from `src/components/map/Joystick.jsx`; `advancePosition`, `isCentred`, `jitterOffset` from `src/lib/joystickMotion.js`; `PinGate` from `src/pages/AdminPanel.jsx`; `adminPost`, `clearAdminPin`, `getAdminPin`, `verifyAdminPin` from `src/lib/adminApi.js`; `useStore`, `workerName` from `src/store.js`.
- Produces: `COMMIT_DEBOUNCE_MS: number` (named export) and default export `MobileAdminMap({ onOpenFullConsole })`.

- [ ] **Step 1: Export `PinGate` from `frontend/src/pages/AdminPanel.jsx`**

Change line 7 from:

```jsx
function PinGate({ onUnlocked }) {
```

to:

```jsx
export function PinGate({ onUnlocked }) {
```

Nothing else in the file changes. `AdminPanel` keeps using it exactly as before.

- [ ] **Step 2: Write the failing test at `frontend/src/pages/MobileAdminMap.test.jsx`**

```jsx
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MobileAdminMap, { COMMIT_DEBOUNCE_MS } from './MobileAdminMap';
import useStore from '../store';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

beforeEach(() => {
  useStore.setState({
    workers: {
      WK_101: { worker_id: 'WK_101', alert: 'NORMAL', x: 50, y: 50, location_valid: true },
    },
    anchors: [],
    personnel: [],
    hiddenNodes: {},
    mapTheme: 'SITE',
  });
  window.innerWidth = 390;
  window.innerHeight = 844;
  sessionStorage.clear();
});

/** The console re-verifies the PIN against the backend on every mount. */
const mockBackend = (overrides = {}) =>
  vi.spyOn(globalThis, 'fetch').mockImplementation((url, init) => {
    const path = String(url);
    if (path.includes('/api/admin/verify')) {
      return Promise.resolve({ ok: overrides.pinOk !== false, status: 200, json: async () => ({}) });
    }
    if (path.includes('/api/admin/node')) {
      overrides.onNodePost?.(JSON.parse(init.body));
      return Promise.resolve({ ok: overrides.saveOk !== false, status: overrides.saveOk === false ? 500 : 200, json: async () => ({}) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });

const renderPage = (props = {}) =>
  render(
    <MemoryRouter>
      <MobileAdminMap onOpenFullConsole={props.onOpenFullConsole || (() => {})} />
    </MemoryRouter>
  );

describe('MobileAdminMap', () => {
  it('shows the PIN gate before the map when the backend rejects the stored PIN', async () => {
    mockBackend({ pinOk: false });
    renderPage();
    await waitFor(() => expect(screen.getByText('ADMIN CONSOLE')).toBeTruthy());
    expect(screen.queryByTestId('flat-map-surface')).toBe(null);
  });

  it('shows the map once the PIN verifies', async () => {
    mockBackend();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
  });

  it('keeps the joystick hidden until a worker is selected', async () => {
    mockBackend();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
    expect(screen.queryByTestId('joystick')).toBe(null);

    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));

    await waitFor(() => expect(screen.getByTestId('joystick')).toBeTruthy());
  });

  it('offers a way back to the full console for field calibration', async () => {
    const onOpenFullConsole = vi.fn();
    mockBackend();
    renderPage({ onOpenFullConsole });
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
    fireEvent.click(screen.getByTestId('open-full-console'));
    expect(onOpenFullConsole).toHaveBeenCalledTimes(1);
  });

  it('renders nothing but the map, its controls and the console button', async () => {
    mockBackend();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());
    // No header, footer ticker, sidebar or alarm banner belongs on this screen.
    expect(screen.queryByText('SYSTEM_LOGS')).toBe(null);
    expect(screen.queryByText('PERSONNEL')).toBe(null);
    expect(screen.queryByText('NETWORK')).toBe(null);
  });

  it('debounces the joystick into a single save after the stick recentres', async () => {
    const posts = [];
    mockBackend({ onNodePost: (body) => posts.push(body) });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());

    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));
    await waitFor(() => expect(screen.getByTestId('joystick')).toBeTruthy());

    vi.useFakeTimers();
    const base = screen.getByTestId('joystick');
    base.getBoundingClientRect = () => ({
      left: 0, top: 0, width: 120, height: 120, right: 120, bottom: 120, x: 0, y: 0,
    });

    // Hold the stick right for a while: no save should fire while it is held.
    fireEvent.pointerDown(base, { clientX: 120, clientY: 60 });
    act(() => { vi.advanceTimersByTime(2000); });
    expect(posts.length).toBe(0);

    // Release, then let the debounce elapse: exactly one save.
    fireEvent.pointerUp(window);
    act(() => { vi.advanceTimersByTime(COMMIT_DEBOUNCE_MS + 50); });
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0].worker_id).toBe('WK_101');
  });

  it('keeps the joystick within twenty units of where the worker started', async () => {
    const posts = [];
    mockBackend({ onNodePost: (body) => posts.push(body) });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());

    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 0, clientY: 0 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));
    await waitFor(() => expect(screen.getByTestId('joystick')).toBeTruthy());

    const base = screen.getByTestId('joystick');
    base.getBoundingClientRect = () => ({
      left: 0, top: 0, width: 120, height: 120, right: 120, bottom: 120, x: 0, y: 0,
    });

    // Hold hard right for 1.6 s. At 15 units/s that is 24 units of travel, so
    // the 20-unit leash has to bind — a shorter hold would pass either way.
    fireEvent.pointerDown(base, { clientX: 120, clientY: 60 });
    await new Promise((resolve) => setTimeout(resolve, 1600));
    fireEvent.pointerUp(window);

    await waitFor(() => expect(posts.length).toBe(1));
    expect(Number(posts[0].x)).toBeGreaterThan(50); // it did move
    expect(Number(posts[0].x)).toBeLessThanOrEqual(70); // but the leash held
  }, 10000);

  it('does not let jitter reach the coordinate that is saved', async () => {
    const posts = [];
    mockBackend({ onNodePost: (body) => posts.push(body) });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());

    // Select but never push: the committed coordinate must be the clean one.
    fireEvent.pointerDown(screen.getByTestId('dot-WK_101'), { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(screen.getByTestId('flat-map-surface'), { clientX: 100, clientY: 100 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));

    await waitFor(() => expect(posts.length).toBe(1));
    expect(Number(posts[0].x)).toBeCloseTo(50, 1);
    expect(Number(posts[0].y)).toBeCloseTo(50, 1);
  });

  it('marks the dot uncommitted when the save fails, instead of snapping it back', async () => {
    mockBackend({ saveOk: false });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('flat-map-surface')).toBeTruthy());

    const dot = screen.getByTestId('dot-WK_101');
    fireEvent.pointerDown(dot, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(screen.getByTestId('flat-map-surface'), { clientX: 160, clientY: 100 });
    fireEvent.pointerUp(screen.getByTestId('flat-map-surface'));

    await waitFor(() => expect(screen.getByTestId('uncommitted-WK_101')).toBeTruthy());
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npm test -- src/pages/MobileAdminMap.test.jsx`
Expected: FAIL — `Failed to resolve import "./MobileAdminMap"`.

- [ ] **Step 4: Write `frontend/src/pages/MobileAdminMap.jsx`**

```jsx
import { useCallback, useEffect, useRef, useState } from 'react';
import FlatMap from '../components/map/FlatMap';
import Joystick from '../components/map/Joystick';
import { PinGate } from './AdminPanel';
import { advancePosition, isCentred, jitterOffset } from '../lib/joystickMotion';
import { adminPost, clearAdminPin, getAdminPin, verifyAdminPin } from '../lib/adminApi';
import useStore, { workerName } from '../store';

/** One save fires this long after the stick returns to centre. */
export const COMMIT_DEBOUNCE_MS = 500;

/**
 * The phone presentation of the admin console: a flat map and nothing else.
 *
 * The vitals alarm banner is deliberately absent — this screen is a placement
 * tool, not a monitoring station, and the operator was told so. Monitoring
 * stays on the desktop dashboard.
 */
export default function MobileAdminMap({ onOpenFullConsole }) {
  const workers = useStore((s) => s.workers);
  const personnel = useStore((s) => s.personnel);

  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [uncommittedIds, setUncommittedIds] = useState(new Set());

  const vectorRef = useRef({ x: 0, y: 0 });
  const frameRef = useRef(null);
  const commitTimerRef = useRef(null);
  const overridesRef = useRef(overrides);
  overridesRef.current = overrides;

  // Where the selected worker sat when this placement session began. The
  // joystick is leashed to it, so a long push corrects a position rather than
  // teleporting the worker across the site.
  const anchorRef = useRef(null);

  // Cosmetic wobble on the worker under the joystick. Held in state purely so
  // the frame loop can repaint it; it never touches the committed coordinate.
  const [jitter, setJitter] = useState(null);

  // The stored PIN is a convenience, not an authorization: re-verify against
  // the backend on mount, exactly as the desktop console does.
  useEffect(() => {
    verifyAdminPin(getAdminPin())
      .then((ok) => setUnlocked(ok))
      .catch(() => setUnlocked(false))
      .finally(() => setChecking(false));
  }, []);

  const commit = useCallback(async (workerId) => {
    const position = overridesRef.current[workerId];
    if (!position) return;
    try {
      const res = await adminPost('/api/admin/node', {
        worker_id: workerId,
        x: position.x.toFixed(1),
        y: position.y.toFixed(1),
      });
      if (res.status === 403) {
        clearAdminPin();
        setUnlocked(false);
        return;
      }
      if (!res.ok) {
        // Keep the operator's placement on screen and flag it. Snapping the dot
        // back without a word would read as "saved".
        setUncommittedIds((prev) => new Set(prev).add(workerId));
        return;
      }
      setUncommittedIds((prev) => {
        const next = new Set(prev);
        next.delete(workerId);
        return next;
      });
      // The backend override now owns the coordinate; drop the local overlay so
      // the next socket update renders server truth.
      setOverrides((prev) => {
        const next = { ...prev };
        delete next[workerId];
        return next;
      });
    } catch {
      setUncommittedIds((prev) => new Set(prev).add(workerId));
    }
  }, []);

  const scheduleCommit = useCallback((workerId) => {
    clearTimeout(commitTimerRef.current);
    commitTimerRef.current = setTimeout(() => commit(workerId), COMMIT_DEBOUNCE_MS);
  }, [commit]);

  // Anchor the leash the moment a worker is selected, and drop any wobble left
  // over from the previous selection.
  useEffect(() => {
    if (!selectedId) {
      anchorRef.current = null;
      setJitter(null);
      return;
    }
    const worker = useStore.getState().workers[selectedId];
    const from = overridesRef.current[selectedId] || worker || { x: 0, y: 0 };
    anchorRef.current = { x: Number(from.x) || 0, y: Number(from.y) || 0 };
  }, [selectedId]);

  // A held thumb fires no further pointer events, so the stick's last vector is
  // applied every frame here rather than on input. The same loop drives the
  // wobble, which only runs while the stick is actually deflected.
  useEffect(() => {
    if (!selectedId) return undefined;
    let last = performance.now();
    const step = (now) => {
      const dtMs = now - last;
      last = now;
      const vector = vectorRef.current;
      if (isCentred(vector)) {
        setJitter(null);
      } else {
        setJitter(jitterOffset(now));
        setOverrides((prev) => {
          const worker = useStore.getState().workers[selectedId];
          if (!worker) return prev;
          const from = prev[selectedId] || { x: Number(worker.x) || 0, y: Number(worker.y) || 0 };
          return {
            ...prev,
            [selectedId]: advancePosition(from, vector, dtMs, anchorRef.current),
          };
        });
      }
      frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameRef.current);
  }, [selectedId]);

  // Only the worker under the joystick wobbles. Every other dot keeps showing
  // exactly what the server reported.
  const jitterFor = useCallback(
    (workerId) => (workerId === selectedId ? jitter : null),
    [selectedId, jitter]
  );

  useEffect(() => () => clearTimeout(commitTimerRef.current), []);

  const handleDragMove = useCallback((workerId, position) => {
    setOverrides((prev) => ({ ...prev, [workerId]: position }));
  }, []);

  const handleDragEnd = useCallback((workerId) => {
    clearTimeout(commitTimerRef.current);
    commit(workerId);
  }, [commit]);

  if (checking) {
    return (
      <div className="w-full h-full flex justify-center items-center bg-gray-100">
        <span className="font-heavy uppercase text-xs tracking-widest text-gray-400">
          Checking admin access…
        </span>
      </div>
    );
  }
  if (!unlocked) return <PinGate onUnlocked={() => setUnlocked(true)} />;

  const selectedLabel = selectedId ? workerName(personnel, selectedId) : '';
  const selectionIsLive = Boolean(selectedId && workers[selectedId]);

  return (
    <div className="w-full h-full relative bg-gray-200 overflow-hidden">
      <FlatMap
        selectedId={selectedId}
        onSelect={setSelectedId}
        overrides={overrides}
        uncommittedIds={uncommittedIds}
        jitterFor={jitterFor}
        onDragMove={handleDragMove}
        onDragEnd={handleDragEnd}
      />

      <button
        data-testid="open-full-console"
        onClick={onOpenFullConsole}
        className="absolute top-4 left-4 z-30 bg-white border-4 border-black px-3 py-2 font-heavy uppercase text-[10px] tracking-widest"
      >
        Console
      </button>

      {selectionIsLive && (
        <div className="absolute bottom-8 left-6 z-30">
          <Joystick
            label={selectedLabel}
            onVector={(vector) => { vectorRef.current = vector; }}
            onRelease={() => scheduleCommit(selectedId)}
          />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd frontend && npm test -- src/pages/MobileAdminMap.test.jsx`
Expected: PASS — 9 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/MobileAdminMap.jsx frontend/src/pages/MobileAdminMap.test.jsx frontend/src/pages/AdminPanel.jsx
git commit -m "feat: mobile admin map page with joystick placement"
```

---

### Task 8: Wire into the admin route

**Files:**
- Modify: `frontend/src/components/layout/CommandLayout.jsx`
- Modify: `frontend/src/pages/AdminPanel.jsx`
- Create: `frontend/src/pages/AdminPanel.mobile.test.jsx`

**Interfaces:**
- Consumes: `useMobileMapMode` from `src/hooks/useMobileMapMode.js`; `MobileAdminMap` from `src/pages/MobileAdminMap.jsx`.
- Produces: nothing new. `/admin` renders the map-only view below 1024 px and the unchanged console at or above it.

- [ ] **Step 1: Write the failing test at `frontend/src/pages/AdminPanel.mobile.test.jsx`**

```jsx
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
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
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm test -- src/pages/AdminPanel.mobile.test.jsx`
Expected: FAIL — the phone-width test finds no `flat-map-surface`; `AdminPanel` still renders the console at every width.

- [ ] **Step 3: Add the guarded branch to `frontend/src/pages/AdminPanel.jsx`**

Add these two imports beside the existing ones at the top of the file:

```jsx
import useMobileMapMode from '../hooks/useMobileMapMode';
import MobileAdminMap from './MobileAdminMap';
```

Then, immediately after the existing `const hiddenNodes = useStore(s => s.hiddenNodes);` line, add:

```jsx
  // Below 1024 px the console becomes a map-only placement tool. A desktop
  // viewport never reaches this branch, so the console below is unchanged.
  const { view, setView } = useMobileMapMode();
```

And immediately before the existing `if (checking) {` block, add:

```jsx
  if (view === 'map') {
    return <MobileAdminMap onOpenFullConsole={() => setView('full')} />;
  }
```

Hooks stay above the early return, so hook order is unconditional and stable.

- [ ] **Step 4: Add the guarded branch to `frontend/src/components/layout/CommandLayout.jsx`**

Replace the whole file with:

```jsx
import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import FooterTicker from './FooterTicker';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';
import VitalsAlarmBanner from './VitalsAlarmBanner';
import useWorkerData from '../../hooks/useWorkerData';
import useMobileMapMode from '../../hooks/useMobileMapMode';

export default function CommandLayout() {
  useWorkerData(); // Activate global polling
  const location = useLocation();
  const { view } = useMobileMapMode();
  const isDashboard = location.pathname === '/dashboard';

  // The phone admin view is the map and nothing else, so it gets the whole
  // viewport with no chrome around it. Every other route, and every desktop
  // viewport, renders the layout exactly as before.
  const isMobileAdminMap = location.pathname === '/admin' && view === 'map';
  if (isMobileAdminMap) {
    return (
      <div className="font-body text-black overflow-hidden h-screen bg-gray-100">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="font-body text-black overflow-hidden h-screen flex flex-col bg-gray-100">
      <Header />
      <VitalsAlarmBanner />

      <main className="flex flex-1 min-h-0 overflow-hidden relative">
        {/* Only show sidebars on the dashboard or if we want them globally */}
        {isDashboard && <LeftSidebar />}

        {/* Main Content Area */}
        <section className="flex-1 flex flex-col overflow-hidden border-r-4 border-black">
          <Outlet />
        </section>

        {isDashboard && <RightSidebar />}
      </main>

      <FooterTicker />
    </div>
  );
}
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd frontend && npm test -- src/pages/AdminPanel.mobile.test.jsx`
Expected: PASS — 4 tests.

- [ ] **Step 6: Run the whole suite, lint and build**

Run: `cd frontend && npm test && npm run lint 2>&1 | tail -3 && npm run build 2>&1 | tail -5`
Expected: every test passes; lint shows the same 6 pre-existing errors and no new ones; the build succeeds.

- [ ] **Step 7: Verify the desktop path by hand**

Run: `cd frontend && npm run dev`

Then, in a browser at a window width above 1024 px, open `/admin` and confirm the two-column console with the isometric map is exactly as before: the worker cards, fall diagnostics, UWB calibration, manual override and visibility toggles all render, and dragging a worker on the isometric map still works.

Narrow the window below 1024 px and confirm the view switches to the flat map with no chrome; widen it again and confirm the console returns.

Then, on the narrow view, confirm the placement feel by hand — this is the part no test can judge:

- Touch a worker's **name label**, not the dot, and confirm it picks up.
- Push the joystick and hold: the dot should stop about a fifth of the map from where it began, and stutter while moving. Judge whether 5 px of wobble every 120 ms looks like signal noise or like a rendering fault, and whether 15 units/s feels right. All three are single constants at the top of `src/lib/joystickMotion.js`.
- Release and confirm the wobble stops and the dot settles on a clean position.
- Confirm no other worker on screen wobbles.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/layout/CommandLayout.jsx frontend/src/pages/AdminPanel.jsx frontend/src/pages/AdminPanel.mobile.test.jsx
git commit -m "feat: route /admin to the map-only view below 1024px"
```

---

## Deferred, with reasons

- **`fall_status === 'FALL'` does not colour a map node red.** `toneFor` mirrors `IsometricMap.jsx:37-86` exactly, and the isometric map keys only on `worker.alert`. Diverging here would make the two views disagree about the same worker. Worth fixing in both at once, as its own change.
- **No vitals alarm on the phone.** Chosen deliberately; recorded in the spec.
- **No "demo mode" badge for the jitter.** The wobble is scoped as tightly as it can be — render-only, one worker, only while the stick is deflected — but it still makes a hand-placed dot read as a live fix, on a screen that deliberately shows no position-confidence badges. Before this build goes to a live site it wants a visible demo indicator, or the jitter behind a flag. Out of scope here; recorded in the spec.
- **The 6 pre-existing lint errors** in `FooterTicker.jsx`, `RightSidebar.jsx`, `IsometricMap.jsx` and `vite.config.js` are untouched — they are outside this feature.
