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

/**
 * Zoom is stored as a multiple of fit rather than an absolute scale, so a
 * resize or an orientation change re-derives it during render instead of
 * needing an effect to correct it afterwards. 1 is "whole scene visible".
 */
export function clampZoomMultiple(multiple) {
  if (!Number.isFinite(multiple)) return 1;
  return Math.min(MAX_ZOOM_MULTIPLE, Math.max(1, multiple));
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
