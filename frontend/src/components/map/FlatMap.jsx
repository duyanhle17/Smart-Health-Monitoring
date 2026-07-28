import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import useStore, { workerName } from '../../store';
import FlatWorkerNode from './FlatWorkerNode';
import {
  PX_PER_UNIT_X,
  PX_PER_UNIT_Y,
  SCENE_H_PX,
  SCENE_W_PX,
  clampLogical,
  clampPan,
  clampZoomMultiple,
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

  // Zoom is held as a multiple of fit, and pan is clamped during render rather
  // than stored pre-clamped. Both then re-derive themselves when the viewport
  // changes shape, so rotating the phone needs no correcting effect.
  const [zoomMultiple, setZoomMultiple] = useState(1);
  const [rawPan, setRawPan] = useState({ x: 0, y: 0 });

  const dragRef = useRef(null);
  const panRef = useRef(null);
  const pinchRef = useRef(null);
  const pointersRef = useRef(new Map());

  const fit = fitScale(viewport.w, viewport.h);
  const zoom = fit * zoomMultiple;
  const pan = clampPan(rawPan.x, rawPan.y, zoom, viewport.w, viewport.h);

  // Measure on mount and on every resize or orientation change. The isometric
  // map computes its zoom once from window.innerWidth and never listens, which
  // is why rotating a phone leaves it wrong.
  useLayoutEffect(() => {
    const measure = () => {
      const el = surfaceRef.current;
      setViewport({
        w: el?.clientWidth || window.innerWidth,
        h: el?.clientHeight || window.innerHeight,
      });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('orientationchange', measure);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('orientationchange', measure);
    };
  }, []);

  const applyZoomMultiple = useCallback((next) => {
    setZoomMultiple(clampZoomMultiple(next));
  }, []);

  const zoomIn = () => applyZoomMultiple(zoomMultiple * 1.4);
  const zoomOut = () => applyZoomMultiple(zoomMultiple / 1.4);
  const resetView = () => {
    setZoomMultiple(1);
    setRawPan({ x: 0, y: 0 });
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
      pinchRef.current = {
        distance: Math.hypot(a.x - b.x, a.y - b.y),
        multiple: zoomMultiple,
      };
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
      // Remember the final coordinate so release does not have to re-read it
      // from a parent render that may not have happened yet.
      drag.last = clampLogical(drag.origX + dlx, drag.origY + dly);
      onDragMove(drag.id, drag.last);
      return;
    }

    if (pinchRef.current && pointersRef.current.size === 2) {
      const [a, b] = [...pointersRef.current.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchRef.current.distance > 0) {
        applyZoomMultiple((pinchRef.current.multiple * distance) / pinchRef.current.distance);
      }
      return;
    }

    const panning = panRef.current;
    if (panning) {
      const dx = e.clientX - panning.startX;
      const dy = e.clientY - panning.startY;
      panning.moved = Math.max(panning.moved, Math.hypot(dx, dy));
      setRawPan({ x: panning.origX + dx, y: panning.origY + dy });
    }
  };

  const handlePointerUp = () => {
    if (dragRef.current) {
      const { id, last } = dragRef.current;
      dragRef.current = null;
      pointersRef.current.clear();
      panRef.current = null;
      pinchRef.current = null;
      onDragEnd(id, last || null);
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
