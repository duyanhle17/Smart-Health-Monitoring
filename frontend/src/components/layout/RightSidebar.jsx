import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProgressBar } from '../ui/ProgressBar';

const envZones = [
  { name: 'ZONE ALPHA (LEFT)', ch4: 0.12, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 38, co_st: 'WARNING', co_c: 'bg-orange-600', o2: 18.5, o2_st: 'DANGER', o2_c: 'bg-brand-red', v1: 15, v2: 65, v3: 88 },
  { name: 'ZONE BETA (RIGHT)', ch4: 0.05, ch4_st: 'SAFE', ch4_c: 'bg-black', co: 12, co_st: 'SAFE', co_c: 'bg-black', o2: 20.9, o2_st: 'SAFE', o2_c: 'bg-black', v1: 5, v2: 25, v3: 100 },
  { name: 'ZONE GAMMA (STAGE)', ch4: 1.5, ch4_st: 'DANGER', ch4_c: 'bg-brand-red', co: 65, co_st: 'DANGER', co_c: 'bg-brand-red', o2: 19.5, o2_st: 'WARNING', o2_c: 'bg-orange-600', v1: 85, v2: 90, v3: 65 }
];

export default function RightSidebar() {
  const navigate = useNavigate();
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const i = setInterval(() => setIdx(v => (v + 1) % envZones.length), 4000);
    return () => clearInterval(i);
  }, []);

  const cur = envZones[idx];

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
              <span className="font-label text-[8px] font-heavy">CARBON MONOXIDE [CO]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">{cur.co} PPM</span>
                <span className={`text-[10px] font-heavy text-white ${cur.co_c} px-1`}>{cur.co_st}</span>
              </div>
            </div>
            <ProgressBar value={cur.v2} colorClass={cur.co_c} className="h-2" />
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
          <div className="border-2 border-black p-3 bg-gray-200 flex items-center justify-between">
            <div>
              <span className="block font-label text-[8px] font-heavy">MESH-NET v2.4</span>
              <span className="font-headline font-heavy text-[10px] uppercase">STABLE MESH</span>
            </div>
            <span className="material-symbols-outlined text-3xl text-black" data-icon="hub">hub</span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="border-2 border-black p-2 bg-white">
              <span className="block font-label text-[8px] font-heavy opacity-60">NODES</span>
              <span className="font-headline text-lg font-heavy">24/24</span>
            </div>
            <div className="border-2 border-black p-2 bg-white">
              <span className="block font-label text-[8px] font-heavy opacity-60">LATENCY</span>
              <span className="font-headline text-lg font-heavy">12ms</span>
            </div>
          </div>

          <div className="border-2 border-black p-3 bg-gray-100 flex flex-col gap-2">
            <span className="font-label text-[8px] font-heavy uppercase border-b border-black pb-1">Routing Logs</span>
            <div className="text-[8px] font-mono space-y-1">
              <div className="text-green-700">NODE_B2 -&gt; NODE_A1 [OK]</div>
              <div className="text-green-700">NODE_C4 -&gt; NODE_B2 [OK]</div>
              <div className="text-orange-600 font-heavy">NODE_D1 -&gt; RE-ROUTING...</div>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
