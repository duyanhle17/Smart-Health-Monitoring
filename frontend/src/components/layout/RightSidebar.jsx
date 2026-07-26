import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProgressBar } from '../ui/ProgressBar';
import useStore from '../../store';

const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);
const zoneDisplayName = (id) => id.replace(/_/g, ' ');

export default function RightSidebar() {
  const navigate = useNavigate();
  const [idx, setIdx] = useState(0);
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);
  const hoveredZone = useStore(s => s.hoveredZone);
  const hiddenNodes = useStore(s => s.hiddenNodes);
  const zonesData = useStore(s => s.zones || {});

  const workerList = Object.values(workers).filter(w => !hiddenNodes[w.worker_id]);
  const workerCount = workerList.length;
  const anchorCount = anchors.filter(a => !hiddenNodes[a.id]).length;

  // Environmental zones come from the backend payload — no hardcoded venue list.
  const zoneIds = Object.keys(zonesData);
  const zoneKey = zoneIds.join(',');

  // Sync index with hoveredZone
  useEffect(() => {
    if (hoveredZone) {
      const zoneIdx = zoneKey.split(',').indexOf(hoveredZone);
      if (zoneIdx !== -1) setIdx(zoneIdx);
    }
  }, [hoveredZone, zoneKey]);

  // Auto-cycle only if NOT hovering a zone
  useEffect(() => {
    if (hoveredZone || zoneIds.length < 2) return;
    const i = setInterval(() => setIdx(v => (v + 1) % zoneIds.length), 4000);
    return () => clearInterval(i);
  }, [hoveredZone, zoneIds.length]);

  const curZoneId = zoneIds.length ? zoneIds[idx % zoneIds.length] : null;
  const liveZone = (curZoneId && zonesData[curZoneId]) || {};

  const gasAvailable = liveZone.source !== 'unavailable' &&
    isFiniteNumber(liveZone.ch4) && isFiniteNumber(liveZone.co);
  const ch4Val = gasAvailable ? liveZone.ch4 : 0;
  const coVal = gasAvailable ? liveZone.co : 0;
  const aqiAvailable = gasAvailable && isFiniteNumber(liveZone.aqi);
  const aqiVal = aqiAvailable ? liveZone.aqi : 0;

  const ch4St = gasAvailable ? (ch4Val >= 4.0 ? 'DANGER' : ch4Val >= 2.0 ? 'WARNING' : 'SAFE') : 'NO DATA';
  const ch4C = !gasAvailable ? 'bg-gray-400' : ch4St === 'DANGER' ? 'bg-brand-red' : ch4St === 'WARNING' ? 'bg-orange-600' : 'bg-black';
  const ch4V = Math.min(100, (ch4Val / 5.0) * 100);

  const coSt = gasAvailable ? (coVal >= 120 ? 'DANGER' : coVal >= 60 ? 'WARNING' : 'SAFE') : 'NO DATA';
  const coC = !gasAvailable ? 'bg-gray-400' : coSt === 'DANGER' ? 'bg-brand-red' : coSt === 'WARNING' ? 'bg-orange-600' : 'bg-black';
  const coV = Math.min(100, (coVal / 150.0) * 100);

  const aqiSt = aqiAvailable ? (aqiVal <= 3 ? 'HAZARDOUS' : aqiVal <= 7 ? 'UNHEALTHY' : 'GOOD') : 'NO DATA';
  const aqiC = !aqiAvailable ? 'bg-gray-400' : aqiVal <= 3 ? 'bg-brand-red' : aqiVal <= 7 ? 'bg-orange-600' : 'bg-green-500';
  const aqiV = Math.min(100, (aqiVal / 10.0) * 100);

  return (
    <aside className="w-80 shrink-0 min-h-0 flex flex-col bg-white border-l-4 border-black">
      {/* AIR QUALITY */}
      <div className="p-4 border-b-4 border-black">
        <div className="flex justify-between items-end mb-6 border-b-2 border-black pb-2">
          <h2 className="font-headline font-heavy text-[10px] uppercase leading-none min-h-3" key={(curZoneId || 'none') + "T"}>
            ENV: {curZoneId ? zoneDisplayName(curZoneId) : 'NO ZONES REPORTING'}
          </h2>
          <button onClick={() => navigate('/environment')} className="text-[8px] font-heavy uppercase hover:text-brand-red transition-colors flex items-center gap-1">VIEW ALL<span className="material-symbols-outlined text-[10px]">open_in_new</span></button>
        </div>
        <div className="space-y-6" key={curZoneId || 'none'}>
          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">AIR QUALITY</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{aqiAvailable ? `${aqiVal}/10` : '—'}</span>
                <span className={`text-[10px] font-heavy text-white ${aqiC} px-1`}>{aqiSt}</span>
              </div>
            </div>
            <ProgressBar value={aqiV} colorClass={aqiC} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">METHANE [CH4]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{gasAvailable ? `${ch4Val.toFixed(2)} % LEL` : 'NO LIVE SENSOR'}</span>
                <span className={`text-[10px] font-heavy text-white ${ch4C} px-1`}>{ch4St}</span>
              </div>
            </div>
            <ProgressBar value={ch4V} colorClass={ch4C} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">CARBON MONOXIDE [CO]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{gasAvailable ? `${coVal.toFixed(1)} PPM` : 'NO LIVE SENSOR'}</span>
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
              <span className="block font-label text-[8px] font-heavy">TELEMETRY LINK</span>
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
              {workerList.map(w => {
                let colorClass = 'text-green-700'; // NORMAL
                const alertType = w.fall_status === 'FALL' ? 'FALL' : w.alert;
                if (alertType === 'DANGER' || alertType === 'FALL') colorClass = 'text-brand-red font-heavy';
                else if (alertType === 'WARNING') colorClass = 'text-orange-600 font-heavy';
                else if (alertType === 'OFFLINE') colorClass = 'text-gray-500 opacity-60';

                return (
                  <div key={w.worker_id} className={colorClass}>
                    {w.worker_id} → {w.zone || 'UNKNOWN'} [{alertType}]
                  </div>
                );
              })}
              {workerList.length === 0 && <div className="opacity-50">Waiting for nodes...</div>}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
