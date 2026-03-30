import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProgressBar } from '../ui/ProgressBar';
import useStore from '../../store';

const envZones = [
  { id: 'ALPHA_LEFT', name: 'ZONE ALPHA (LEFT)', ch4: 0.3, co: 4.0 },
  { id: 'BETA_RIGHT', name: 'ZONE BETA (RIGHT)', ch4: 0.2, co: 3.5 },
  { id: 'GAMMA_STAGE', name: 'ZONE GAMMA (STAGE)', ch4: 0.5, co: 6.0 },
  { id: 'CENTER_PATH', name: 'CENTER PATHWAY', ch4: 0.1, co: 2.0 }
];

export default function RightSidebar() {
  const navigate = useNavigate();
  const [idx, setIdx] = useState(0);
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);
  const hoveredZone = useStore(s => s.hoveredZone);

  const workerCount = Object.keys(workers).length;
  const anchorCount = anchors.length || 3;

  // Sync index with hoveredZone
  useEffect(() => {
    if (hoveredZone) {
      const zoneIdx = envZones.findIndex(z => z.id === hoveredZone);
      if (zoneIdx !== -1) setIdx(zoneIdx);
    }
  }, [hoveredZone]);

  // Auto-cycle only if NOT hovering a zone
  useEffect(() => {
    if (hoveredZone) return; 
    const i = setInterval(() => setIdx(v => (v + 1) % envZones.length), 4000);
    return () => clearInterval(i);
  }, [hoveredZone]);

  const curZoneBase = envZones[idx] || envZones[0];
  const zonesData = useStore(s => s.zones || {});
  const liveZone = zonesData[curZoneBase.id] || {};

  // Final display values priority: Live Zone Data > Base Default
  const ch4Val = liveZone.ch4 !== undefined ? liveZone.ch4 : curZoneBase.ch4;
  const coVal = liveZone.co !== undefined ? liveZone.co : curZoneBase.co;
  const aqiVal = liveZone.aqi !== undefined ? liveZone.aqi : 0;
  
  const ch4St = ch4Val >= 4.0 ? 'DANGER' : ch4Val >= 2.0 ? 'WARNING' : 'SAFE';
  const ch4C = ch4St === 'DANGER' ? 'bg-brand-red' : ch4St === 'WARNING' ? 'bg-orange-600' : 'bg-black';
  const ch4V = Math.min(100, (ch4Val / 5.0) * 100);

  const coSt = coVal >= 120 ? 'DANGER' : coVal >= 60 ? 'WARNING' : 'SAFE';
  const coC = coSt === 'DANGER' ? 'bg-brand-red' : coSt === 'WARNING' ? 'bg-orange-600' : 'bg-black';
  const coV = Math.min(100, (coVal / 150.0) * 100);

  const aqiSt = aqiVal >= 8 ? 'HAZARDOUS' : aqiVal >= 4 ? 'UNHEALTHY' : 'GOOD';
  const aqiC = aqiVal >= 8 ? 'bg-brand-red' : aqiVal >= 4 ? 'bg-orange-600' : 'bg-black';
  const aqiV = Math.min(100, (aqiVal / 10.0) * 100);

  const workerList = Object.values(workers);

  return (
    <aside className="fixed right-0 top-20 h-[calc(100vh-7rem)] w-80 z-40 flex flex-col bg-white border-l-4 border-black">
      {/* AIR QUALITY */}
      <div className="p-4 border-b-4 border-black">
        <div className="flex justify-between items-end mb-6 border-b-2 border-black pb-2">
          <h2 className="font-headline font-heavy text-[10px] uppercase leading-none min-h-3" key={curZoneBase.id + "T"}>ENV: {curZoneBase.name}</h2>
          <button onClick={() => navigate('/environment')} className="text-[8px] font-heavy uppercase hover:text-brand-red transition-colors flex items-center gap-1">VIEW ALL<span className="material-symbols-outlined text-[10px]">open_in_new</span></button>
        </div>
        <div className="space-y-6" key={curZoneBase.id}>
          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">AIR QUALITY</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{aqiVal}/10</span>
                <span className={`text-[10px] font-heavy text-white ${aqiC} px-1`}>{aqiSt}</span>
              </div>
            </div>
            <ProgressBar value={aqiV} colorClass={aqiC} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">METHANE [CH4]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{ch4Val.toFixed(2)} % LEL</span>
                <span className={`text-[10px] font-heavy text-white ${ch4C} px-1`}>{ch4St}</span>
              </div>
            </div>
            <ProgressBar value={ch4V} colorClass={ch4C} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">CARBON MONOXIDE [CO]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{coVal.toFixed(1)} PPM</span>
                <span className={`text-[10px] font-heavy text-white ${coC} px-1`}>{coSt}</span>
              </div>
            </div>
            <ProgressBar value={coV} colorClass={coC} className="h-2" />
          </div>
        </div>
      </div>

      {/* NETWORK STATUS */}
      <div className="p-4 flex-1">
        <h2 className="font-headline font-heavy text-sm uppercase leading-none mb-4">NETWORK</h2>
        <div className="space-y-3">
          <div className={`border-2 border-black p-3 flex items-center justify-between ${isConnected ? 'bg-gray-200' : 'bg-red-100'}`}>
            <div>
              <span className="block font-label text-[8px] font-heavy">MESH-NET v2.4</span>
              <span className={`font-headline font-heavy text-[10px] uppercase ${isConnected ? 'text-green-700' : 'text-brand-red'}`}>{isConnected ? 'STABLE' : 'DISCONNECTED'}</span>
            </div>
            <span className="material-symbols-outlined text-3xl text-black" data-icon="hub">hub</span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="border-2 border-black p-2 bg-white">
              <span className="block font-label text-[8px] font-heavy opacity-60">WORKERS</span>
              <span className="font-headline text-lg font-heavy">{workerCount}</span>
            </div>
            <div className="border-2 border-black p-2 bg-white">
              <span className="block font-label text-[8px] font-heavy opacity-60">ANCHORS</span>
              <span className="font-headline text-lg font-heavy">{anchorCount}</span>
            </div>
          </div>

          <div className="border-2 border-black p-3 bg-gray-100 flex flex-col gap-2">
            <span className="font-label text-[8px] font-heavy uppercase border-b border-black pb-1">Worker Zones</span>
            <div className="text-[8px] font-mono space-y-1">
              {workerList.map(w => (
                <div key={w.worker_id} className={w.alert === 'DANGER' ? 'text-brand-red font-heavy' : 'text-green-700'}>
                  {w.worker_id} → {w.zone || 'UNKNOWN'} [{w.alert}]
                </div>
              ))}
              {workerList.length === 0 && <div className="opacity-50">Waiting for nodes...</div>}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
