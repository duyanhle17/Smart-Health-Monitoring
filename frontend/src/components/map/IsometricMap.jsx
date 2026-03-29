import { useState } from 'react';

const WorkerNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100]" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px) rotateZ(45deg) rotateX(-60deg)` }}>
    <div className="relative flex items-center justify-center">
      <div className="w-5 h-5 rounded-full bg-brand-red border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-full bg-brand-red opacity-60 animate-ping absolute"></div>
      <div className="absolute top-6 whitespace-nowrap bg-black text-white px-2 py-0.5 text-[8px] font-heavy tracking-widest border border-white z-20">{id}</div>
    </div>
  </div>
);

const AnchorNode = ({ left, top, id, z = 2 }) => (
  <div className="absolute z-[100]" style={{ left, top, transform: `translate(-50%, -50%) translateZ(${z}px) rotateZ(45deg) rotateX(-60deg)` }}>
    <div className="relative flex items-center justify-center">
      <div className="w-5 h-5 rounded-none bg-brand-yellow border-2 border-black absolute z-10 shadow-lg"></div>
      <div className="w-10 h-10 rounded-none bg-brand-yellow opacity-40 animate-pulse absolute"></div>
      <div className="absolute top-6 whitespace-nowrap bg-brand-yellow text-black px-2 py-0.5 text-[8px] font-heavy tracking-widest border border-black z-20">{id}</div>
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
          </svg>

          {/* Stage Trails (Elevated to z=61) */}
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

          {/* Anchor Nodes (T-Shape on Stage + Path) */}
          {/* On Stage (z=62) */}
          <AnchorNode left="140px" top="130px" id="ANC_L1" z={62} />
          <AnchorNode left="220px" top="130px" id="ANC_L2" z={62} />
          <AnchorNode left="300px" top="130px" id="ANC_C0" z={62} />
          <AnchorNode left="380px" top="130px" id="ANC_R1" z={62} />
          <AnchorNode left="460px" top="130px" id="ANC_R2" z={62} />
          {/* On Ground Center Path (z=2) */}
          <AnchorNode left="300px" top="280px" id="ANC_C1" />
          <AnchorNode left="300px" top="400px" id="ANC_C2" />
          <AnchorNode left="300px" top="520px" id="ANC_C3" />

          {/* Worker Nodes on Side Boxes (z=32) */}
          {/* Left Box */}
          <WorkerNode left="160px" top="360px" id="WK_102" z={32} />
          <WorkerNode left="200px" top="460px" id="WK_04" z={32} />
          {/* Right Box */}
          <WorkerNode left="400px" top="350px" id="WK_89" z={32} />
          <WorkerNode left="460px" top="480px" id="WK_48" z={32} />
        </div>
      </div>
    </div>
  );
}
