import { useState } from 'react';

const WorkerNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100] group" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px)` }}>
    <div className="relative flex items-center justify-center cursor-pointer">
      <div className="w-5 h-5 rounded-full bg-brand-red border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-full bg-brand-red opacity-60 animate-ping absolute"></div>
      <div 
        className="absolute whitespace-nowrap bg-black text-white px-3 py-1 text-[10px] font-heavy tracking-widest border-2 border-white z-[200] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-lg"
        style={{ transform: 'translateZ(100px) rotateZ(45deg) rotateX(-60deg) translate(0px, -40px)' }}
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
        className="absolute whitespace-nowrap bg-brand-yellow text-black px-3 py-1 text-[10px] font-heavy tracking-widest border-2 border-black z-[200] opacity-0 group-hover:opacity-100 transition-none pointer-events-none drop-shadow-lg"
        style={{ transform: 'translateZ(100px) rotateZ(45deg) rotateX(-60deg) translate(0px, -40px)' }}
      >
        {id}
      </div>
    </div>
  </div>
);

export default function IsometricMap() {
  const [zoom, setZoom] = useState(1);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));
  const handleResetZoom = () => setZoom(1);

  return (
    <div className="relative w-full h-full bg-gray-100 flex-1 overflow-hidden flex flex-col justify-center items-center">
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
            <div className="w-4 h-4 bg-brand-red rounded-full border-2 border-black relative"><div className="w-full h-full rounded-full bg-brand-red animate-ping absolute"></div></div> Worker Node
          </div>
          <div className="flex items-center gap-4">
            <div className="w-4 h-4 bg-brand-yellow border-2 border-black relative"><div className="w-full h-full rounded-none bg-brand-yellow animate-pulse absolute"></div></div> Anchor Point
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
            {/* Red worker trace on ground */}
            <path className="animate-pulse" d="M 300 550 L 300 220" fill="none" stroke="#FF0000" strokeDasharray="4 4" strokeWidth="4"></path>
          </svg>

          {/* Stage Trails (Elevated to z=61) */}
          <svg className="absolute w-full h-full top-0 left-0 pointer-events-none z-50 trails-layer" viewBox="0 0 600 600" style={{ transform: 'translateZ(61px)' }}>
            <path d="M 140 130 L 460 130" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
            <path d="M 300 130 L 300 220" fill="none" stroke="#FFCC00" strokeDasharray="8 4" strokeWidth="4"></path>
            {/* Red worker trace on stage towards center */}
            <path className="animate-pulse" d="M 300 220 L 300 160" fill="none" stroke="#FF0000" strokeDasharray="4 4" strokeWidth="4"></path>
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

          {/* Anchor Nodes */}
          {/* Stage Middle */}
          <AnchorNode left="300px" top="130px" id="ANC_STAGE" z={62} />
          {/* Far Left Block */}
          <AnchorNode left="160px" top="360px" id="ANC_LEFT" z={32} />
          {/* Far Right Block */}
          <AnchorNode left="440px" top="360px" id="ANC_RIGHT" z={32} />

          {/* Worker Node moving up to stage */}
          <WorkerNode left="300px" top="160px" id="WK_102" z={62} />
        </div>
      </div>
    </div>
  );
}
