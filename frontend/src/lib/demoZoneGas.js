// Presentation-only environmental readings for the dashboard.
//
// The gas figures on screen are generated here, not measured. They replace the
// zone payload on its way into the store, so every consumer — the right
// sidebar, the analytics page and the alerts log — shows one consistent set of
// numbers. Nothing here is sent to the backend and nothing enters the stored
// history: this is display dressing for a demo, and switching it off restores
// the real sensor feed with no other change.
//
// Set DEMO_GAS_ENABLED to false to show live sensor data again.

export const DEMO_GAS_ENABLED = true;

// The readings drift on their own clock rather than only when telemetry
// arrives, so the panel keeps moving even while the backend is quiet.
export const DEMO_GAS_TICK_MS = 1500;

// Full-scale of each gauge, matching what the two consumers already divide by:
// RightSidebar.jsx and Environment.jsx both scale CH4 against 5.0 and CO
// against 150. Keep these in step with those files.
export const CH4_GAUGE_MAX = 5.0; // % LEL
export const CO_GAUGE_MAX = 150.0; // ppm

// How far each bar is allowed to fill, as a fraction of its own gauge. These
// are the knobs to turn if the bars look too lively or too dead.
//
// To make methane swing across its whole gauge instead — bar to 100%, status
// flipping through WARNING and DANGER — set CH4_MAX_FILL to 1.0.
export const CH4_MIN_FILL = 0.01; // bars hold in the very-low 1-5% band,
export const CH4_MAX_FILL = 0.05; // never resting at a dead zero
export const CO_MIN_FILL = 0.01;
export const CO_MAX_FILL = 0.05;

// Air quality is scored high-is-good on a 0-10 scale and displayed as a
// percentage; this band renders as GOOD 92-97%.
export const AQI_MIN = 9.2;
export const AQI_MAX = 9.7;

/**
 * Zones to show when the backend has reported none — because it is still
 * starting, unreachable, or simply not running. Without this the environmental
 * panel reads "NO ZONES REPORTING" and nothing moves, which is the one thing a
 * demo must not do. Matches the zone ids in backend/app.py so the display is
 * consistent the moment a real backend does connect.
 */
export const FALLBACK_ZONE_IDS = [
  'ALPHA_LEFT',
  'DELTA_CENTER',
  'BETA_RIGHT',
  'GAMMA_STAGE',
  'CENTER_PATH',
];

/** Stable per-zone seed, so two zones never move in lockstep. */
const seedOf = (zoneId) => {
  let hash = 0;
  for (let i = 0; i < zoneId.length; i += 1) {
    hash = (hash * 31 + zoneId.charCodeAt(i)) % 9973;
  }
  return hash;
};

/**
 * Smooth 0-1 wander. Two sine waves at incommensurate periods drift without
 * ever repeating on a visible cycle, which reads as a settling sensor rather
 * than an animation loop. Coefficients sum to 1, so the result stays in 0-1.
 */
const wander = (seed, tick, phase) => {
  const t = tick + phase + seed;
  return 0.5 + 0.5 * (0.6 * Math.sin(t / 7) + 0.4 * Math.sin(t / 11));
};

/**
 * One zone's generated reading. Pure — `tick` advances the wander, so the same
 * (zoneId, tick) always yields the same numbers.
 *
 * Status is pinned to SAFE rather than derived: the three gas figures move
 * independently here, so a derived status could contradict the AQI shown
 * beside it, and Alerts.jsx would log gas incidents that never happened.
 */
export function demoZoneReading(zoneId, tick) {
  const seed = seedOf(zoneId);
  return {
    ch4: Number((CH4_GAUGE_MAX * (CH4_MIN_FILL + (CH4_MAX_FILL - CH4_MIN_FILL) * wander(seed, tick, 0))).toFixed(2)),
    co: Number((CO_GAUGE_MAX * (CO_MIN_FILL + (CO_MAX_FILL - CO_MIN_FILL) * wander(seed, tick, 37))).toFixed(1)),
    aqi: Number((AQI_MIN + (AQI_MAX - AQI_MIN) * wander(seed, tick, 71)).toFixed(1)),
    status: 'SAFE',
    source: 'demo',
  };
}

let tick = 0;

/**
 * Replace the gas figures in a zone payload, keeping every other field the
 * backend sent, and advance the wander one step.
 *
 * Falls back to a standard zone list when the backend has reported nothing, so
 * the panel is populated and moving whether or not a backend is up.
 */
export function demoZoneGas(zones) {
  const ids = zones && Object.keys(zones).length ? Object.keys(zones) : FALLBACK_ZONE_IDS;
  tick += 1;
  const next = {};
  for (const zoneId of ids) {
    next[zoneId] = { ...(zones?.[zoneId] || {}), ...demoZoneReading(zoneId, tick) };
  }
  return next;
}
