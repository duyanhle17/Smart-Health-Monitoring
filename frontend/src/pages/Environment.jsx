import { useState } from 'react';
import useStore from '../store';

const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);
const zoneDisplayName = (id) => id.replace(/_/g, ' ');

export default function Environment() {
  const [activeZoneIdx, setActiveZoneIdx] = useState(0);
  const workers = useStore(s => s.workers);
  const zonesData = useStore(s => s.zones);
  const workerList = Object.values(workers);

  // Zones come from the backend payload — no hardcoded venue list.
  const zoneIds = Object.keys(zonesData);
  const activeZoneId = zoneIds.length ? zoneIds[activeZoneIdx % zoneIds.length] : null;
  const liveZone = (activeZoneId && zonesData[activeZoneId]) || {};
  const zoneWorkers = activeZoneId ? workerList.filter(w => w.zone === activeZoneId) : [];

  const gasAvailable = liveZone.source !== 'unavailable' &&
    isFiniteNumber(liveZone.ch4) && isFiniteNumber(liveZone.co);
  const avgCH4 = gasAvailable ? liveZone.ch4 : 0;
  const avgCO = gasAvailable ? liveZone.co : 0;
  const aqiAvailable = gasAvailable && isFiniteNumber(liveZone.aqi);
  const aqi = aqiAvailable ? liveZone.aqi : 0;
  const aqiT = aqiAvailable ? (aqi <= 3 ? 'HAZARDOUS' : aqi <= 7 ? 'UNHEALTHY' : 'GOOD') : 'NO DATA';

  const ch4C = !gasAvailable ? 'bg-gray-400' : avgCH4 >= 4.0 ? 'bg-brand-red' : avgCH4 >= 2.0 ? 'bg-orange-600' : 'bg-black';
  const coC = !gasAvailable ? 'bg-gray-400' : avgCO >= 120 ? 'bg-brand-red' : avgCO >= 60 ? 'bg-orange-600' : 'bg-black';
  const aqiC = !aqiAvailable ? 'text-gray-500 border-gray-400' : aqi <= 3 ? 'text-brand-red border-brand-red' : aqi <= 7 ? 'text-orange-600 border-orange-600' : 'text-green-600 border-green-600';

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col overflow-auto custom-scrollbar">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-4 uppercase tracking-tighter">ENVIRONMENTAL ANALYTICS</h1>

      <div className="flex gap-4 border-b-4 border-brand-red pb-4 mb-8 shrink-0 flex-wrap">
        {zoneIds.map((id, i) => (
          <button
            key={id}
            onClick={() => setActiveZoneIdx(i)}
            className={`px-6 py-2 border-2 border-black font-heavy uppercase transition-none ${i === activeZoneIdx ? 'bg-black text-white px-8' : 'bg-white text-black hover:bg-gray-200'}`}
          >
            {zoneDisplayName(id)}
          </button>
        ))}
        {zoneIds.length === 0 && (
          <div className="px-6 py-2 border-2 border-dashed border-gray-400 font-heavy uppercase text-gray-400">
            No environmental zones reporting
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-8 shrink-0 mb-8">
        <div className="bg-white border-4 border-black p-6">
          <h2 className="text-xl font-heavy mb-6 uppercase tracking-tight">Toxic Gas Levels (Avg)</h2>
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CH4 (METHANE)</span>
                <span className={`font-heavy tracking-tighter ${gasAvailable && avgCH4 >= 2.0 ? 'text-brand-red animate-pulse' : 'text-black'}`}>{gasAvailable ? `${avgCH4.toFixed(2)} % LEL` : 'NO LIVE SENSOR'}</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200">
                <div className={`h-full ${ch4C} transition-all duration-500`} style={{ width: `${Math.min(100, (avgCH4/5.0)*100)}%` }}></div>
              </div>
            </div>
             <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CO (CARBON MONOXIDE)</span>
                <span className={`font-heavy tracking-tighter ${gasAvailable && avgCO >= 60 ? 'text-brand-red animate-pulse' : 'text-black'}`}>{gasAvailable ? `${avgCO.toFixed(1)} ppm` : 'NO LIVE SENSOR'}</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200">
                <div className={`h-full ${coC} transition-all duration-500`} style={{ width: `${Math.min(100, (avgCO/150)*100)}%` }}></div>
              </div>
            </div>
          </div>
        </div>
        <div className="bg-white border-4 border-black p-6 flex flex-col justify-center items-center relative gap-8">
          <h2 className="text-xl font-heavy uppercase tracking-tight absolute top-6 left-6">Air Quality Index</h2>
          <div className="text-8xl font-heavy tracking-tighter text-center mt-12 flex flex-col items-center">
            {aqiAvailable ? aqi : '—'}<span className="text-3xl font-body text-gray-500">{aqiAvailable ? '/10' : ''}</span>
            <span className={`text-2xl mt-4 px-6 py-2 uppercase border-4 ${aqiC} tracking-widest ${aqiT !== 'GOOD' ? 'animate-pulse' : ''}`}>{aqiT}</span>
          </div>
        </div>
      </div>

      <div className="bg-white border-4 border-black p-6 flex-1 shrink-0">
        <h2 className="text-xl font-heavy mb-6 uppercase tracking-tight border-b-2 border-black pb-2">ZONE WORKERS</h2>
        <div className="grid grid-cols-4 gap-4">
          {zoneWorkers.map(w => (
            <div key={w.worker_id} className={`border-2 p-4 flex flex-col gap-2 ${w.alert !== 'NORMAL' ? 'border-brand-red bg-red-50 text-brand-red' : 'border-black text-black'}`}>
              <div className="font-heavy text-lg border-b-2 border-current pb-1">{w.worker_id}</div>
              <div className="flex justify-between font-headline text-xs"><span>TEMP</span><span className="font-heavy">{typeof w.temp === 'number' ? `${w.temp.toFixed(1)}°C` : '--'}</span></div>
              <div className="flex justify-between font-headline text-xs mb-2"><span>HEART</span><span className="font-heavy">{typeof w.hr === 'number' ? `${Math.round(w.hr)} BPM` : '--'}</span></div>
              <div className={`text-[10px] font-heavy text-center py-1 uppercase tracking-widest ${w.alert !== 'NORMAL' ? 'bg-brand-red text-white animate-pulse' : 'bg-black text-white'}`}>{w.alert}</div>
            </div>
          ))}
          {zoneWorkers.length === 0 && (
            <div className="col-span-4 py-8 text-center text-gray-400 font-heavy uppercase">No personnel detected in this zone</div>
          )}
        </div>
      </div>
    </div>
  );
}
