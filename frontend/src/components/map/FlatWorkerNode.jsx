import {
  DOT_PX,
  HIT_MIN_PX,
  HIT_PAD_PX,
  LABEL_GAP_PX,
  LABEL_H_PX,
  dotCenterOffsetY,
  hitBoxHeight,
} from '../../lib/flatNodeMetrics';
import { toneFor } from '../../lib/flatNodeTone';

const TONE = {
  NORMAL: { dot: 'bg-green-500 border-green-900', label: 'bg-green-900 border-green-400 text-white' },
  WARNING: { dot: 'bg-orange-500 border-orange-900', label: 'bg-orange-700 border-orange-200 text-white' },
  DANGER: { dot: 'bg-red-600 border-red-950', label: 'bg-red-700 border-red-300 text-white' },
  OFFLINE: { dot: 'bg-gray-700 border-gray-900', label: 'bg-gray-800 border-gray-600 text-gray-400' },
  LAST_KNOWN: { dot: 'bg-gray-500 border-gray-800', label: 'bg-gray-800 border-gray-300 text-white' },
  DEGRADED: { dot: 'bg-amber-500 border-amber-900', label: 'bg-amber-700 border-amber-100 text-white' },
};

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
