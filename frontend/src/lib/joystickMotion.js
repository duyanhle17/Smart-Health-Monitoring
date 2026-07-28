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
