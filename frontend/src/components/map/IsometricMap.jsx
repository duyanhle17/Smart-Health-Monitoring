import { useState } from 'react';
import useStore from '../../store';

// Coordinate mapping: backend logical (0-100) → CSS px (0-600)
const toCSS = (lx, ly) => ({ left: `${lx * 6}px`, top: `${ly * 6}px` });

// Z-height based on zone
const getZ = (y) => y < 35 ? 62 : (y >= 35 && (true)) ? 2 : 2;
const getBlockZ = (zone) => zone === 'GAMMA_STAGE' ? 62 : zone === 'ALPHA_LEFT' || zone === 'BETA_RIGHT' ? 32 : 2;

const WorkerNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100] group" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px)`, transition: 'left 0.6s ease-out, top 0.6s ease-out' }}>
    <div className="relative flex items-center justify-center cursor-pointer">
      <div className="w-5 h-5 rounded-full bg-brand-red border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-full bg-brand-red opacity-60 animate-ping absolute"></div>
      <div 
        className="fixed whitespace-nowrap bg-black text-white px-3 py-1 text-[10px] font-heavy tracking-widest border-2 border-white z-[500] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-xl"
        style={{ transform: 'translate(-50%, -150%) rotate(0deg)', left: '50%', top: '0px', isolation: 'isolate' }}
      >
        {id}
      </div>
    </div>
  </div>
);

const AnchorNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100] group" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px)` }}>
    <div className="relative flex items-center justify-center cursor-pointer">
      <div className="w-5 h-5 rounded-none bg-brand-yellow border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-none bg-brand-yellow opacity-40 animate-pulse absolute"></div>
      <div 
        className="fixed whitespace-nowrap bg-brand-yellow text-black px-3 py-1 text-[10px] font-heavy tracking-widest border-2 border-black z-[500] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-xl"
        style={{ transform: 'translate(-50%, -150%) rotate(0deg)', left: '50%', top: '0px', isolation: 'isolate' }}
      >
        {id}
      </div>
    </div>
  </div>
);

// Fallback static data when backend is offline
const FALLBACK_ANCHORS = [
  { id: 'ANC_STAGE', x: 50, y: 20 },
  { id: 'ANC_LEFT', x: 15, y: 60 },
  { id: 'ANC_RIGHT', x: 85, y: 60 },
];

const FALLBACK_WORKERS = [
  { worker_id: 'WK_102', x: 50, y: 27, zone: 'GAMMA_STAGE' },
];

export default function IsometricMap() {
  const [zoom, setZoom] = useState(1);
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));
  const handleResetZoom = () => setZoom(1);

  // Use live data or fallback
  const displayAnchors = anchors.length > 0 ? anchors : FALLBACK_ANCHORS;
  const displayWorkers = Object.values(workers).length > 0 ? Object.values(workers) : FALLBACK_WORKERS;

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

      <div className="absolute inset-0 scanline pointer-events-none opacity-20 z-10"></div>

      <div className="iso-container">
        <div 
          className="iso-scene transition-transform duration-300 ease-out" 
          style={{ transform: `scale(${zoom}) rotateX(60deg) rotateZ(-45deg)` }}
        >
          {/* Ground Plane */}
          <div className="iso-ground"></div>

          {/* Ground Trails */}
          <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 600 600" style={{ transform: 'translateZ(1px)' }}>
            <path d="M 300 220 L 300 550" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
            {/* Worker movement trace */}
            {displayWorkers.map(w => {
              const pos = toCSS(w.x, w.y);
              return <circle key={w.worker_id + '-trail'} cx={parseFloat(pos.left)} cy={parseFloat(pos.top)} r="6" fill="#FF0000" opacity="0.4" className="animate-ping" />;
            })}
          </svg>

          {/* Stage Trails */}
          <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 600 600" style={{ transform: 'translateZ(61px)' }}>
            <path d="M 140 130 L 460 130" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
            <path d="M 300 130 L 300 220" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
          </svg>

          {/* Stage Block */}
          <div className="iso-block stage-block">
            <div className="iso-face face-front"></div>
            <div className="iso-face face-right"></div>
            <div className="iso-face face-top flex items-center justify-center bg-gray-50">
               <span className="font-heavy text-black opacity-30 tracking-widest text-[16px]" style={{ transform: 'rotateX(-90deg) rotateY(45deg)' }}>MAIN STAGE AREA</span>
            </div>
          </div>

          {/* Left Seating Block */}
          <div className="iso-block seat-left">
            <div className="iso-face face-front"></div>
            <div className="iso-face face-right"></div>
            <div className="iso-face face-top bg-gray-200"></div>
          </div>

          {/* Right Seating Block */}
          <div className="iso-block seat-right">
            <div className="iso-face face-front"></div>
            <div className="iso-face face-right"></div>
            <div className="iso-face face-top bg-gray-200"></div>
          </div>

          {/* Dynamic Anchor Nodes */}
          {displayAnchors.map(a => {
            const pos = toCSS(a.x, a.y);
            const z = a.y < 35 ? 62 : 32;
            return <AnchorNode key={a.id} left={pos.left} top={pos.top} id={a.id} z={z} />;
          })}

          {/* Dynamic Worker Nodes */}
          {displayWorkers.map(w => {
            const pos = toCSS(w.x, w.y);
            const z = getBlockZ(w.zone || 'CENTER_PATH');
            return <WorkerNode key={w.worker_id} left={pos.left} top={pos.top} id={w.worker_id} z={z} />;
          })}
        </div>
      </div>
    </div>
  );
}
