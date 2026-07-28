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
