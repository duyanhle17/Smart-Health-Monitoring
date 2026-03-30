import { useState } from 'react';
import useStore from '../../store';

// Coordinate mapping: backend logical (0-100) → CSS px (0-600)
const toCSS = (lx, ly) => ({ left: `${lx * 6}px`, top: `${ly * 6}px` });

// Z-height based on zone
const getZ = (y) => y < 35 ? 62 : (y >= 35 && (true)) ? 2 : 2;
const getBlockZ = (zone) => zone === 'GAMMA_STAGE' ? 62 : zone === 'ALPHA_LEFT' || zone === 'BETA_RIGHT' ? 32 : 2;

const workerNames = {
  'WK_102': 'Trung Nam',
  'WK_048': 'Duy Anh',
  'WK_089': 'Quoc Khanh',
  'WK_004': 'Ngoc Diem',
  'WK_055': 'Thanh Tran',
  'WK_077': 'Son Tung'
};

const WorkerNode = ({ left, top, id, z = 2, status = 'NORMAL' }) => {
  const isOffline = status === 'OFFLINE';
  const isDanger = status === 'DANGER';
  const displayName = workerNames[id] || id;
  return (
  <div className="absolute z-[100] group" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px)`, transformStyle: 'preserve-3d', transition: 'left 0.8s linear, top 0.8s linear' }}>
    <div className="relative flex items-center justify-center cursor-pointer" style={{ transformStyle: 'preserve-3d' }}>
      <div className={`w-5 h-5 rounded-full ${isOffline ? 'bg-gray-800 border-gray-500 grayscale opacity-80' : 'bg-brand-red border-black'} border-2 absolute z-10 shadow-lg`}></div>
      
      {!isOffline && !isDanger && <div className="w-10 h-10 rounded-full bg-brand-red opacity-60 animate-ping absolute"></div>}
      {isDanger && !isOffline && <div className="w-10 h-10 rounded-full bg-brand-red animate-radiate absolute pointer-events-none"></div>}
      
      {isOffline && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full border-4 border-brand-red animate-radar-ping pointer-events-none"></div>
      )}

      <div 
        className={`absolute z-[999] ${isOffline ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-none pointer-events-none drop-shadow-2xl`}
        style={{ transform: 'rotateZ(45deg) rotateX(-60deg) translate(-50%, -50%) translateZ(150px) scale(0.5)', left: '50%', top: '0px' }}
      >
        <div className={`whitespace-nowrap ${isOffline ? 'bg-brand-red text-white animate-glitch' : 'bg-black text-white'} px-8 py-3 text-2xl font-heavy tracking-widest border-[6px] border-white`} style={{ WebkitFontSmoothing: 'antialiased', backfaceVisibility: 'hidden' }}>
          {displayName}
        </div>
      </div>
    </div>
  </div>
)};

const AnchorNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100] group" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px)`, transformStyle: 'preserve-3d' }}>
    <div className="relative flex items-center justify-center cursor-pointer" style={{ transformStyle: 'preserve-3d' }}>
      <div className="w-5 h-5 rounded-none bg-brand-yellow border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-none bg-brand-yellow opacity-40 animate-pulse absolute"></div>
      <div 
        className="absolute z-[999] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-2xl"
        style={{ transform: 'rotateZ(45deg) rotateX(-60deg) translate(-50%, -30%) translateZ(100px) scale(0.5)', left: '50%', top: '0px' }}
      >
        <div className="whitespace-nowrap bg-brand-yellow text-black px-8 py-3 text-2xl font-heavy tracking-widest border-[6px] border-black" style={{ WebkitFontSmoothing: 'antialiased', backfaceVisibility: 'hidden' }}>
          {id}
        </div>
      </div>
    </div>
  </div>
);

// Fallback static data when backend is offline
const FALLBACK_ANCHORS = [
  { id: 'ANC_STAGE', x: 50, y: 20 },
  { id: 'ANC_LEFT', x: 30, y: 60 },
  { id: 'ANC_RIGHT', x: 70, y: 60 },
];

const FALLBACK_WORKERS = [
  { worker_id: 'WK_102', x: 50, y: 27, zone: 'GAMMA_STAGE' },
];

const SCENARIO_ANCHORS = {
  CAVE_IN: [
    { id: 'ANC_DEEP_X1', x: 80, y: -13, z: 50 },
    { id: 'ANC_UPPER_L', x: 10, y: 80, z: 2 },
    { id: 'ANC_UPPER_R', x: 73, y: 75, z: 2 }
  ],
  EVACUATION: [
    { id: 'ANC_EXIT_A', x: 10, y: 85, z: 2 },
    { id: 'ANC_EXIT_B', x: 90, y: 85, z: 2 },
    { id: 'ANC_MID_PUMP', x: 50, y: 40, z: 2 },
    { id: 'ANC_CORE_SHAFT', x: 50, y: 10, z: 2 }
  ]
};

const SCENARIO_WORKERS = {
  CAVE_IN: [
    { worker_id: 'WK_004', x: 52, y: 28, alert: 'OFFLINE', zone: 'CAVE_ZONE', z: 2 },
    { worker_id: 'WK_102', x: 48, y: 32, alert: 'DANGER', zone: 'CAVE_ZONE', z: 2 },
    { worker_id: 'WK_089', x: 45, y: 35, alert: 'WARNING', zone: 'CAVE_ZONE', z: 2 },
    { worker_id: 'WK_048', x: 25, y: 65, alert: 'NORMAL', zone: 'SAFE_ZONE', z: 2 },
    { worker_id: 'WK_055', x: 75, y: 65, alert: 'NORMAL', zone: 'SAFE_ZONE', z: 2 }
  ],
  EVACUATION: [
    { worker_id: 'WK_048', x: 15, y: 85, alert: 'WARNING', zone: 'EVAC_ROUTE', z: 2 },
    { worker_id: 'WK_089', x: 12, y: 88, alert: 'NORMAL', zone: 'EVAC_ROUTE', z: 2 },
    { worker_id: 'WK_055', x: 85, y: 85, alert: 'WARNING', zone: 'EVAC_ROUTE', z: 2 },
    { worker_id: 'WK_077', x: 88, y: 88, alert: 'NORMAL', zone: 'EVAC_ROUTE', z: 2 },
    { worker_id: 'WK_102', x: 50, y: 60, alert: 'DANGER', zone: 'CENTER_PATH', z: 2 },
    { worker_id: 'WK_004', x: 50, y: 55, alert: 'WARNING', zone: 'CENTER_PATH', z: 2 }
  ]
};

export default function IsometricMap() {
  const [zoom, setZoom] = useState(1);
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);
  const scenario = useStore(s => s.scenario);
  const hoveredZone = useStore(s => s.hoveredZone);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));
  const handleResetZoom = () => setZoom(1);

  // Use live data or fallback, EXCEPT when in a custom scenario
  const displayAnchors = scenario === 'NORMAL' 
    ? (anchors.length > 0 ? anchors : FALLBACK_ANCHORS)
    : (SCENARIO_ANCHORS[scenario] || FALLBACK_ANCHORS);
    
  const displayWorkers = scenario === 'NORMAL'
    ? (Object.values(workers).length > 0 ? Object.values(workers) : FALLBACK_WORKERS)
    : (SCENARIO_WORKERS[scenario] || FALLBACK_WORKERS);

  return (
    <div className="relative w-full h-full bg-gray-100 flex-1 overflow-hidden flex flex-col justify-center items-center">
      {/* Connection indicator */}
      <div className={`absolute bottom-6 left-6 z-20 flex items-center gap-2 text-[10px] font-heavy uppercase ${isConnected ? 'text-green-700' : 'text-gray-400'}`}>
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></div>
        {isConnected ? 'LIVE' : 'OFFLINE'}
      </div>

      {/* Map Controls */}
      <div className="absolute top-6 right-6 z-20 flex flex-col">
        <button onClick={handleZoomIn} className="w-10 h-10 bg-white border-2 border-black flex items-center justify-center font-heavy hover:bg-black hover:text-white transition-none">+</button>
        <button onClick={handleZoomOut} className="w-10 h-10 bg-white border-2 border-black border-t-0 flex items-center justify-center font-heavy hover:bg-black hover:text-white transition-none">−</button>
        <button onClick={handleResetZoom} className="w-10 h-10 bg-white border-2 border-black flex items-center justify-center hover:bg-black hover:text-white transition-none mt-4">
          <span className="material-symbols-outlined text-lg" data-icon="my_location">my_location</span>
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

      {/* New map backgrounds for scenarios */}
      {scenario === 'EVACUATION' && <img src="/map_cave_in.png" alt="Cave In Map" className="absolute object-cover w-full h-full opacity-30 z-0 select-none grayscale" />}
      {scenario === 'CAVE_IN' && <img src="/map_cave_in.png" alt="Evacuation Map" className="absolute object-cover w-[80%] h-full opacity-40 z-0 select-none brightness-75 mix-blend-multiply" />}

      {/* Red Overlay for Evacuation */}
      {scenario === 'EVACUATION' && (
        <div className="absolute inset-0 bg-red-900/30 mix-blend-multiply pointer-events-none z-10 transition-colors duration-1000 animate-pulse"></div>
      )}

      <div className="iso-container -ml-20">
        <div 
          className="iso-scene transition-transform duration-300 ease-out" 
          style={{ transform: `scale(${zoom}) rotateX(60deg) rotateZ(-45deg)` }}
        >
          {/* Default Map Render */}
          {scenario === 'NORMAL' && (
            <>
              {/* Ground Plane */}
              <div className="iso-ground"></div>

              {/* Ground Trails */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 600 600" style={{ transform: 'translateZ(1px)' }}>
                <path d="M 300 220 L 300 550" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
              </svg>

              {/* Stage Trails */}
              <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 600 600" style={{ transform: 'translateZ(61px)' }}>
                <path d="M 140 130 L 460 130" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
                <path d="M 300 130 L 300 220" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
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
                <div className={`iso-face face-top flex flex-col justify-evenly p-4 border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'ALPHA_LEFT' ? 'bg-white' : 'bg-gray-200'}`}>
                  {[...Array(6)].map((_, i) => <div key={i} className="w-full h-3 bg-black/10 rounded-sm"></div>)}
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
                <div className={`iso-face face-top flex flex-col justify-evenly p-4 border-gray-400 group-hover:bg-white transition-colors ${hoveredZone === 'BETA_RIGHT' ? 'bg-white' : 'bg-gray-200'}`}>
                  {[...Array(6)].map((_, i) => <div key={i} className="w-full h-3 bg-black/10 rounded-sm"></div>)}
                </div>
              </div>
            </>
          )}

          {/* Dynamic Anchor Nodes */}
          {displayAnchors.map(a => {
            const pos = toCSS(a.x, a.y);
            const z = a.z !== undefined ? a.z : (a.y < 35 ? 62 : 32);
            return <AnchorNode key={a.id} left={pos.left} top={pos.top} id={a.id} z={z} />;
          })}

          {/* Dynamic Worker Nodes */}
          {displayWorkers.map(w => {
            const pos = toCSS(w.x, w.y);
            // Default 3D z-mapping for Normal, allow override for scenarios
            const z = w.z !== undefined ? w.z : getBlockZ(w.zone || 'CENTER_PATH');
            return <WorkerNode key={w.worker_id} left={pos.left} top={pos.top} id={w.worker_id} z={z} status={w.alert} />;
          })}
        </div>
      </div>
    </div>
  );
}
