import { BorderCard } from '../ui/BorderCard';
import { AlertBadge } from '../ui/AlertBadge';

export default function LeftSidebar() {
  return (
    <aside className="fixed left-0 top-20 h-[calc(100vh-7rem)] w-80 z-40 flex flex-col bg-white border-r-4 border-black">
      <div className="p-4 bg-black text-white flex justify-between items-end">
        <div>
          <h2 className="font-headline font-heavy text-sm uppercase leading-none">PERSONNEL</h2>
          <span className="font-label text-[8px] opacity-70 uppercase">SECTOR-04 ACTIVE SQUAD</span>
        </div>
        <span className="font-headline text-xl font-heavy tabular-nums">12/12</span>
      </div>
      
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* Worker 01 - Normal */}
        <div className="p-4 border-b-2 border-black flex flex-col gap-3 hover:bg-gray-100">
          <div className="flex gap-3">
            <div className="w-12 h-12 bg-black flex items-center justify-center text-white text-[10px] font-heavy shrink-0">IMG</div>
            <div className="flex-1 overflow-hidden">
              <div className="flex justify-between items-center mb-1">
                <span className="font-headline font-heavy text-[10px] uppercase truncate">WORKER_048 [J. VANCE]</span>
              </div>
              <AlertBadge text="STABLE" status="stable" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BorderCard className="p-2 border-2">
              <span className="block font-label text-[8px] font-heavy opacity-60">BPM</span>
              <span className="font-headline text-2xl font-heavy tabular-nums">72</span>
            </BorderCard>
            <BorderCard className="p-2 border-2">
              <span className="block font-label text-[8px] font-heavy opacity-60">TEMP</span>
              <span className="font-headline text-2xl font-heavy tabular-nums">36.5°</span>
            </BorderCard>
          </div>
        </div>

        {/* Worker 02 - ALERT */}
        <div className="p-4 border-b-2 border-black flex flex-col gap-3 bg-red-100/50">
          <div className="flex gap-3">
            <div className="w-12 h-12 bg-brand-red flex items-center justify-center text-white text-[10px] font-heavy shrink-0">IMG</div>
            <div className="flex-1 overflow-hidden">
              <div className="flex justify-between items-center mb-1">
                <span className="font-headline font-heavy text-[10px] uppercase truncate text-brand-red">WORKER_102 [A. CHEN]</span>
              </div>
              <AlertBadge text="FALL DETECTED" status="alert" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BorderCard className="p-2 border-2 border-brand-red bg-white">
              <span className="block font-label text-[8px] font-heavy text-brand-red opacity-60">BPM</span>
              <span className="font-headline text-2xl font-heavy tabular-nums text-brand-red">114</span>
            </BorderCard>
            <BorderCard className="p-2 border-2 border-brand-red bg-white">
              <span className="block font-label text-[8px] font-heavy text-brand-red opacity-60">TEMP</span>
              <span className="font-headline text-2xl font-heavy tabular-nums text-brand-red">39.0°</span>
            </BorderCard>
          </div>
        </div>
      </div>
    </aside>
  );
}
