import { BorderCard } from '../ui/BorderCard';
import { AlertBadge } from '../ui/AlertBadge';
import useStore from '../../store';

const statusMap = {
  DANGER: { text: 'DANGER', status: 'alert' },
  WARNING: { text: 'WARNING', status: 'alert' },
  NORMAL: { text: 'STABLE', status: 'stable' },
  FALL: { text: 'FALL DETECTED', status: 'alert' },
  OFFLINE: { text: 'SIGNAL LOST', status: 'alert' },
};

const workerNames = {
  'WK_102': 'A. Chen',
  'WK_048': 'J. Vance',
  'WK_089': 'M. Johnson',
  'WK_004': 'E. Davis'
};

export default function LeftSidebar() {
  const workers = useStore(s => s.workers);
  const workerList = Object.values(workers);

  const scenario = useStore(s => s.scenario);
  const isEvacuation = scenario === 'EVACUATION';

  // Sort: DANGER/OFFLINE first, then WARNING, then NORMAL
  const sorted = [...workerList].sort((a, b) => {
    const getPriority = (w) => {
      if (w.alert === 'OFFLINE') return 0;
      if (w.alert === 'DANGER' || w.fall_status === 'FALL') return 1;
      if (w.alert === 'WARNING') return 2;
      return 3;
    };
    return getPriority(a) - getPriority(b);
  });

  return (
    <aside className="fixed left-0 top-20 h-[calc(100vh-7rem)] w-80 z-40 flex flex-col bg-white border-r-4 border-black">
      <div className="p-4 bg-black text-white flex justify-between items-end">
        <div>
          <h2 className="font-headline font-heavy text-sm uppercase leading-none">PERSONNEL</h2>
          <span className="font-label text-[8px] opacity-70 uppercase">LIVE MONITORING</span>
        </div>
        <span className="font-headline text-xl font-heavy tabular-nums">{workerList.length}/{workerList.length}</span>
      </div>
      
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {sorted.length === 0 && (
          <div className="p-8 text-center text-gray-400 font-headline text-xs uppercase">
            Waiting for telemetry...
          </div>
        )}

        {sorted.map(w => {
          const isOffline = w.alert === 'OFFLINE';
          const isDanger = w.alert === 'DANGER' || w.fall_status === 'FALL' || isOffline || isEvacuation;
          
          let alertInfo = w.fall_status === 'FALL' 
            ? statusMap.FALL 
            : (statusMap[w.alert] || statusMap.NORMAL);
            
          if (isEvacuation && !isOffline) {
            alertInfo = { text: 'EVACUATE NOW', status: 'alert' };
          }

          const hr = isOffline ? '--' : Math.round(w.hr || 75);
          const temp = isOffline ? '--' : (w.temp || 36.5).toFixed(1);
          const displayName = workerNames[w.worker_id] || w.worker_id;

          return (
            <div key={w.worker_id} className={`p-4 border-b-2 border-black flex flex-col gap-3 ${isDanger ? 'bg-red-100/50' : 'hover:bg-gray-100'} ${isOffline ? 'animate-glitch opacity-80' : ''} ${isEvacuation && !isOffline ? 'animate-pulse-fast' : ''}`}>
              <div className="flex gap-3">
                <div className={`w-12 h-12 ${isDanger ? 'bg-brand-red' : 'bg-black'} ${isOffline ? 'bg-gray-700' : ''} flex items-center justify-center text-white text-[10px] font-heavy shrink-0 transition-colors`}>
                  {w.worker_id.replace('WK_', '')}
                </div>
                <div className="flex-1 overflow-hidden">
                  <div className="flex justify-between items-center mb-1">
                    <span className={`font-headline font-heavy text-xs uppercase truncate ${isDanger && !isOffline ? 'text-brand-red' : ''} ${isOffline ? 'text-gray-500 line-through' : ''}`}>
                      {displayName}
                    </span>
                    <span className="font-label text-[8px] text-gray-500 ml-2">{w.worker_id}</span>
                  </div>
                  <AlertBadge text={alertInfo.text} status={alertInfo.status} />
                </div>
              </div>
              <div className={`grid grid-cols-2 gap-2 ${isOffline ? 'opacity-50 grayscale' : ''}`}>
                <BorderCard className={`p-2 border-2 ${isDanger && !isOffline ? 'border-brand-red bg-white' : ''}`}>
                  <span className={`block font-label text-[8px] font-heavy ${isDanger && !isOffline ? 'text-brand-red' : ''} opacity-60`}>BPM</span>
                  <span className={`font-headline text-2xl font-heavy tabular-nums ${isDanger && !isOffline ? 'text-brand-red' : ''}`}>{hr}</span>
                </BorderCard>
                <BorderCard className={`p-2 border-2 ${isDanger && !isOffline ? 'border-brand-red bg-white' : ''}`}>
                  <span className={`block font-label text-[8px] font-heavy ${isDanger && !isOffline ? 'text-brand-red' : ''} opacity-60`}>TEMP</span>
                  <span className={`font-headline text-2xl font-heavy tabular-nums ${isDanger && !isOffline ? 'text-brand-red' : ''}`}>{temp}°</span>
                </BorderCard>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
