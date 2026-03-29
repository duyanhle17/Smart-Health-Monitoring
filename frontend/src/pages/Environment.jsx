import { useState } from 'react';

const envZones = [
  { name: 'ZONE ALPHA (LEFT)', ch4: 0.12, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 38, co_st: 'WARNING', co_c: 'bg-orange-600', o2: 18.5, o2_st: 'DANGER', o2_c: 'bg-brand-red', v1: 15, v2: 65, v3: 88, aqi: 152, aqi_t: 'UNHEALTHY', aqi_c: 'text-brand-red border-brand-red', workers: [
    { id: 'WK_048', temp: '36.5°C', hr: '72 BPM', st: 'STABLE', c: 'border-black' },
    { id: 'WK_099', temp: '37.1°C', hr: '80 BPM', st: 'STABLE', c: 'border-black' }
  ]},
  { name: 'ZONE BETA (RIGHT)', ch4: 0.05, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 12, co_st: 'SAFE', co_c: 'bg-gray-800', o2: 20.9, o2_st: 'SAFE', o2_c: 'bg-black', v1: 5, v2: 25, v3: 100, aqi: 45, aqi_t: 'GOOD', aqi_c: 'text-black border-black', workers: [
    { id: 'WK_89', temp: '36.8°C', hr: '82 BPM', st: 'STABLE', c: 'border-black' },
    { id: 'WK_48', temp: '36.4°C', hr: '71 BPM', st: 'STABLE', c: 'border-black' }
  ]},
  { name: 'ZONE GAMMA (STAGE)', ch4: 1.5, ch4_st: 'DANGER', ch4_c: 'bg-brand-red', co: 65, co_st: 'DANGER', co_c: 'bg-brand-red', o2: 19.5, o2_st: 'WARNING', o2_c: 'bg-orange-600', v1: 85, v2: 90, v3: 65, aqi: 240, aqi_t: 'HAZARDOUS', aqi_c: 'text-brand-red border-brand-red', workers: [
    { id: 'WK_102', temp: '39.0°C', hr: '130 BPM', st: 'CRITICAL', c: 'border-brand-red bg-red-100 text-brand-red' }
  ]}
];

export default function Environment() {
  const [activeZone, setActiveZone] = useState(0);
  const cur = envZones[activeZone];

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col overflow-auto custom-scrollbar">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-4 uppercase tracking-tighter">ENVIRONMENTAL ANALYTICS</h1>
      
      <div className="flex gap-4 border-b-4 border-brand-red pb-4 mb-8 shrink-0">
        {envZones.map((z, i) => (
          <button 
            key={z.name} 
            onClick={() => setActiveZone(i)}
            className={`px-6 py-2 border-2 border-black font-heavy uppercase transition-none ${i === activeZone ? 'bg-black text-white px-8' : 'bg-white text-black hover:bg-gray-200'}`}
          >
            {z.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-8 shrink-0 mb-8">
        <div className="bg-white border-4 border-black p-6">
          <h2 className="text-xl font-heavy mb-6 uppercase tracking-tight">Toxic Gas Levels</h2>
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CO (CARBON MONOXIDE)</span>
                <span className={`font-heavy tracking-tighter ${cur.co_c === 'bg-brand-red' ? 'text-brand-red animate-pulse' : 'text-black'}`}>{cur.co} ppm ({cur.co_st})</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200"><div className={`h-full ${cur.co_c}`} style={{ width: `${cur.v2}%` }}></div></div>
            </div>
            <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>CH4 (METHANE)</span>
                <span className={`font-heavy tracking-tighter ${cur.ch4_c === 'bg-brand-red' ? 'text-brand-red animate-pulse' : 'text-black'}`}>{cur.ch4}% LEL ({cur.ch4_st})</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200"><div className={`h-full ${cur.ch4_c}`} style={{ width: `${cur.v1}%` }}></div></div>
            </div>
             <div>
              <div className="flex justify-between font-headline text-xs mb-1">
                <span>O2 (OXYGEN)</span>
                <span className={`font-heavy tracking-tighter ${cur.o2_c === 'bg-brand-red' ? 'text-brand-red animate-pulse' : 'text-black'}`}>{cur.o2}% ({cur.o2_st})</span>
              </div>
              <div className="w-full h-4 border-2 border-black bg-gray-200"><div className={`h-full ${cur.o2_c}`} style={{ width: `${cur.v3}%` }}></div></div>
            </div>
          </div>
        </div>
        <div className="bg-white border-4 border-black p-6 flex flex-col justify-center items-center relative gap-8 relative">
          <h2 className="text-xl font-heavy uppercase tracking-tight absolute top-6 left-6">Air Quality Index</h2>
          <div className="text-8xl font-heavy tracking-tighter text-center mt-12 flex flex-col items-center">
            {cur.aqi}
            <span className={`text-2xl mt-4 px-6 py-2 uppercase border-4 ${cur.aqi_c} tracking-widest ${cur.aqi_t !== 'GOOD' ? 'animate-pulse' : ''}`}>{cur.aqi_t}</span>
          </div>
        </div>
      </div>

      <div className="bg-white border-4 border-black p-6 flex-1 shrink-0">
        <h2 className="text-xl font-heavy mb-6 uppercase tracking-tight border-b-2 border-black pb-2">LOCAL SQUAD VITALS</h2>
        <div className="grid grid-cols-4 gap-4">
          {cur.workers.map(w => (
            <div key={w.id} className={`border-2 p-4 flex flex-col gap-2 ${w.c}`}>
              <div className="font-heavy text-lg border-b-2 border-current pb-1">{w.id}</div>
              <div className="flex justify-between font-headline text-xs"><span>TEMP</span><span className="font-heavy">{w.temp}</span></div>
              <div className="flex justify-between font-headline text-xs mb-2"><span>HEART</span><span className="font-heavy">{w.hr}</span></div>
              <div className={`text-[10px] font-heavy text-center py-1 uppercase tracking-widest ${w.st === 'CRITICAL' ? 'bg-brand-red text-white animate-pulse' : 'bg-black text-white'}`}>{w.st}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
