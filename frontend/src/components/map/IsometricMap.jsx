import { useState, useEffect, useRef, useCallback } from 'react';
import useStore from '../../store';

// Coordinate mapping: backend logical (0-100) → CSS px (0-1000 X, 0-800 Y)
const toCSS = (lx, ly) => ({ left: `${lx * 10}px`, top: `${ly * 8}px` });

// Z-height based on zone
const getZ = (y) => y < 35 ? 70 : 5;
const getBlockZ = (zone) => zone === 'GAMMA_STAGE' ? 70 : (zone === 'ALPHA_LEFT' || zone === 'BETA_RIGHT' || zone === 'DELTA_CENTER') ? 42 : 5;

import { SCENARIO_ANCHORS, SCENARIO_WORKERS, MODE_ANCHORS, MODE_WORKERS, FALLBACK_ANCHORS, FALLBACK_WORKERS } from '../../mockData';

const workerNames = {
  'WK_102': 'Trung Nam',
  'WK_048': 'Duy Anh',
  'WK_089': 'Quoc Khanh',
  'WK_004': 'Ngoc Diem',
  'WK_055': 'Son Tung',
  'WK_077': 'Thanh Tran'
};

const WorkerNode = ({ worker, left, top, id, z = 2, status = 'NORMAL', yaw = 0, isDragging, onMouseDown, rotX, rotZ }) => {
  const isOffline = status === 'OFFLINE';
  const isDanger = status === 'DANGER';
  const displayName = workerNames[id] || id;

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
      transition: isDragging ? 'none' : 'left 0.8s linear, top 0.8s linear',
      cursor: onMouseDown ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
      pointerEvents: onMouseDown ? 'auto' : undefined
    }}
    onMouseDown={onMouseDown}
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
          {displayName}
        </div>
      </div>
    </div>
  </div>
)};

const AnchorNode = ({ left, top, id, z = 2, rotX, rotZ, onMouseDown, isDragging }) => {
  const labelHeight = z < 50 ? 250 : 150;
  
  return (
  <div 
    className="absolute z-[100] group" 
    style={{ 
      left, 
      top, 
      transform: `translate(-50%, -50%) translateZ(${z}px)`, 
      transformStyle: 'preserve-3d',
      transition: isDragging ? 'none' : 'left 0.8s linear, top 0.8s linear',
      cursor: onMouseDown ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
      pointerEvents: onMouseDown ? 'auto' : undefined
    }}
    onMouseDown={onMouseDown}
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
  const [zoom, setZoom] = useState(1);
  const [showAdmin, setShowAdmin] = useState(false);
  const [adminForm, setAdminForm] = useState({ target_id: 'WK_102', alert: 'NORMAL', x: '', y: '', ch4: '', co: '' });
  const [ticker, setTicker] = useState(0);

  const [rotZ, setRotZ] = useState(-45);
  const [rotX, setRotX] = useState(60);
  const [isRotating, setIsRotating] = useState(false);
  const rotDragRef = useRef({ active: false, startX: 0, startY: 0, startRotZ: -45, startRotX: 60 });

  // Drag worker
  const [dragWorker, setDragWorker] = useState(null);
  const dragRef = useRef({ startX: 0, startY: 0, origLx: 0, origLy: 0 });

  // Movement-based heading tracker
  const prevPositionsRef = useRef({});
  const [headingAngles, setHeadingAngles] = useState({});

  const handleAdminSubmit = async (e) => {
    e.preventDefault();
    try {
      const API_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000';
      const payload = { ...adminForm };
      if (!payload.x) delete payload.x;
      if (!payload.y) delete payload.y;
      if (!payload.ch4) delete payload.ch4;
      if (!payload.co) delete payload.co;

      if (payload.target_id.startsWith('ANC_')) {
          payload.anchor_id = payload.target_id;
      } else {
          payload.worker_id = payload.target_id;
      }
      delete payload.target_id;
      
      await fetch(`${API_URL}/api/admin/node`, {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' }
      });
      setShowAdmin(false);
    } catch (err) {
      console.error(err);
    }
  };

  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);
  const scenario = useStore(s => s.scenario);
  const hoveredZone = useStore(s => s.hoveredZone);
  const mapMode = useStore(s => s.mapMode);
  const isSimulation = useStore(s => s.isSimulation);
  const hiddenNodes = useStore(s => s.hiddenNodes);

  // Auto-jitter for simulated scenarios AND mode workers
  useEffect(() => {
    if (!isSimulation) return;
    const isSimScenario = scenario !== 'NORMAL';
    const isModeWithWorkers = mapMode !== 'NORMAL';
    if (!isSimScenario && !isModeWithWorkers) return;
    const interval = setInterval(() => {
      const lists = [];
      if (isSimScenario && SCENARIO_WORKERS[scenario]) lists.push(SCENARIO_WORKERS[scenario]);
      if (isModeWithWorkers && MODE_WORKERS[mapMode]) lists.push(MODE_WORKERS[mapMode]);
      lists.forEach(wList => {
        wList.forEach(w => {
          if (w.alert === 'OFFLINE') return;
          w.x += (Math.random() - 0.5) * 0.8;
          w.y += (Math.random() - 0.5) * 0.8;
          if (w.hr !== '--') {
            if (w.worker_id === 'WK_089' && mapMode === 'ELEVATED') {
              w.hr = Math.max(70, Math.min(100, w.hr + (Math.random() - 0.5) * 3));
            } else {
              w.hr = Math.max(60, Math.min(180, w.hr + (Math.random() - 0.5) * 3));
            }
          }
          if (w.temp !== '--') w.temp = Math.max(36.0, Math.min(41.0, w.temp + (Math.random() - 0.5) * 0.1));
          w.ch4 = Math.max(0, w.ch4 + (Math.random() - 0.5) * 0.1);
          w.co = Math.max(0, w.co + (Math.random() - 0.5) * 1.5);
        });
      });
      setTicker(t => t + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [scenario, mapMode, isSimulation]);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));
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
    // Inverted dx and dy based on user feedback to feel more natural (grab front edge behavior)
    // Up-Down reverted to original (- dy)
    const newRotZ = Math.max(-90, Math.min(90, rotDragRef.current.startRotZ - dx * 0.3));
    const newRotX = Math.max(0, Math.min(80, rotDragRef.current.startRotX - dy * 0.3)); 
    
    setRotZ(newRotZ);
    setRotX(newRotX);
  }, []);

  const handleRotEnd = useCallback(() => {
    rotDragRef.current.active = false;
    setIsRotating(false);
  }, []);

  // Drag-worker handlers


  const handleWorkerDragStart = useCallback((e, workerId, lx, ly) => {
    if (!isAdminView) return; // CHẶN KÉO NẾU KHÔNG Ở TRANG ADMIN!
    e.stopPropagation();
    e.preventDefault();

    // Đồng bộ toạ độ hiển thị (từ backend) xuống dữ liệu gốc giả lập ngay khi bắt đầu click
    // Để khi fallback chuyển về mode Drag, node không bị nhảy về toạ độ cũ!
    const allLists = [MODE_WORKERS.LOBBY, MODE_WORKERS.ELEVATED, SCENARIO_WORKERS.CAVE_IN, SCENARIO_WORKERS.EVACUATION,
                      MODE_ANCHORS.LOBBY, MODE_ANCHORS.ELEVATED, SCENARIO_ANCHORS.CAVE_IN, SCENARIO_ANCHORS.EVACUATION, FALLBACK_ANCHORS];
    allLists.forEach(list => {
      const w = list?.find(node => (node.worker_id === workerId || node.id === workerId));
      if (w) {
        w.x = lx;
        w.y = ly;
      }
    });

    setDragWorker(workerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, origLx: lx, origLy: ly };
  }, [isAdminView]);

  const handleWorkerDragMove = useCallback((e) => {
    if (!dragWorker) return;
    
    // Reverse-projection using exact trigonometric un-projection
    // Track from absolute start pointer to avoid floating point accumulation (movementX lag)
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

    // Update the mode/scenario worker data incrementally
    const allLists = [MODE_WORKERS.LOBBY, MODE_WORKERS.ELEVATED, SCENARIO_WORKERS.CAVE_IN, SCENARIO_WORKERS.EVACUATION,
                      MODE_ANCHORS.LOBBY, MODE_ANCHORS.ELEVATED, SCENARIO_ANCHORS.CAVE_IN, SCENARIO_ANCHORS.EVACUATION, FALLBACK_ANCHORS];
    allLists.forEach(list => {
      const w = list?.find(node => (node.worker_id === dragWorker || node.id === dragWorker));
      if (w) { 
        w.x = Math.max(0, Math.min(100, dragRef.current.origLx + dlx)); 
        w.y = Math.max(0, Math.min(100, dragRef.current.origLy + dly)); 
      }
    });
    setTicker(t => t + 1);
  }, [dragWorker, zoom, rotX, rotZ]);

  const handleWorkerDragEnd = useCallback(async () => {
    if (!dragWorker) return;
    // Find the worker's current position and POST to backend
    const allLists = [MODE_WORKERS.LOBBY, MODE_WORKERS.ELEVATED, SCENARIO_WORKERS.CAVE_IN, SCENARIO_WORKERS.EVACUATION,
                      MODE_ANCHORS.LOBBY, MODE_ANCHORS.ELEVATED, SCENARIO_ANCHORS.CAVE_IN, SCENARIO_ANCHORS.EVACUATION, FALLBACK_ANCHORS];
    let finalW = null;
    allLists.forEach(list => {
      const w = list?.find(node => (node.worker_id === dragWorker || node.id === dragWorker));
      if (w) finalW = w;
    });
    if (finalW) {
      try {
        let payload = finalW.worker_id ? { worker_id: dragWorker } : { anchor_id: dragWorker };
        payload.x = finalW.x.toFixed(1);
        payload.y = finalW.y.toFixed(1);
        await fetch(`/api/admin/node`, {
          method: 'POST',
          body: JSON.stringify(payload),
          headers: { 'Content-Type': 'application/json' }
        });
      } catch (e) { console.error(e); }
    }
    setDragWorker(null);
  }, [dragWorker]);

  // Determine display data based on mapMode + scenario + simulation
  let displayAnchors, displayWorkers;
  
  // Anchors always stick to layout configuration
  if (scenario !== 'NORMAL') {
    displayAnchors = SCENARIO_ANCHORS[scenario] || FALLBACK_ANCHORS;
  } else if (mapMode !== 'NORMAL') {
    displayAnchors = MODE_ANCHORS[mapMode] || FALLBACK_ANCHORS;
  } else {
    displayAnchors = FALLBACK_ANCHORS;
  }
  
  // Workers depend on Simulation state vs Hardware Live state
  if (isSimulation) {
    if (scenario !== 'NORMAL') {
      displayWorkers = SCENARIO_WORKERS[scenario] || FALLBACK_WORKERS;
    } else if (mapMode !== 'NORMAL') {
      displayWorkers = MODE_WORKERS[mapMode] || FALLBACK_WORKERS;
    } else {
      displayWorkers = Object.values(workers).length > 0 ? Object.values(workers) : FALLBACK_WORKERS;
    }
  } else {
    displayWorkers = Object.values(workers).filter(w => w.worker_id === 'WK_102');
  }

  const customAnchors = useStore(s => s.customAnchors) || {};

  // Map mock backend workers positional & alert states onto displayWorkers for global sync
  displayWorkers = displayWorkers.map(w => {
    const bw = workers[w.worker_id];
    if (bw) {
      if (dragWorker === w.worker_id) {
         // Do not overwrite X/Y from backend if we are locally dragging it!
         return { ...w, alert: bw.alert };
      }
      return { ...w, x: bw.x, y: bw.y, alert: bw.alert };
    }
    return w;
  });

  // Filter out globally hidden nodes and apply custom anchor positions
  displayAnchors = displayAnchors
    .filter(a => !hiddenNodes[a.id])
    .map(a => {
      if (customAnchors[a.id] && dragWorker !== a.id) {
         return { ...a, x: customAnchors[a.id].x, y: customAnchors[a.id].y };
      }
      return a;
    });
  
  displayWorkers = displayWorkers.filter(w => !hiddenNodes[w.worker_id]);

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

  const loadTargetData = (targetId) => {
    let newForm = { target_id: targetId, x: '', y: '', alert: 'NORMAL', speed: '', ch4: '', co: '' };
    if (targetId.startsWith('ANC_')) {
      const anchor = displayAnchors.find(a => a.id === targetId);
      if (anchor) {
        newForm.x = parseFloat(anchor.x).toFixed(1);
        newForm.y = parseFloat(anchor.y).toFixed(1);
        const stateZones = useStore.getState().zones;
        const zoneMap = {"ANC_STAGE": "GAMMA_STAGE", "ANC_LEFT": "ALPHA_LEFT", "ANC_RIGHT": "BETA_RIGHT"};
        const zId = zoneMap[targetId] || targetId;
        if (stateZones[zId]) {
           newForm.ch4 = stateZones[zId].ch4;
           newForm.co = stateZones[zId].co;
        }
      }
    } else {
      const worker = displayWorkers.find(w => w.worker_id === targetId);
      if (worker) {
        newForm.x = parseFloat(worker.x).toFixed(1);
        newForm.y = parseFloat(worker.y).toFixed(1);
        newForm.alert = worker.alert;
      }
    }
    setAdminForm(newForm);
  };

  const getRenderZ = (node, type) => {
    if (node.z !== undefined && node.z !== null) return node.z;

    if (mapMode === 'LOBBY') {
      if (node.id === 'ANC_LOBBY_LEFT' || node.id === 'ANC_LOBBY_RIGHT' || node.id === 'ANC_LEFT' || node.id === 'ANC_RIGHT') return 2;
      if (node.id === 'ANC_STAGE' || node.id === 'ANC_LOBBY_MID') return 80;
      
      const px = node.x * 10, py = node.y * 10;
      if (px >= 220 && px <= 780 && py >= 0 && py <= 180) return 80;
      if (px >= 180 && px <= 820 && py >= 0 && py <= 220) return 60;
      if (px >= 140 && px <= 860 && py >= 0 && py <= 260) return 40;
      if (px >= 100 && px <= 900 && py >= 0 && py <= 300) return 20;
      return 2;
    }
    if (mapMode === 'ELEVATED') {
      return 35;
    }
    
    if (type === 'anchor') {
       return node.y < 35 ? 62 : 32;
    } else {
       const zone = node.zone || 'CENTER_PATH';
       return zone === 'GAMMA_STAGE' ? 70 : (zone === 'ALPHA_LEFT' || zone === 'BETA_RIGHT' || zone === 'DELTA_CENTER') ? 42 : 5;
    }
  };

  return (
    <div 
      className="relative w-full h-full bg-gray-100 flex-1 overflow-hidden flex flex-col justify-center items-center"
      onMouseDown={handleRotStart}
      onMouseMove={(e) => { handleRotMove(e); handleWorkerDragMove(e); }}
      onMouseUp={(e) => { handleRotEnd(); handleWorkerDragEnd(); }}
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

        {/* Hidden Admin Config button */}
        <button onClick={handleResetZoom} title="Reset Zoom"
        onDoubleClick={() => { setShowAdmin(true); loadTargetData(adminForm.target_id); }} className="w-10 h-10 bg-white border-2 border-black flex items-center justify-center hover:bg-black hover:text-white transition-none mt-4 group">
          <span className="material-symbols-outlined text-lg group-hover:opacity-100" data-icon="my_location">my_location</span>
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
        </div>
      </div>

      {/* Mode / Rotation indicator */}
      {mapMode !== 'NORMAL' && (
        <div className="absolute top-6 left-48 z-20 text-[10px] font-heavy uppercase text-black bg-brand-yellow border-2 border-black px-3 py-1">
          MODE: {mapMode} {isSimulation}
        </div>
      )}
      {rotZ > -44 && (
        <div className="absolute bottom-6 right-6 z-20 text-[10px] font-heavy uppercase text-gray-500">
          LEFT-CLICK DRAG → ROTATE | {rotZ > -10 ? 'TOP-DOWN' : 'ISOMETRIC'}
        </div>
      )}

      {/* New map backgrounds for scenarios */}
      {scenario === 'EVACUATION' && <img src="/map_cave_in.png" alt="Cave In Map" className="absolute object-cover w-[80%] h-full opacity-30 z-0 select-none grayscale" />}
      {scenario === 'CAVE_IN' && <img src="/map_cave_in.png" alt="Evacuation Map" className="absolute object-cover w-[80%] h-full opacity-40 z-0 select-none brightness-75 mix-blend-multiply" />}

      {/* Red Overlay for Evacuation */}
      {scenario === 'EVACUATION' && (
        <div className="absolute inset-0 bg-red-900/30 mix-blend-multiply pointer-events-none z-10 transition-colors duration-1000 animate-pulse"></div>
      )}

      <div className="iso-container -ml-20">
        <div 
          className={`iso-scene ease-out ${isRotating ? '' : 'transition-transform duration-100'}`} 
          style={{ transform: `scale(${zoom}) rotateX(${rotX}deg) rotateZ(${rotZ}deg)` }}
        >
          {/* Default Map Render */}
          {(scenario === 'NORMAL' && mapMode === 'NORMAL') && (
            <>
              {/* Ground Plane */}
              <div className="iso-ground"></div>

              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 1000 800" style={{ transform: 'translateZ(1px)' }}>
                <path d="M 310 240 L 310 800" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
                <path d="M 690 240 L 690 800" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
              </svg>

              {/* Stage Trails */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 1000 800" style={{ transform: 'translateZ(61px)' }}>
                <path d="M 120 140 L 880 140" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
                <path d="M 310 140 L 310 240" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
                <path d="M 500 140 L 500 240" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
                <path d="M 690 140 L 690 240" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
              </svg>

              {/* Stage Block */}
              <div 
                className={`iso-block stage-block cursor-pointer group ${hoveredZone === 'GAMMA_STAGE' ? 'ring-8 ring-brand-yellow/50 z-[200]' : ''}`}
                onMouseEnter={() => useStore.getState().setHoveredZone('GAMMA_STAGE')}
                onMouseLeave={() => useStore.getState().setHoveredZone(null)}
              >
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className={`iso-face face-top flex items-center justify-center border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'GAMMA_STAGE' ? 'bg-white' : 'bg-gray-50'}`}>
                   <span className="font-heavy text-black opacity-30 tracking-widest text-[16px]" style={{ transform: 'rotateX(-90deg) rotateY(45deg)' }}>MAIN STAGE AREA</span>
                </div>
              </div>

              {/* Left Seating Block */}
              <div 
                className={`iso-block seat-left cursor-pointer group ${hoveredZone === 'ALPHA_LEFT' ? 'ring-8 ring-brand-yellow/50 z-[200]' : ''}`}
                onMouseEnter={() => useStore.getState().setHoveredZone('ALPHA_LEFT')}
                onMouseLeave={() => useStore.getState().setHoveredZone(null)}
              >
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className={`iso-face face-top flex flex-col justify-evenly relative p-4 border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'ALPHA_LEFT' ? 'bg-white' : 'bg-gray-200'}`}>
                  {[...Array(10)].map((_, i) => <div key={i} className="w-full h-[6px] bg-black/10 rounded-sm"></div>)}
                </div>
              </div>

              {/* Center Seating Block */}
              <div 
                className={`iso-block seat-center cursor-pointer group ${hoveredZone === 'DELTA_CENTER' ? 'ring-8 ring-brand-yellow/50 z-[200]' : ''}`}
                onMouseEnter={() => useStore.getState().setHoveredZone('DELTA_CENTER')}
                onMouseLeave={() => useStore.getState().setHoveredZone(null)}
              >
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className={`iso-face face-top flex flex-col justify-evenly relative p-4 border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'DELTA_CENTER' ? 'bg-white' : 'bg-gray-200'}`}>
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                    <span className="font-heavy text-black opacity-30 tracking-widest text-[16px]" style={{ transform: 'rotateX(-90deg) rotateY(45deg)' }}>CENTER ZONE</span>
                  </div>
                  {[...Array(10)].map((_, i) => <div key={i} className="w-full h-[6px] bg-black/10 rounded-sm z-0"></div>)}
                </div>
              </div>

              {/* Right Seating Block */}
              <div 
                className={`iso-block seat-right cursor-pointer group ${hoveredZone === 'BETA_RIGHT' ? 'ring-8 ring-brand-yellow/50 z-[200]' : ''}`}
                onMouseEnter={() => useStore.getState().setHoveredZone('BETA_RIGHT')}
                onMouseLeave={() => useStore.getState().setHoveredZone(null)}
              >
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className={`iso-face face-top flex flex-col justify-evenly relative p-4 border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'BETA_RIGHT' ? 'bg-white' : 'bg-gray-200'}`}>
                  {[...Array(10)].map((_, i) => <div key={i} className="w-full h-[6px] bg-black/10 rounded-sm"></div>)}
                </div>
              </div>

              {/* Gate Left — End of Left Pathway */}
              <div className="iso-block gate-left">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top !bg-transparent !border-none flex items-center justify-center">
                  <svg viewBox="0 0 110 100" className="w-full h-full text-black block opacity-90 drop-shadow-md">
                    <rect x="0" y="0" width="10" height="100" fill="currentColor" />
                    <rect x="98" y="0" width="10" height="100" fill="currentColor" />
                    <path d="M 12 0 A 43 100 0 0 1 55 100 M 98 0 A 43 100 0 0 0 55 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              </div>

              {/* Gate Right — End of Right Pathway */}
              <div className="iso-block gate-right">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top !bg-transparent !border-none flex items-center justify-center">
                  <svg viewBox="0 0 110 100" className="w-full h-full text-black block opacity-90 drop-shadow-md">
                    <rect x="0" y="0" width="10" height="100" fill="currentColor" />
                    <rect x="98" y="0" width="10" height="100" fill="currentColor" />
                    <path d="M 12 0 A 43 100 0 0 1 55 100 M 98 0 A 43 100 0 0 0 55 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              </div>
            </>
          )}

          {/* ═══ LOBBY MAP ═══ */}
          {mapMode === 'LOBBY' && scenario === 'NORMAL' && (
            <>
              {/* Wide Floor */}
              <div className="lobby-floor"></div>

              {/* Wraith-around Stairs Outer */}
              <div className="iso-block lobby-stair-1">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Wraith-around Stairs Inner */}
              <div className="iso-block lobby-stair-2">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Central Stage */}
              <div className="iso-block lobby-stage">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Topmost Platform holding the gates */}
              <div className="iso-block lobby-top-platform">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Gate Left */}
              <div className="iso-block lobby-gate-left">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top !bg-transparent !border-none flex items-center justify-center">
                  <svg viewBox="0 0 110 100" className="w-full h-full text-black block opacity-90 drop-shadow-md">
                    <rect x="0" y="0" width="10" height="100" fill="currentColor" />
                    <rect x="98" y="0" width="10" height="100" fill="currentColor" />
                    <path d="M 12 0 A 43 100 0 0 1 55 100 M 98 0 A 43 100 0 0 0 55 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              </div>

              {/* Gate Right */}
              <div className="iso-block lobby-gate-right">
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-top !bg-transparent !border-none flex items-center justify-center">
                  <svg viewBox="0 0 110 100" className="w-full h-full text-black block opacity-90 drop-shadow-md">
                    <rect x="0" y="0" width="10" height="100" fill="currentColor" />
                    <rect x="98" y="0" width="10" height="100" fill="currentColor" />
                    <path d="M 12 0 A 43 100 0 0 1 55 100 M 98 0 A 43 100 0 0 0 55 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              </div>

              {/* (Removed old stair blocks from here as they are integrated above into wraparound stage blocks) */}

              {/* Dashed trails on floor */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50" viewBox="0 0 1000 800" style={{ transform: 'translateZ(1px)' }}>
                <path d="M 500 800 L 500 520" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="3" />
                <path d="M 200 800 L 350 520" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="3" />
                <path d="M 800 800 L 650 520" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="3" />
              </svg>
            </>
          )}

          {/* ═══ ELEVATED TUBE MAP ═══ */}
          {mapMode === 'ELEVATED' && scenario === 'NORMAL' && (
            <>
              {/* Main Horizontal Base */}
              <div className="iso-block tube-ground" style={{ width: '944px', left: '50px', top: '320px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Vertical Branch (Corner Left) */}
              <div className="iso-block tube-ground" style={{ width: '160px', height: '294px', left: '50px', top: '480px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                {/* Omitted face-back to completely nullify any co-planar plane fighting with the horizontal ground edge */}
                <div className="iso-face face-top"></div>
              </div>

              {/* Outer Top Railing */}
              <div className="iso-block tube-railing-horiz" style={{ left: '50px', top: '320px', width: '944px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              {/* Inner Bottom Railing */}
              <div className="iso-block tube-railing-horiz" style={{ left: '210px', top: '472px', width: '784px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Outer Left Railing */}
              <div className="iso-block tube-railing-vert" style={{ left: '50px', top: '328px', height: '446px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>
              {/* Inner Right Railing */}
              <div className="iso-block tube-railing-vert" style={{ left: '202px', top: '480px', height: '294px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div>

              {/* Corner Junction Glass (flush squared block) */}
              {/* <div className="iso-block glass-panel-junction" style={{ left: '58px', top: '328px' }}>
                <div className="iso-face face-front"></div>
                <div className="iso-face face-right"></div>
                <div className="iso-face face-left"></div>
                <div className="iso-face face-back"></div>
                <div className="iso-face face-top"></div>
              </div> */}

              {/* Glass panels — Horizontal leg */}
              {[...Array(7)].map((_, i) => (
                <div key={`h-${i}`} className="iso-block glass-panel-horiz" style={{ left: `${302 + i * 98}px`, top: '328px' }}>
                  <div className="iso-face face-front"></div>
                  <div className="iso-face face-right"></div>
                  <div className="iso-face face-left"></div>
                  <div className="iso-face face-back"></div>
                  <div className="iso-face face-top"></div>
                </div>
              ))}

              {/* Glass panels — Vertical leg */}
              {/* {[...Array(3)].map((_, i) => (
                <div key={`v-${i}`} className="iso-block glass-panel-vert" style={{ left: '58px', top: `${474 + i * 98}px` }}>
                  <div className="iso-face face-front"></div>
                  <div className="iso-face face-right"></div>
                  <div className="iso-face face-left"></div>
                  <div className="iso-face face-back"></div>
                  <div className="iso-face face-top"></div>
                </div>
              ))} */}

              {/* Dashed center line on walkway */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50" viewBox="0 0 1000 800" style={{ transform: 'translateZ(1px)' }}>
                <path d="M 50 400 L 950 400" fill="none" stroke="#FFCC00" strokeDasharray="12 6" strokeWidth="3" />
              </svg>
            </>
          )}

          {/* Dynamic Anchor Nodes */}
          {displayAnchors.map(a => {
            const pos = toCSS(a.x, a.y);
            const isDragging = dragWorker === a.id;
            return <AnchorNode 
                     key={a.id} 
                     left={pos.left} 
                     top={pos.top} 
                     id={a.id} 
                     z={getRenderZ(a, 'anchor')} 
                     rotX={rotX} 
                     rotZ={rotZ} 
                     onMouseDown={isAdminView ? (e) => handleWorkerDragStart(e, a.id, a.x, a.y) : undefined}
                     isDragging={isDragging}
                   />;
          })}

          {/* Dynamic Worker Nodes (draggable in simulation) */}
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
                  z={getRenderZ(w, 'worker')} 
                  status={w.alert} 
                  yaw={headingAngles[w.worker_id] ?? w.yaw ?? 0} 
                  isDragging={isDragging}
                  onMouseDown={isAdminView ? (e) => handleWorkerDragStart(e, w.worker_id, w.x, w.y) : undefined}
                  rotX={rotX}
                  rotZ={rotZ}
                />
            );
          })}
        </div>
      </div>

      {/* Admin Dialog */}
      {showAdmin && (
        <div className="absolute top-6 right-20 z-[99999]">
          <div className="bg-white p-6 border-4 border-black min-w-[320px] shadow-2xl">
            <h2 className="text-xl font-heavy uppercase mb-4 border-b-2 border-black pb-2">Admin: Override Node</h2>
            <form onSubmit={handleAdminSubmit} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1 font-heavy text-sm">
                Target Node:
                <select 
                  className="border-2 border-black p-2 font-mono text-xs"
                  value={adminForm.target_id}
                  onChange={e => loadTargetData(e.target.value)}
                >
                  <optgroup label="Workers">
                    {displayWorkers.map(w => <option key={w.worker_id} value={w.worker_id}>{w.worker_id} ({workerNames[w.worker_id] || 'Unknown'})</option>)}
                  </optgroup>
                  <optgroup label="Anchors">
                    {displayAnchors.map(a => <option key={a.id} value={a.id}>{a.id}</option>)}
                  </optgroup>
                </select>
              </label>

              {!adminForm.target_id.startsWith('ANC_') ? (
                <>
                  <div className="flex gap-2">
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      Force Alert Status:
                      <select
                        className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.alert}
                        onChange={e => setAdminForm({...adminForm, alert: e.target.value})}
                      >
                        <option value="NORMAL">NORMAL</option>
                        <option value="WARNING">WARNING</option>
                        <option value="DANGER">DANGER</option>
                        <option value="OFFLINE">OFFLINE</option>
                      </select>
                    </label>

                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                       Worker Speed:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.speed} onChange={e => setAdminForm({...adminForm, speed: e.target.value})} placeholder="Auto (1.x)" />
                    </label>
                  </div>
                  
                  <div className="flex gap-2">
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      X Logic Coord:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.x} onChange={e => setAdminForm({...adminForm, x: e.target.value})} placeholder="Auto" />
                    </label>
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      Y Logic Coord:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.y} onChange={e => setAdminForm({...adminForm, y: e.target.value})} placeholder="Auto" />
                    </label>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex gap-2">
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      X Physical Coord:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.x} onChange={e => setAdminForm({...adminForm, x: e.target.value})} placeholder="Fixed" />
                    </label>
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      Y Physical Coord:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.y} onChange={e => setAdminForm({...adminForm, y: e.target.value})} placeholder="Fixed" />
                    </label>
                  </div>

                  <div className="flex gap-2">
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      Force CH4:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.ch4} onChange={e => setAdminForm({...adminForm, ch4: e.target.value})} placeholder="Auto" />
                    </label>
                    <label className="flex flex-col gap-1 font-heavy text-sm flex-1">
                      Force CO:
                      <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                        value={adminForm.co} onChange={e => setAdminForm({...adminForm, co: e.target.value})} placeholder="Auto" />
                    </label>
                  </div>
                </>
              )}

              <div className="flex gap-2 mt-4">
                <button type="submit" className="flex-1 bg-brand-yellow border-2 border-black py-2 font-heavy uppercase hover:bg-black hover:text-brand-yellow">Apply</button>
                <button type="button" onClick={async () => {
                   const API_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000';
                   const payload = adminForm.target_id.startsWith('ANC_') ? {anchor_id: adminForm.target_id} : {worker_id: adminForm.target_id};
                   await fetch(`${API_URL}/api/admin/clear_override`, { method: 'POST', body: JSON.stringify(payload)});
                   setShowAdmin(false);
                }} className="flex-1 bg-red-500 text-white border-2 border-black py-2 font-heavy uppercase hover:bg-black">Clear</button>
                <button type="button" onClick={() => setShowAdmin(false)} className="flex-1 bg-gray-200 border-2 border-black py-2 font-heavy uppercase hover:bg-black hover:text-white">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
