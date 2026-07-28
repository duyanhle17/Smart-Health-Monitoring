/**
 * Which visual tone a worker's map node takes.
 *
 * Mirrors the isometric map's precedence at IsometricMap.jsx:37-86 exactly, so
 * the two views can never disagree about how confident a position is. A health
 * alert outranks any position state; last-known is kept distinct from the
 * degraded family, because "we are holding an old fix" and "we have a fresh but
 * weak fix" are different things to an operator.
 *
 * Lives outside the component so the mapping can be unit-tested on its own, and
 * so the node file exports only a component.
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
