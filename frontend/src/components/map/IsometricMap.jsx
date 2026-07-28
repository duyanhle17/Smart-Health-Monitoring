import { useState, useEffect, useRef, useCallback } from 'react';
import useStore, { workerName } from '../../store';
import { adminPost } from '../../lib/adminApi';

// Coordinate mapping: backend logical (0-100) → CSS px (0-1000 X, 0-800 Y)
const toCSS = (lx, ly) => ({ left: `${lx * 10}px`, top: `${ly * 8}px` });

const LIVE_UWB_ANCHOR_IDS = ['ANC_LEFT', 'ANC_RIGHT'];

const finiteCoordinate = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const WorkerNode = ({ worker, left, top, id, displayName, z = 2, status = 'NORMAL', yaw = 0, isDragging, onPointerDown, rotX, rotZ }) => {
  const isOffline = status === 'OFFLINE';
  const isDanger = status === 'DANGER';
  const isStaleLocation = Boolean(worker?.location_stale);
  const isLastKnownLocation = Boolean(worker?.location_last_known);
  const isLineEstimate = Boolean(
    worker?.location_degraded || worker?.uwb?.degraded || worker?.uwb?.geometry_mode === 'line'
  );
  const isLowGeometry = !isLineEstimate && worker?.location_valid === true && Boolean(
    worker?.uwb?.low_geometry || worker?.uwb?.branch_ambiguous
  );

  let angle = 0;
  if (worker?.history_imu && worker.history_imu.ax?.length > 0 && worker.history_imu.ay?.length > 0) {
    const ax = worker.history_imu.ax[worker.history_imu.ax.length - 1];
    const ay = worker.history_imu.ay[worker.history_imu.ay.length - 1];
    if (ax !== 0 || ay !== 0) {
      angle = Math.atan2(ay, ax) * (180 / Math.PI);
    }
  }

  let nodeColor = 'bg-green-500 border-green-800';
  let labelBg = 'bg-green-900 border-green-400 text-white';
  let effect = <div className="w-10 h-10 rounded-full bg-green-500 opacity-60 animate-ping absolute pointer-events-none"></div>;

  if (status === 'WARNING') {
    nodeColor = 'bg-orange-500 border-orange-900';
    labelBg = 'bg-orange-600 border-orange-200 text-white';
    effect = <div className="w-12 h-12 rounded-full bg-orange-500 opacity-70 animate-ping absolute pointer-events-none" style={{ animationDuration: '0.7s' }}></div>;
  } else if (isDanger) {
    nodeColor = 'bg-red-600 border-red-950';
    labelBg = 'bg-red-700 border-red-300 text-white animate-pulse';
    effect = (
      <>
        <div className="w-14 h-14 rounded-full bg-red-600 animate-radiate absolute pointer-events-none opacity-80"></div>
        <div className="w-8 h-8 rounded-full bg-red-500 opacity-90 animate-ping absolute pointer-events-none" style={{ animationDuration: '0.4s' }}></div>
      </>
    );
  } else if (isOffline) {
    nodeColor = 'bg-gray-700 border-gray-900 grayscale opacity-80';
    labelBg = 'bg-gray-800 border-gray-600 text-gray-400 animate-glitch';
    effect = <div className="w-8 h-8 rounded-full border-4 border-gray-500 animate-radar-ping absolute pointer-events-none"></div>;
  } else if (isLastKnownLocation) {
    // The current UWB geometry has been invalid for longer than the short
    // hold window. Keep the last *measured* coordinate visible in gray so an
    // online worker never blinks away, while clearly separating it from live.
    nodeColor = 'bg-gray-500 border-gray-800 grayscale opacity-90';
    labelBg = 'bg-gray-800 border-gray-300 text-white';
    effect = <div className="w-10 h-10 rounded-full border-2 border-gray-500 animate-radar-ping absolute pointer-events-none"></div>;
  } else if (isStaleLocation) {
    // The backend is deliberately holding the last *real* circle-intersection
    // during a short RF dropout. Keep the marker visible, but never make it
    // look like a fresh green position.
    nodeColor = 'bg-orange-500 border-orange-900';
    labelBg = 'bg-orange-700 border-orange-200 text-white';
    effect = <div className="w-10 h-10 rounded-full border-2 border-orange-500 animate-radar-ping absolute pointer-events-none"></div>;
  } else if (isLineEstimate) {
    // The backend has a new pair of real ranges, but the deployment's explicit
    // on-line constraint supplies only the along-anchor coordinate. Never make
    // that degraded 1-D estimate look like a green 2-D position lock.
    nodeColor = 'bg-amber-500 border-amber-900';
    labelBg = 'bg-amber-700 border-amber-100 text-white';
    effect = <div className="w-10 h-10 rounded-full border-2 border-amber-500 animate-radar-ping absolute pointer-events-none"></div>;
  } else if (isLowGeometry) {
    // This is still a real two-range update, but close to the anchor baseline
    // its perpendicular coordinate is weakly observed. Make that limitation
    // visible instead of showing the usual high-confidence green marker.
    nodeColor = 'bg-amber-500 border-amber-900';
    labelBg = 'bg-amber-700 border-amber-100 text-white';
    effect = <div className="w-10 h-10 rounded-full border-2 border-amber-500 animate-radar-ping absolute pointer-events-none"></div>;
  }

  // Calculate dynamic label pop-up height to ensure it jumps out of glass ceilings
  // Z=2 means on the ground, so we need extra height to clear the Z=100 glass tube layer.
  const labelHeight = z < 50 ? 250 : 150;

  return (
  <div
    className="absolute z-[100] group"
    style={{
      left,
      top,
      transform: `translate(-50%, -50%) translateZ(${z}px)`,
      transformStyle: 'preserve-3d',
      // Incoming HTTPS/Socket.IO timing is not perfectly uniform. A longer eased
      // retargeting transition turns fresh UWB fixes into continuous motion
      // instead of move-stop-move, without altering the coordinate itself.
      transition: isDragging ? 'none' : 'left 1.2s cubic-bezier(0.22, 1, 0.36, 1), top 1.2s cubic-bezier(0.22, 1, 0.36, 1)',
      willChange: 'left, top',
      cursor: onPointerDown ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
      pointerEvents: onPointerDown ? 'auto' : undefined,
      // A finger starting a drag on the node must not scroll the page.
      touchAction: onPointerDown ? 'none' : undefined
    }}
    onPointerDown={onPointerDown}
  >
    <div className="relative flex items-center justify-center pointer-events-auto" style={{ transformStyle: 'preserve-3d' }}>
      {/* Target Direction Arrow (from IMU Yaw tracking anchor) */}
      {!isOffline && (<div className="absolute w-12 h-12 transition-transform duration-500 ease-linear pointer-events-none" style={{ transform: `rotate(${yaw}deg) translateZ(1px)` }}><div className="absolute -top-[2px] left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-b-[12px] border-l-transparent border-r-transparent border-b-black opacity-60 z-20 drop-shadow-md"></div></div>)}

      {/* Node Body */}
      <div className={`w-5 h-5 rounded-full ${nodeColor} border-2 absolute z-10 shadow-xl`}></div>

      {/* Acceleration/Movement Arrow */}
      {!isOffline && (
        <div className="absolute transition-transform duration-500 ease-in-out z-20" style={{ transform: `rotateZ(${angle}deg)` }}>
          <div className="absolute w-0 h-0 border-t-[5px] border-b-[5px] border-l-[10px] border-t-transparent border-b-transparent border-l-gray-400 drop-shadow-md" style={{ left: '12px', top: '-5px' }}></div>
        </div>
      )}

      {/* Visual State Effects */}
      {effect}

      {/* 3D Label */}
      <div
        className={`absolute z-[999] transition-all duration-300 pointer-events-none drop-shadow-2xl ${isOffline ? 'opacity-100' : 'opacity-0 translate-y-4 group-hover:opacity-100 group-hover:translate-y-0'}`}
        style={{ transform: `rotateZ(${-rotZ}deg) rotateX(${-rotX}deg) translate(-50%, -50%) translateZ(${labelHeight}px) scale(0.5)`, left: '50%', top: '0px' }}
      >
        <div className={`whitespace-nowrap ${labelBg} px-8 py-3 text-2xl font-heavy tracking-widest border-[6px] shadow-[0_10px_30px_rgba(0,0,0,0.5)]`} style={{ WebkitFontSmoothing: 'antialiased', backfaceVisibility: 'hidden' }}>
          {displayName || id}{isLastKnownLocation
            ? ' · LAST KNOWN'
            : isStaleLocation
              ? ' · LAST FIX'
              : (isLineEstimate || isLowGeometry) ? ' · DEGRADED' : ''}
        </div>
      </div>
    </div>
  </div>
)};

const AnchorNode = ({ left, top, id, z = 2, rotX, rotZ }) => {
  const labelHeight = z < 50 ? 250 : 150;

  return (
  <div
    className="absolute z-[100] group"
    style={{
      left,
      top,
      transform: `translate(-50%, -50%) translateZ(${z}px)`,
      transformStyle: 'preserve-3d',
      transition: 'left 0.8s linear, top 0.8s linear',
      cursor: 'pointer'
    }}
  >
    <div className="relative flex items-center justify-center cursor-pointer" style={{ transformStyle: 'preserve-3d' }}>
      <div className="w-5 h-5 rounded-none bg-brand-yellow border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-none bg-brand-yellow opacity-40 animate-pulse absolute"></div>
      <div
        className="absolute z-[999] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-2xl"
        style={{ transform: `rotateZ(${-rotZ}deg) rotateX(${-rotX}deg) translate(-50%, -30%) translateZ(${labelHeight}px) scale(0.5)`, left: '50%', top: '0px' }}
      >
        <div className="whitespace-nowrap bg-brand-yellow text-black px-8 py-3 text-2xl font-heavy tracking-widest border-[6px] border-black" style={{ WebkitFontSmoothing: 'antialiased', backfaceVisibility: 'hidden' }}>
          {id}
        </div>
      </div>
    </div>
  </div>
)};

export default function IsometricMap({ isAdminView = false }) {
  // A phone screen cannot fit the 1000x800 scene at 1:1 — start zoomed out.
  const [zoom, setZoom] = useState(() =>
    (typeof window !== 'undefined' && window.innerWidth < 1024 ? 0.45 : 1)
  );

  const [rotZ, setRotZ] = useState(-45);
  const [rotX, setRotX] = useState(60);
  const [isRotating, setIsRotating] = useState(false);
  const rotDragRef = useRef({ active: false, startX: 0, startY: 0, startRotZ: -45, startRotX: 60 });

  // Admin-only worker drag: a local optimistic position overlay, committed to
  // the backend on release. Never mutates store data directly.
  const [dragWorker, setDragWorker] = useState(null);
  const [dragPositions, setDragPositions] = useState({});
  const dragRef = useRef({ startX: 0, startY: 0, origLx: 0, origLy: 0 });

  // Movement-based heading tracker
  const prevPositionsRef = useRef({});
  const [headingAngles, setHeadingAngles] = useState({});

  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const personnel = useStore(s => s.personnel);
  const isConnected = useStore(s => s.isConnected);
  const hiddenNodes = useStore(s => s.hiddenNodes);
  const uwbConfig = useStore(s => s.uwbConfig);
  const mapTheme = useStore(s => s.mapTheme);
  const setMapTheme = useStore(s => s.setMapTheme);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.3));
  const handleResetZoom = () => setZoom(1);

  const handleRotStart = useCallback((e) => {
    if (e.button !== 0) return; // left-click only
    if (e.target.closest('.group') || e.target.closest('button')) return; // ignore workers and buttons
    rotDragRef.current = { active: true, startX: e.clientX, startY: e.clientY, startRotZ: rotZ, startRotX: rotX };
    setIsRotating(true);
  }, [rotZ, rotX]);

  const handleRotMove = useCallback((e) => {
    if (!rotDragRef.current.active) return;
    const dx = e.clientX - rotDragRef.current.startX;
    const dy = e.clientY - rotDragRef.current.startY;

    // Free camera rotation mapping physically to mouse directions
    const newRotZ = Math.max(-90, Math.min(90, rotDragRef.current.startRotZ - dx * 0.3));
    const newRotX = Math.max(0, Math.min(80, rotDragRef.current.startRotX - dy * 0.3));

    setRotZ(newRotZ);
    setRotX(newRotX);
  }, []);

  const handleRotEnd = useCallback(() => {
    rotDragRef.current.active = false;
    setIsRotating(false);
  }, []);

  const handleWorkerDragStart = useCallback((e, workerId, lx, ly) => {
    if (!isAdminView) return;
    e.stopPropagation();
    e.preventDefault();
    setDragWorker(workerId);
    setDragPositions(prev => ({ ...prev, [workerId]: { x: lx, y: ly } }));
    dragRef.current = { startX: e.clientX, startY: e.clientY, origLx: lx, origLy: ly };
  }, [isAdminView]);

  const handleWorkerDragMove = useCallback((e) => {
    if (!dragWorker) return;

    // Reverse-projection using exact trigonometric un-projection
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;

    const scaledDx = dx / zoom;
    const scaledDy = dy / zoom;

    const rotXRad = rotX * Math.PI / 180;
    const unpitchedDy = scaledDy / Math.cos(rotXRad);

    const rotZRad = rotZ * Math.PI / 180;
    const cosZ = Math.cos(-rotZRad);
    const sinZ = Math.sin(-rotZRad);

    const sceneDx = scaledDx * cosZ - unpitchedDy * sinZ;
    const sceneDy = scaledDx * sinZ + unpitchedDy * cosZ;

    const dlx = sceneDx / 10;
    const dly = sceneDy / 8;

    setDragPositions(prev => ({
      ...prev,
      [dragWorker]: {
        x: Math.max(0, Math.min(100, dragRef.current.origLx + dlx)),
        y: Math.max(0, Math.min(100, dragRef.current.origLy + dly)),
      },
    }));
  }, [dragWorker, zoom, rotX, rotZ]);

  const handleWorkerDragEnd = useCallback(async () => {
    if (!dragWorker) return;
    const finalPos = dragPositions[dragWorker];
    if (finalPos) {
      try {
        await adminPost('/api/admin/node', {
          worker_id: dragWorker,
          x: finalPos.x.toFixed(1),
          y: finalPos.y.toFixed(1),
        });
      } catch (e) { console.error(e); }
    }
    // The backend override now owns the coordinate; drop the local overlay so
    // the next socket update renders server truth.
    setDragWorker(null);
    setDragPositions(prev => {
      const next = { ...prev };
      delete next[dragWorker];
      return next;
    });
  }, [dragWorker, dragPositions]);

  const liveAnchors = LIVE_UWB_ANCHOR_IDS
    .map(id => anchors.find(anchor => anchor.id === id))
    .filter(Boolean);

  const displayAnchors = liveAnchors.filter(a => !hiddenNodes[a.id]);

  let displayWorkers = Object.values(workers).map(w => {
    const dragPos = dragPositions[w.worker_id];
    return dragPos ? { ...w, x: dragPos.x, y: dragPos.y } : w;
  });

  const liveBaselineM = finiteCoordinate(uwbConfig?.anchor_baseline_m);
  const liveBaselineAnchors = displayAnchors.length === 2 ? displayAnchors : null;

  // Metric mapping for the site scene: the backend spans 80 logical units
  // across the anchor baseline.
  const baselineMetres = liveBaselineM || 6.0;
  const unitsPerMetre = 80 / baselineMetres;
  const gridMetres = 4 / unitsPerMetre; // one 40 px grid cell along X

  // In live mode, x/y remain at a harmless backend default until a real,
  // geometrically valid UWB fix exists.  An uncalibrated real estimate is
  // shown (and labelled) rather than being replaced by that default dot.
  const unlocalizedWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    w.location_valid !== true &&
    w.location_last_known !== true
  );
  const uncalibratedLiveWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    w.location_valid === true &&
    !w.location_degraded &&
    !w.uwb?.degraded &&
    w.uwb?.geometry_mode !== 'line' &&
    w.location_calibrated === false
  );
  const lowGeometryLiveWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    w.location_valid === true &&
    !w.location_degraded &&
    w.uwb?.geometry_mode !== 'line' &&
    (w.uwb?.low_geometry || w.uwb?.branch_ambiguous)
  );
  const lineEstimateWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    (w.location_degraded || w.uwb?.degraded || w.uwb?.geometry_mode === 'line') &&
    (w.location_valid === true || w.location_last_known === true)
  );
  const staleLiveWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    w.location_valid === true &&
    w.location_stale === true
  );
  const lastKnownLiveWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] &&
    w.location_last_known === true
  );
  displayWorkers = displayWorkers.filter(w =>
    !hiddenNodes[w.worker_id] && (
      isAdminView || w.location_valid === true || w.location_last_known === true
      // A dot the operator placed by hand stays visible on every dashboard,
      // even with no live/last-known UWB position (offline staging).
      || w.location_manual === true
    )
  );

  // Operator-facing grouping: one amber strip for every degraded-accuracy
  // reason, one gray strip for workers without a live position. Per-reason
  // detail stays available in the strip tooltips.
  const degradedWorkers = [...new Set([
    ...lineEstimateWorkers, ...lowGeometryLiveWorkers,
    ...uncalibratedLiveWorkers, ...staleLiveWorkers,
  ].map(w => w.worker_id))];
  const awaitingWorkers = [...new Set([
    ...lastKnownLiveWorkers, ...unlocalizedWorkers,
  ].map(w => w.worker_id))];

  // Compute heading angles from position changes
  useEffect(() => {
    const prev = prevPositionsRef.current;
    const newAngles = {};
    displayWorkers.forEach(w => {
      const id = w.worker_id;
      if (prev[id]) {
        const dx = w.x - prev[id].x;
        const dy = w.y - prev[id].y;
        // Only update heading if the node actually moved (threshold > 0.3 to avoid jitter)
        if (Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3) {
          // atan2(dx, -dy): in isometric space, positive X = right, positive Y = down
          // The arrow rotates in CSS where 0deg = up, so we use atan2(dx, -dy)
          newAngles[id] = Math.atan2(dx, -dy) * (180 / Math.PI);
        } else {
          // Keep previous heading when stationary
          newAngles[id] = headingAngles[id] ?? 0;
        }
      }
      prev[id] = { x: w.x, y: w.y };
    });
    if (Object.keys(newAngles).length > 0) {
      setHeadingAngles(a => ({ ...a, ...newAngles }));
    }
  }, [displayWorkers.map(w => `${w.worker_id}:${w.x}:${w.y}`).join(',')]);

  const getRenderZ = (node, type) => {
    if (node.z !== undefined && node.z !== null) return node.z;

    // The live UWB coordinate frame is a flat physical plan; workers stay on
    // the floor and the two anchors sit on the scene fixtures.
    if (type === 'worker') return 5;
    return 48;
  };

  return (
    <div
      className="relative w-full h-full bg-gray-100 flex-1 overflow-hidden flex flex-col justify-center items-center"
      // Pointer events cover both mouse and touch: a finger can rotate the
      // camera or drag a worker (admin) exactly like the mouse does.
      style={{ touchAction: 'none' }}
      onPointerDown={handleRotStart}
      onPointerMove={(e) => { handleRotMove(e); handleWorkerDragMove(e); }}
      onPointerUp={() => { handleRotEnd(); handleWorkerDragEnd(); }}
      onPointerCancel={() => { handleRotEnd(); handleWorkerDragEnd(); }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* Connection indicator */}
      <div className={`absolute bottom-6 left-6 z-20 flex items-center gap-2 text-[10px] font-heavy uppercase ${isConnected ? 'text-green-700' : 'text-gray-400'}`}>
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></div>
        {isConnected ? 'LIVE' : 'OFFLINE'}
      </div>

      {/* Map Controls */}
      <div className="absolute top-6 right-6 z-20 flex flex-col">
        <button onClick={handleZoomIn} className="w-10 h-10 bg-white border-2 border-black flex items-center justify-center font-heavy hover:bg-black hover:text-white transition-none">+</button>
        <button onClick={handleZoomOut} className="w-10 h-10 bg-white border-2 border-black border-t-0 flex items-center justify-center font-heavy hover:bg-black hover:text-white transition-none">−</button>

        {/* Reset Camera View Button */}
        <button onClick={() => { handleResetZoom(); setRotZ(-45); setRotX(60); }} className="h-10 bg-white border-2 border-black flex items-center justify-center font-heavy text-[10px] uppercase hover:bg-black hover:text-white transition-none shadow-sm gap-1 mt-4" title="Reset Camera View">
          <span className="material-symbols-outlined text-sm" data-icon="3d_rotation">3d_rotation</span>
        </button>

        {/* Scene toggle: real site vs mine presentation demo */}
        <button
          onClick={() => setMapTheme(mapTheme === 'SITE' ? 'MINE' : 'SITE')}
          className={`h-10 px-2 border-2 border-black flex items-center justify-center font-heavy text-[10px] uppercase transition-none shadow-sm gap-1 mt-4 ${mapTheme === 'MINE' ? 'bg-black text-brand-yellow' : 'bg-white hover:bg-black hover:text-white'}`}
          title="Switch scene (visual only — positions stay live)"
        >
          {mapTheme === 'SITE' ? 'SCENE: SITE' : 'SCENE: MINE'}
        </button>
      </div>

      {/* Legend */}
      <div className="absolute top-6 left-6 z-20 bg-white border-4 border-black p-4 shadow-sm">
        <h3 className="font-heavy uppercase text-[10px] border-b-2 border-black pb-2 mb-3">MAP LEGEND</h3>
        <div className="flex flex-col gap-3 text-[10px] font-heavy uppercase">
          <div className="flex items-center gap-4">
            <div className="w-4 h-4 bg-brand-red rounded-full border-2 border-black relative"><div className="w-full h-full rounded-full bg-brand-red animate-ping absolute"></div></div> Worker ({displayWorkers.length})
          </div>
          <div className="flex items-center gap-4">
            <div className="w-4 h-4 bg-brand-yellow border-2 border-black relative"><div className="w-full h-full rounded-none bg-brand-yellow animate-pulse absolute"></div></div> Anchor ({displayAnchors.length})
          </div>
          {liveBaselineAnchors && liveBaselineM !== null && (
            <div className="border-l-2 border-brand-yellow pl-2 text-[9px] leading-3 text-gray-600">
              ANCHOR BASELINE: {liveBaselineM.toFixed(2)} m · GRID {gridMetres.toFixed(2)} m
            </div>
          )}
          {degradedWorkers.length > 0 && (
            <div
              className="border-l-2 border-amber-500 pl-2 text-[9px] leading-3 text-amber-800"
              title={`Technical detail — 1-D line only: ${lineEstimateWorkers.map(w => w.worker_id).join(', ') || 'none'} · near-baseline geometry: ${lowGeometryLiveWorkers.map(w => w.worker_id).join(', ') || 'none'} · awaiting calibration: ${uncalibratedLiveWorkers.map(w => w.worker_id).join(', ') || 'none'} · holding last fix: ${staleLiveWorkers.map(w => w.worker_id).join(', ') || 'none'}`}
            >
              DEGRADED ACCURACY: {degradedWorkers.join(', ')}
            </div>
          )}
          {awaitingWorkers.length > 0 && (
            <div
              className="border-l-2 border-gray-500 pl-2 text-[9px] leading-3 text-gray-600"
              title={`Technical detail — last known position: ${lastKnownLiveWorkers.map(w => w.worker_id).join(', ') || 'none'} · no position yet: ${unlocalizedWorkers.map(w => w.worker_id).join(', ') || 'none'}${unlocalizedWorkers[0]?.uwb?.calibrated === false ? ' (calibration required)' : ''}`}
            >
              NO LIVE POSITION: {awaitingWorkers.join(', ')}
            </div>
          )}
        </div>
      </div>

      {rotZ > -44 && (
        <div className="absolute bottom-6 right-6 z-20 text-[10px] font-heavy uppercase text-gray-500">
          LEFT-CLICK DRAG → ROTATE | {rotZ > -10 ? 'TOP-DOWN' : 'ISOMETRIC'}
        </div>
      )}

      <div className="iso-container -ml-20">
        <div
          className={`iso-scene ease-out ${isRotating ? '' : 'transition-transform duration-100'}`}
          style={{ transform: `scale(${zoom}) rotateX(${rotX}deg) rotateZ(${rotZ}deg)` }}
        >
          {/* ═══ SITE scene — the real deployment: clean surveyed floor ═══ */}
          {mapTheme === 'SITE' && (
            <>
              <div className="site-apron"></div>
              <div className="site-ground"></div>
              {/* Painted-on floor label */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <span className="font-heavy text-black opacity-15 tracking-[0.5em] text-[42px] uppercase whitespace-nowrap">SafeWork Area</span>
              </div>
            </>
          )}

          {/* ═══ MINE scene — presentation demo: 2.5D tunnel with timber sets ═══ */}
          {mapTheme === 'MINE' && (
            <>
              <div className="mine-ground"></div>

              {/* Tunnel walls */}
              <div className="iso-block mine-wall" style={{ left: '0px', top: '0px', width: '70px', height: '800px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              <div className="iso-block mine-wall" style={{ left: '930px', top: '0px', width: '70px', height: '800px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Back wall with tunnel mouth */}
              <div className="iso-block mine-wall" style={{ left: '70px', top: '0px', width: '310px', height: '70px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              <div className="iso-block mine-wall" style={{ left: '620px', top: '0px', width: '310px', height: '70px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              {/* Dark tunnel mouth on the floor between the back walls */}
              <div className="absolute" style={{ left: '380px', top: '0px', width: '240px', height: '70px', background: '#0c0a09', border: '4px solid #000', transform: 'translateZ(1px)' }}></div>

              {/* Timber support sets (posts + lintel) */}
              {[190, 400, 610].map(y => (
                <div key={`frame-${y}`}>
                  <div className="iso-block timber-post" style={{ left: '70px', top: `${y}px`, width: '26px', height: '26px' }}>
                    <div className="iso-face face-front"></div>
                    <div className="iso-face face-right"></div>
                    <div className="iso-face face-left"></div>
                    <div className="iso-face face-back"></div>
                    <div className="iso-face face-top"></div>
                  </div>
                  <div className="iso-block timber-post" style={{ left: '904px', top: `${y}px`, width: '26px', height: '26px' }}>
                    <div className="iso-face face-front"></div>
                    <div className="iso-face face-right"></div>
                    <div className="iso-face face-left"></div>
                    <div className="iso-face face-back"></div>
                    <div className="iso-face face-top"></div>
                  </div>
                  <div className="iso-block timber-lintel" style={{ left: '70px', top: `${y}px`, width: '860px', height: '26px', transform: 'translateZ(88px)' }}>
                    <div className="iso-face face-front"></div>
                    <div className="iso-face face-right"></div>
                    <div className="iso-face face-left"></div>
                    <div className="iso-face face-back"></div>
                    <div className="iso-face face-top"></div>
                  </div>
                </div>
              ))}

              {/* Ore piles */}
              <div className="iso-block ore-rock" style={{ left: '120px', top: '520px', width: '54px', height: '44px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              <div className="iso-block ore-rock" style={{ left: '830px', top: '300px', width: '44px', height: '54px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Escape route + entrance hazard stripe */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50" viewBox="0 0 1000 800" style={{ transform: 'translateZ(2px)' }}>
                <path d="M 500 796 L 500 70" fill="none" stroke="#FFCC00" strokeDasharray="14 10" strokeWidth="4" />
                <line x1="74" y1="770" x2="926" y2="770" stroke="#FFCC00" strokeWidth="10" strokeDasharray="26 18" />
                <line x1="74" y1="770" x2="926" y2="770" stroke="#000" strokeWidth="10" strokeDasharray="18 26" strokeDashoffset="-22" />
              </svg>
            </>
          )}

          {/* UWB baseline between the two physical anchors */}
          {liveBaselineAnchors && liveBaselineM !== null && (() => {
            const [leftAnchor, rightAnchor] = liveBaselineAnchors;
            const leftX = finiteCoordinate(leftAnchor.x);
            const leftY = finiteCoordinate(leftAnchor.y);
            const rightX = finiteCoordinate(rightAnchor.x);
            const rightY = finiteCoordinate(rightAnchor.y);
            if ([leftX, leftY, rightX, rightY].some(value => value === null)) return null;
            const labelX = ((leftX + rightX) / 2) * 10;
            const labelY = ((leftY + rightY) / 2) * 8 - 14;
            return (
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-[60]" viewBox="0 0 1000 800" aria-label={`UWB anchor baseline ${liveBaselineM.toFixed(2)} metres`}>
                <line x1={leftX * 10} y1={leftY * 8} x2={rightX * 10} y2={rightY * 8} stroke="#FFCC00" strokeWidth="3" strokeDasharray="7 5" />
                <rect x={labelX - 34} y={labelY - 10} width="68" height="20" fill="white" stroke="black" strokeWidth="1" />
                <text x={labelX} y={labelY + 4} textAnchor="middle" fontSize="10" fontWeight="700" fill="black">{liveBaselineM.toFixed(2)} m</text>
              </svg>
            );
          })()}
          {displayAnchors.map(a => {
            const pos = toCSS(a.x, a.y);
            return <AnchorNode
                     key={a.id}
                     left={pos.left}
                     top={pos.top}
                     id={a.id}
                     z={getRenderZ(a, 'anchor')}
                     rotX={rotX}
                     rotZ={rotZ}
                   />;
          })}

          {/* Dynamic Worker Nodes (draggable on the admin console only) */}
          {displayWorkers.map(w => {
            const pos = toCSS(w.x, w.y);
            const isDragging = dragWorker === w.worker_id;
            return (
                <WorkerNode
                  key={w.worker_id}
                  worker={w}
                  left={pos.left}
                  top={pos.top}
                  id={w.worker_id}
                  displayName={workerName(personnel, w.worker_id)}
                  z={getRenderZ(w, 'worker')}
                  status={w.alert}
                  yaw={headingAngles[w.worker_id] ?? w.yaw ?? 0}
                  isDragging={isDragging}
                  onPointerDown={isAdminView ? (e) => handleWorkerDragStart(e, w.worker_id, w.x, w.y) : undefined}
                  rotX={rotX}
                  rotZ={rotZ}
                />
            );
          })}
        </div>
      </div>
    </div>
  );
}
