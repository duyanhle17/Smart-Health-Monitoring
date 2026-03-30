import useStore from '../../store';
import { useState, useEffect } from 'react';

export default function FooterTicker() {
  const workers = useStore(s => s.workers);
  const isConnected = useStore(s => s.isConnected);
  const [logs, setLogs] = useState([]);

  // Generate logs based on worker alerts
  useEffect(() => {
    const workerList = Object.values(workers);
    const newLogs = [];
    const now = new Date().toLocaleTimeString('en-GB', { hour12: false });

    workerList.forEach(w => {
      if (w.alert === 'DANGER') {
        newLogs.push({ msg: `ALERT: ${w.worker_id} - CRITICAL VITAL STATUS DETECTED`, type: 'danger' });
      } else if (w.alert === 'WARNING') {
        newLogs.push({ msg: `WARNING: ${w.worker_id} - GAS/HEART RATE IRREGULARITY`, type: 'warning' });
      }
    });

    // Add general system logs if no alerts
    if (newLogs.length === 0) {
      newLogs.push({ msg: `INFO: SYSTEM STATUS OK - ${workerList.length} NODES ACTIVE`, type: 'info' });
      newLogs.push({ msg: `INFO: MESH-NET STABILITY: 98.4%`, type: 'info' });
      newLogs.push({ msg: `INFO: MONITORING WORKER DATA PACKETS [INCOMING]`, type: 'info' });
    }

    setLogs(newLogs.map(log => `[${now}] ${log.msg}`));
  }, [workers]);

  return (
    <footer className="fixed bottom-0 left-0 w-full z-50 h-8 flex items-center bg-gray-100 border-t-4 border-black overflow-hidden truncate">
      <div className="flex-shrink-0 bg-black text-white h-full px-4 flex items-center font-headline font-heavy text-[8px] uppercase tracking-widest z-20">
        SYSTEM_LOGS
      </div>
      <div className="flex-1 overflow-hidden h-full flex items-center justify-start relative whitespace-nowrap">
        <div className="animate-ticker flex justify-start items-center gap-12 ml-12 absolute left-0 text-[8px] font-label font-heavy text-black uppercase tracking-widest">
          {logs.map((log, i) => (
            <span key={i} className={`flex items-center gap-2 ${log.includes('ALERT') ? 'text-brand-red font-heavy' : log.includes('WARNING') ? 'text-orange-600' : ''}`}>
              {log}
            </span>
          ))}
          {/* Duplicate for infinite loop */}
          {logs.map((log, i) => (
            <span key={'dup-'+i} className={`flex items-center gap-2 ${log.includes('ALERT') ? 'text-brand-red font-heavy' : log.includes('WARNING') ? 'text-orange-600' : ''}`}>
              {log}
            </span>
          ))}
        </div>
      </div>
      <div className={`flex-shrink-0 bg-black text-white h-full px-4 flex items-center font-headline font-heavy text-[8px] uppercase tracking-widest z-20 ${!isConnected ? 'text-brand-red animate-pulse' : ''}`}>
        SYSTEM STATUS: {isConnected ? 'OPERATIONAL' : 'OFFLINE'}
      </div>
    </footer>
  );
}
