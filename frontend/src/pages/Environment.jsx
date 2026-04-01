import { useState } from 'react';
import useStore from '../store';

const ZONES = [
  { id: 'ALPHA_LEFT', name: 'ZONE ALPHA (LEFT)' },
  { id: 'BETA_RIGHT', name: 'ZONE BETA (RIGHT)' },
  { id: 'GAMMA_STAGE', name: 'ZONE GAMMA (STAGE)' },
  { id: 'CENTER_PATH', name: 'CENTER PATHWAY' }
];

export default function Environment() {
  const [activeZoneIdx, setActiveZoneIdx] = useState(0);
  const workers = useStore(s => s.workers);
  const zonesData = useStore(s => s.zones);
  const workerList = Object.values(workers);
  
  const activeZone = ZONES[activeZoneIdx];
  const liveZone = zonesData[activeZone.id] || {};
  const zoneWorkers = workerList.filter(w => w.zone === activeZone.id);

  // Use live zone-wide data from backend
  const avgCH4 = liveZone.ch4 !== undefined ? liveZone.ch4 : 0.5;
  const avgCO = liveZone.co !== undefined ? liveZone.co : 5.0;
  const gasSt = liveZone.status || 'SAFE';
  
  const aqi = liveZone.aqi !== undefined ? liveZone.aqi : 10;
  const aqiT = aqi <= 3 ? 'HAZARDOUS' : aqi <= 7 ? 'UNHEALTHY' : 'GOOD';
  
  const ch4C = avgCH4 >= 4.0 ? 'bg-brand-red' : avgCH4 >= 2.0 ? 'bg-orange-600' : 'bg-black';
  const coC = avgCO >= 120 ? 'bg-brand-red' : avgCO >= 60 ? 'bg-orange-600' : 'bg-black';
  const aqiC = aqi <= 3 ? 'text-brand-red border-brand-red' : aqi <= 7 ? 'text-orange-600 border-orange-600' : 'text-green-600 border-green-600';

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col overflow-auto custom-scrollbar">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-4 uppercase tracking-tighter">ENVIRONMENTAL ANALYTICS</h1>
      
      <div className="flex gap-4 border-b-4 border-brand-red pb-4 mb-8 shrink-0">
        {ZONES.map((z, i) => (
          <button 
            key={z.id} 
            onClick={() => setActiveZoneIdx(i)}
            className={`px-6 py-2 border-2 border-black font-heavy uppercase transition-none ${i === activeZoneIdx ? 'bg-black text-white px-8' : 'bg-white text-black hover:bg-gray-200'}`}
          >
            {z.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-8 shrink-0 mb-8">
        <div className="bg-white border-4 border-black p-6">
          <h2 className="text-xl font-heavy mb-6 uppercase tracking-tight">Toxic Gas Levels (Avg)</h2>
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CH4 (METHANE)</span>
                <span className={`font-heavy tracking-tighter ${avgCH4 >= 2.0 ? 'text-brand-red animate-pulse' : 'text-black'}`}>{avgCH4.toFixed(2)} % LEL</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200">
                <div className={`h-full ${ch4C} transition-all duration-500`} style={{ width: `${Math.min(100, (avgCH4/5.0)*100)}%` }}></div>
              </div>
            </div>
             <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CO (CARBON MONOXIDE)</span>
                <span className={`font-heavy tracking-tighter ${avgCO >= 60 ? 'text-brand-red animate-pulse' : 'text-black'}`}>{avgCO.toFixed(1)} ppm</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200">
                <div className={`h-full ${coC} transition-all duration-500`} style={{ width: `${Math.min(100, (avgCO/150)*100)}%` }}></div>
              </div>
            </div>
          </div>
        </div>
        <div className="bg-white border-4 border-black p-6 flex flex-col justify-center items-center relative gap-8 relative">
          <h2 className="text-xl font-heavy uppercase tracking-tight absolute top-6 left-6">Air Quality Index</h2>
          <div className="text-8xl font-heavy tracking-tighter text-center mt-12 flex flex-col items-center">
            {aqi}<span className="text-3xl font-body text-gray-500">/10</span>
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
              <div className="flex justify-between font-headline text-xs"><span>TEMP</span><span className="font-heavy">{w.temp?.toFixed(1)}°C</span></div>
              <div className="flex justify-between font-headline text-xs mb-2"><span>HEART</span><span className="font-heavy">{Math.round(w.hr)} BPM</span></div>
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
