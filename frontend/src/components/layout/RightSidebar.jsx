import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProgressBar } from '../ui/ProgressBar';
import useStore from '../../store';

const envZones = [
  { name: 'ZONE ALPHA (LEFT)', ch4: 0.12, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 38, co_st: 'WARNING', co_c: 'bg-orange-600', o2: 18.5, o2_st: 'DANGER', o2_c: 'bg-brand-red', v1: 15, v2: 65, v3: 88 },
  { name: 'ZONE BETA (RIGHT)', ch4: 0.05, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 12, co_st: 'SAFE', co_c: 'bg-black', o2: 20.9, o2_st: 'SAFE', o2_c: 'bg-black', v1: 5, v2: 25, v3: 100 },
  { name: 'ZONE GAMMA (STAGE)', ch4: 1.5, ch4_st: 'DANGER', ch4_c: 'bg-brand-red', co: 65, co_st: 'DANGER', co_c: 'bg-brand-red', o2: 19.5, o2_st: 'WARNING', o2_c: 'bg-orange-600', v1: 85, v2: 90, v3: 65 }
];

export default function RightSidebar() {
  const navigate = useNavigate();
  const [idx, setIdx] = useState(0);
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const isConnected = useStore(s => s.isConnected);

  const workerCount = Object.keys(workers).length;
  const anchorCount = anchors.length || 3;

  // Compute live gas from workers (max gas across all workers)
  const workerList = Object.values(workers);
  const liveGas = workerList.length > 0
    ? Math.max(...workerList.map(w => w.gas || 0))
    : null;

  useEffect(() => {
    const i = setInterval(() => setIdx(v => (v + 1) % envZones.length), 4000);
    return () => clearInterval(i);
  }, []);

  const cur = envZones[idx];

  // Override gas display with live data if connected
  const gasVal = liveGas !== null ? liveGas : cur.co;
  const gasSt = gasVal >= 50 ? 'DANGER' : gasVal >= 25 ? 'WARNING' : 'SAFE';
  const gasC = gasSt === 'DANGER' ? 'bg-brand-red' : gasSt === 'WARNING' ? 'bg-orange-600' : 'bg-black';
  const gasV = Math.min(100, (gasVal / 60) * 100);

  return (
    <aside className="fixed right-0 top-20 h-[calc(100vh-7rem)] w-80 z-40 flex flex-col bg-white border-l-4 border-black">
      {/* GAS LEVELS */}
      <div className="p-4 border-b-4 border-black">
        <div className="flex justify-between items-end mb-6 border-b-2 border-black pb-2">
          <h2 className="font-headline font-heavy text-[10px] uppercase leading-none min-h-3" key={cur.name + "T"}>ENV: {cur.name}</h2>
          <button onClick={() => navigate('/environment')} className="text-[8px] font-heavy uppercase hover:text-brand-red transition-colors flex items-center gap-1">VIEW ALL<span className="material-symbols-outlined text-[10px]">open_in_new</span></button>
        </div>
        <div className="space-y-6" key={cur.name}>
          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">METHANE [CH4]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{cur.ch4} % LEL</span>
                <span className={`text-[10px] font-heavy text-white ${cur.ch4_c} px-1`}>{cur.ch4_st}</span>
              </div>
            </div>
            <ProgressBar value={cur.v1} colorClass={cur.ch4_c} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">GAS LEVEL {isConnected ? '(LIVE)' : '[CO]'}</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{gasVal.toFixed(1)} PPM</span>
                <span className={`text-[10px] font-heavy text-white ${gasC} px-1`}>{gasSt}</span>
              </div>
            </div>
            <ProgressBar value={gasV} colorClass={gasC} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">OXYGEN [O2]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{cur.o2} %</span>
                <span className={`text-[10px] font-heavy text-white ${cur.o2_c} px-1`}>{cur.o2_st}</span>
              </div>
            </div>
            <ProgressBar value={cur.v3} colorClass={cur.o2_c} className="h-2" />
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
              <span className={`font-headline font-heavy text-[10px] uppercase ${isConnected ? '' : 'text-brand-red'}`}>{isConnected ? 'STABLE MESH' : 'DISCONNECTED'}</span>
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
