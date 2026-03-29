import { ProgressBar } from '../ui/ProgressBar';

export default function RightSidebar() {
  return (
    <aside className="fixed right-0 top-20 h-[calc(100vh-7rem)] w-80 z-40 flex flex-col bg-white border-l-4 border-black">
      {/* GAS LEVELS */}
      <div className="p-4 border-b-4 border-black">
        <h2 className="font-headline font-heavy text-sm uppercase leading-none mb-6">ENVIRONMENT</h2>
        <div className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">METHANE [CH4]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">0.12 % LEL</span>
                <span className="text-[10px] font-heavy text-white bg-black px-1">SAFE</span>
              </div>
            </div>
            <ProgressBar value={15} colorClass="bg-black" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">CARBON MONOXIDE [CO]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">38 PPM</span>
                <span className="text-[10px] font-heavy text-white bg-orange-600 px-1">WARNING</span>
              </div>
            </div>
            <ProgressBar value={65} colorClass="bg-orange-600" />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-end">
              <span className="font-label text-[8px] font-heavy">OXYGEN [O2]</span>
              <div className="flex flex-col items-end">
                <span className="text-[8px] font-heavy opacity-60">18.5 %</span>
                <span className="text-[10px] font-heavy text-white bg-brand-red px-1">DANGER</span>
              </div>
            </div>
            <ProgressBar value={88} colorClass="bg-brand-red" />
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
