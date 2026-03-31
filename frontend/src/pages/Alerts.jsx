import { useMemo } from 'react';
import useStore from '../store';

export default function Alerts() {
  const workers = useStore(s => s.workers);
  const zones = useStore(s => s.zones);
  
  const activeAlerts = useMemo(() => {
    const alerts = [];
    
    // Check zone alerts
    Object.entries(zones).forEach(([zoneId, data]) => {
      if (data.status === 'DANGER' || data.status === 'WARNING') {
        alerts.push({
          id: `zone-${zoneId}`,
          level: data.status,
          time: new Date().toLocaleTimeString('en-US', { hour12: false }),
          msg: `Toxic Gas Alert (${data.ch4} CH4, ${data.co} CO) detected in ${zoneId.replace('_', ' ')}`
        });
      }
    });

    // Check worker alerts
    Object.values(workers).forEach(w => {
      if (w.alert === 'DANGER' || w.alert === 'WARNING' || w.alert === 'OFFLINE' || w.fall_status === 'FALL') {
        const level = (w.alert === 'DANGER' || w.fall_status === 'FALL') ? 'CRITICAL WARNING' : w.alert;
        let msg = `Health/safety anomaly detected for ${w.worker_id} (${w.zone || 'UNKNOWN ZONE'})`;
        if (w.alert === 'OFFLINE') msg = `Signal lost for worker ${w.worker_id}. Last known location: ${w.zone || 'UNKNOWN'}`;
        if (w.fall_status === 'FALL') msg = `IMPACT / FALL DETECTED for worker ${w.worker_id}. Immediate assistance required.`;
        
        alerts.push({
          id: `worker-${w.worker_id}`,
          level: level.toUpperCase(),
          time: new Date(w.last_active * 1000).toLocaleTimeString('en-US', { hour12: false }) || 'NOW',
          msg: msg
        });
      }
    });
    
    return alerts;
  }, [workers, zones]);

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-brand-red pb-4 mb-8 uppercase tracking-tighter text-brand-red flex items-center gap-4">
        <span className="material-symbols-outlined text-4xl animate-ping" data-icon="warning">warning</span> 
        INCIDENT & ALERTS LOGS
      </h1>
      <div className="flex flex-col gap-4 overflow-auto">
        {activeAlerts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 font-heavy uppercase tracking-widest border-4 border-gray-300 border-dashed">
            ALL SYSTEMS NOMINAL. NO ACTIVE ALERTS.
          </div>
        ) : (
          activeAlerts.map((alert) => (
            <div key={alert.id} className="bg-white border-4 border-brand-red p-4 border-l-8 flex justify-between items-center transition-all hover:bg-gray-50 cursor-pointer">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className={`text-white text-[10px] uppercase font-heavy px-2 py-0.5 animate-pulse \${alert.level.includes('CRITICAL') || alert.level === 'DANGER' ? 'bg-brand-red' : 'bg-orange-600'}`}>{alert.level}</span>
                  <span className="font-headline text-xs text-black">TODAY, {alert.time}</span>
                </div>
                <p className="font-heavy uppercase text-xl">{alert.msg}</p>
              </div>
              <button className="border-2 border-black px-6 py-3 uppercase font-heavy text-xs hover:bg-black hover:text-white transition-none">Acknowledge</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
